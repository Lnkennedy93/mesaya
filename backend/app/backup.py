"""Copias de seguridad automáticas (base de datos + fotos) y restauración.

  python -m app.backup now                  crea una copia ahora
  python -m app.backup list                 lista las copias
  python -m app.backup restore ARCHIVO --yes   restaura (detén el servidor antes)

La copia de la base usa la API de respaldo de SQLite: es consistente aunque el servidor esté atendiendo pedidos.
Con PostgreSQL (MESAYA_DATABASE_URL) la copia solo incluye las fotos: la base se respalda con los backups/PITR de tu
proveedor (Neon, Supabase, RDS...) o con pg_dump (ver DEPLOY.md).
NO incluye la clave de cifrado (MESAYA_SECRET_KEY / data/secret.key): guárdala aparte, nunca junto a las copias.
Las copias locales no te protegen si se pierde el disco: usa MESAYA_BACKUP_HOOK para subirlas a otro lugar
(ver DEPLOY.md) o activa los snapshots de tu proveedor."""
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import config, db

log = logging.getLogger("mesaya.backup")
PREFIX = "mesaya-"
_lock = threading.Lock()


def list_backups() -> list[Path]:
    if not config.BACKUP_DIR.exists():
        return []
    return sorted(config.BACKUP_DIR.glob(f"{PREFIX}*.zip"))


def last_backup_age_hours() -> float | None:
    files = list_backups()
    if not files:
        return None
    return round((time.time() - files[-1].stat().st_mtime) / 3600, 2)


def make_backup() -> Path:
    with _lock:
        config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        final = config.BACKUP_DIR / f"{PREFIX}{stamp}.zip"
        partial = final.with_suffix(".partial")
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "mesaya.db"
            if db.IS_PG:
                snap = None
                counts = {t: db.row(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("restaurants", "orders", "items")}
            else:
                src = sqlite3.connect(config.DB_PATH)
                dst = sqlite3.connect(snap)
                try:
                    src.backup(dst)
                finally:
                    src.close()
                check = dst.execute("PRAGMA integrity_check").fetchone()[0]
                counts = {t: dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("restaurants", "orders", "items")}
                dst.close()
                if check != "ok":
                    raise RuntimeError(f"La copia no pasó la verificación de integridad: {check}")
            n_files = 0
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
                if snap is not None:
                    z.write(snap, "mesaya.db")
                if config.UPLOAD_DIR.exists():
                    for f in config.UPLOAD_DIR.iterdir():
                        if f.is_file():
                            z.write(f, f"uploads/{f.name}")
                            n_files += 1
                z.writestr("MANIFEST.json", json.dumps({
                    "created_utc": stamp, "engine": "postgres" if db.IS_PG else "sqlite", "counts": counts, "uploads": n_files,
                    "terms_version": config.TERMS_VERSION}, indent=2))
        os.replace(partial, final)
        prune()
        log.info("Copia creada: %s", final.name)
    run_hook(final)
    return final


def prune():
    files = list_backups()
    for old in files[: max(0, len(files) - config.BACKUP_KEEP)]:
        old.unlink(missing_ok=True)


def run_hook(path: Path):
    if not config.BACKUP_HOOK:
        return
    try:
        subprocess.run(config.BACKUP_HOOK, shell=True, timeout=900, check=True,
                       env={**os.environ, "MESAYA_BACKUP_FILE": str(path)})
    except Exception as e:  # la copia local ya existe; solo avisamos
        log.error("El comando posterior a la copia falló: %s", type(e).__name__)


def restore(archive: Path):
    """Reemplaza la base y las fotos por las de la copia. El servidor debe estar detenido."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if db.IS_PG:
            if "mesaya.db" in names:
                raise RuntimeError("Esta instalación usa PostgreSQL: la copia es de SQLite. Restaura la base con pg_restore/tu proveedor.")
            if "MANIFEST.json" not in names:
                raise RuntimeError("El archivo no parece una copia de MesaYa (falta MANIFEST.json)")
            _restore_uploads(z, names)
            return
        if "mesaya.db" not in names:
            raise RuntimeError("El archivo no parece una copia de MesaYa (falta mesaya.db)")
        with tempfile.TemporaryDirectory() as tmp:
            z.extract("mesaya.db", tmp)
            probe = sqlite3.connect(Path(tmp) / "mesaya.db")
            ok = probe.execute("PRAGMA integrity_check").fetchone()[0]
            probe.close()
            if ok != "ok":
                raise RuntimeError("La copia está dañada: " + ok)
            if config.DB_PATH.exists():  # red de seguridad por si te equivocas de archivo
                shutil.copy2(config.DB_PATH, config.DB_PATH.with_name(config.DB_PATH.name + ".before-restore"))
            for ext in ("-wal", "-shm"):
                Path(str(config.DB_PATH) + ext).unlink(missing_ok=True)
            shutil.copy2(Path(tmp) / "mesaya.db", config.DB_PATH)
        _restore_uploads(z, names)


def _restore_uploads(z, names):
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for n in names:
        if n.startswith("uploads/") and not n.endswith("/"):
            target = config.UPLOAD_DIR / Path(n).name  # solo el nombre: evita rutas maliciosas
            with z.open(n) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def start_backup_loop():
    """Hilo en segundo plano: copia al arrancar si la última es antigua, y luego cada MESAYA_BACKUP_EVERY_HOURS."""
    if config.BACKUP_EVERY_HOURS <= 0:
        log.warning("Copias automáticas DESACTIVADAS (MESAYA_BACKUP_EVERY_HOURS=0)")
        return

    def loop():
        time.sleep(30)
        while True:
            try:
                age = last_backup_age_hours()
                if age is None or age >= config.BACKUP_EVERY_HOURS:
                    make_backup()
            except Exception as e:
                log.error("Falló la copia automática: %s", e)
            time.sleep(600)

    threading.Thread(target=loop, daemon=True, name="backup").start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "now"
    if cmd == "now":
        print("Copia creada:", make_backup())
    elif cmd == "list":
        for f in list_backups():
            print(f"{f.name}  {f.stat().st_size / 1024:.0f} KB")
    elif cmd == "restore" and len(sys.argv) > 2:
        if "--yes" not in sys.argv:
            sys.exit("Esto reemplaza tus datos actuales. Detén el servidor y repite con --yes")
        restore(Path(sys.argv[2]))
        print("Restauración completa. Arranca el servidor de nuevo.")
    else:
        sys.exit(__doc__)
