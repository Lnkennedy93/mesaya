"""Fotos, logos y cartas originales en Vercel Blob:  python -m tests.test_storage
(Blob simulado en memoria; la base es temporal)"""
import io
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import storage  # noqa: E402
from app.main import app  # noqa: E402

HOST = "https://abc.public.blob.vercel-storage.com/"
blobs: dict[str, bytes] = {}
broken = {"put": False, "prefix": False}


def fake_put(path, data, content_type, random_suffix=False):
    if broken["put"]:
        raise RuntimeError("Blob caído")
    url = HOST + path + (f"-{len(blobs)}x" if random_suffix else "")
    blobs[url] = data
    return url


def fake_delete(urls):
    for u in urls:
        blobs.pop(u, None)


def fake_delete_prefix(prefix, keep=""):
    if broken["prefix"]:
        raise RuntimeError("Blob caído")
    for u in [u for u in blobs if u.startswith(HOST + prefix) and u != keep]:
        del blobs[u]


storage.enabled, storage.put, storage.delete, storage.delete_prefix = lambda: True, fake_put, fake_delete, fake_delete_prefix


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def png(color="red"):
    b = io.BytesIO()
    Image.new("RGB", (60, 60), color).save(b, "PNG")
    return b.getvalue()


def mine(rid, sub=""):
    return [u for u in blobs if u.startswith(f"{HOST}r{rid}/{sub}")]


with TestClient(app) as c:
    me = c.post("/api/signup", json={"accept_terms": True, "name": "Blob Café", "email": "b@b.co", "password": "secreto123", "tables": 3}).json()
    rid = me["restaurant"]["id"]

    check(storage.owns(f"{HOST}r{rid}/img-1.webp", rid) and not storage.owns(f"{HOST}r{rid + 1}/img-1.webp", rid)
          and not storage.owns(f"https://evil.example.com/r{rid}/img-1.webp", rid) and not storage.owns("/uploads/x.webp", rid),
          "owns(): solo URLs de Blob de este restaurante")

    # logo
    logo1 = c.post("/api/logo", files={"file": ("l.png", png())}).json()["logo"]
    check(logo1.startswith(f"{HOST}r{rid}/img-") and logo1 in blobs, "el logo se sube a Blob, no a la base")
    logo2 = c.post("/api/logo", files={"file": ("l.png", png("blue"))}).json()["logo"]
    check(logo2 in blobs and logo1 not in blobs, "al cambiar el logo se borra el anterior de Blob")

    # foto de un plato
    draft = c.post("/api/import/text", json={"text": "# Entradas\nEmpanadas - 8.000\n"}).json()
    c.post("/api/import/commit", json=draft)
    it = c.get("/api/menu").json()["categories"][0]["items"][0]
    p1 = c.post(f"/api/items/{it['id']}/image", files={"file": ("f.png", png())}).json()["image"]
    check(p1 in blobs, "la foto del plato se sube a Blob")
    p2 = c.post(f"/api/items/{it['id']}/image", files={"file": ("f.png", png("green"))}).json()["image"]
    check(p2 in blobs and p1 not in blobs, "al cambiar la foto se borra la anterior")
    check(c.get("/api/menu").json()["categories"][0]["items"][0]["image"] == p2, "la carta devuelve la URL de Blob")
    c.delete(f"/api/items/{it['id']}")
    check(p2 not in blobs, "al borrar el plato se borra su foto")

    # catálogo original: se conserva solo el último
    csv1 = b"categoria,nombre,precio\nEntradas,Empanada,8000\n"
    check(c.post("/api/import/ai", files={"file": ("carta uno.csv", csv1, "text/csv")}).status_code == 200, "la carta se lee igual")
    cat1 = mine(rid, "catalogs/")
    check(len(cat1) == 1 and "carta_uno.csv" in cat1[0], "el archivo original queda en Blob con nombre limpio")
    c.post("/api/import/ai", files={"file": ("dos.csv", csv1, "text/csv")})
    cat2 = mine(rid, "catalogs/")
    check(len(cat2) == 1 and cat2 != cat1, "solo se conserva la última carta")

    # si Blob falla, nada se pierde: la foto va a la base y la carta se lee igual
    broken["put"] = True
    lg = c.post("/api/logo", files={"file": ("l.png", png("black"))})
    check(lg.status_code == 200 and lg.json()["logo"].startswith("/uploads/"), "con Blob caído, el logo se guarda en la base")
    check(c.get(lg.json()["logo"]).status_code == 200, "…y se sirve igual desde /uploads")
    check(c.post("/api/import/ai", files={"file": ("tres.csv", csv1, "text/csv")}).status_code == 200, "con Blob caído, la carta se lee igual")
    broken["put"] = False

    # borrar la cuenta borra los archivos; si Blob falla, la cuenta NO se borra
    c.post("/api/logo", files={"file": ("l.png", png())})
    check(len(mine(rid)) >= 2, "hay archivos del restaurante en Blob")
    broken["prefix"] = True
    r = c.post("/api/account/delete", json={"password": "secreto123", "confirm": me["restaurant"]["slug"]})
    check(r.status_code == 503 and c.get("/api/me").status_code == 200, "con Blob caído la cuenta no se borra a medias")
    broken["prefix"] = False
    r = c.post("/api/account/delete", json={"password": "secreto123", "confirm": me["restaurant"]["slug"]})
    check(r.status_code == 200 and not mine(rid), "al borrar la cuenta no queda nada del restaurante en Blob")

print("\nBlob ✔")
