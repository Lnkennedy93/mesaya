"""Arma el video: locución (voz es-CO Salomé, igual que los demás videos) + cuadros + ffmpeg.
Usa el Python que tenga edge_tts (el venv de Proyecto_monetización) y el ffmpeg que trae imageio_ffmpeg.

    python make_video.py            → horizontal 16:9 y vertical 9:16 en out/
    python make_video.py h          → solo uno
"""
import asyncio
import glob
import json
import os
import re
import subprocess
import sys

import edge_tts

VOICE = "es-CO-SalomeNeural"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT, AUDIO = os.path.join(HERE, "out"), os.path.join(HERE, "audio")
SIZES = {"h": (1920, 1080, "16x9"), "v": (1080, 1920, "9x16")}
FPS = 30


def ffmpeg_exe() -> str:
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    hits = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Python\*\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-*.exe"))
    if not hits:
        raise SystemExit("No encuentro ffmpeg: define FFMPEG con su ruta.")
    return hits[0]


FF = ffmpeg_exe()


def run(args):
    p = subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit("ffmpeg falló:\n" + p.stderr[-1500:])


def duration(path) -> float:
    err = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


async def voices(scenes):
    os.makedirs(AUDIO, exist_ok=True)
    for sc in scenes:
        path = os.path.join(AUDIO, sc["id"] + ".mp3")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            continue  # ya generada: borra audio/ para volver a locutar
        await edge_tts.Communicate(text=sc["vo"], voice=VOICE, rate="+0%").save(path)
        print("  voz", sc["id"], f"{duration(path):.1f}s")


def clip(o, sc):
    w, h, _ = SIZES[o]
    a = os.path.join(AUDIO, sc["id"] + ".mp3")
    d = max(4.5, duration(a) + 1.0)
    frames = int(d * FPS)
    out = os.path.join(OUT, f"_{o}_{sc['id']}.mp4")
    vf = (f"scale={w * 2}:{h * 2},zoompan=z='min(zoom+0.0004,1.05)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS},"
          f"fade=t=in:st=0:d=0.25,fade=t=out:st={d - 0.25:.2f}:d=0.25,format=yuv420p")
    run(["-loop", "1", "-i", os.path.join(HERE, "frames", o, sc["id"] + ".png"), "-i", a,
         "-vf", vf, "-af", "adelay=350|350,apad,aresample=44100", "-t", f"{d:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ac", "2", out])
    return out, d


def main():
    scenes = json.load(open(os.path.join(HERE, "scenes.json"), encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    asyncio.run(voices(scenes))
    for o in (sys.argv[1:] or SIZES):
        clips, total = [], 0.0
        for sc in scenes:
            c, d = clip(o, sc)
            clips.append(c)
            total += d
        lst = os.path.join(OUT, f"_{o}.txt")
        open(lst, "w", encoding="utf-8").write("".join(f"file '{c.replace(os.sep, '/')}'\n" for c in clips))
        final = os.path.join(OUT, f"MesaYa-promo-{SIZES[o][2]}.mp4")
        run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", final])
        for c in clips + [lst]:
            os.remove(c)
        print(f"✓ {final}  ({total:.0f} s, {os.path.getsize(final) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
