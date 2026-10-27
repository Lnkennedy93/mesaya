"""Operación: recuperar contraseña, términos/datos, borrado de cuenta, copias y validaciones de producción.
python -m tests.test_ops"""
import os
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_BACKUP_DIR"] = str(tmp / "bk")
os.environ["MESAYA_SECRET_KEY"] = "cFhmZ3N3N2pFb0F4dDJyV2xRR2hQZ3ZtQ0hCQ2ZQZmM="
os.environ["MESAYA_ADMIN_KEY"] = "k" * 24
os.environ["MESAYA_BACKUP_KEEP"] = "2"
os.environ["MESAYA_BACKUP_EVERY_HOURS"] = "0"  # el hilo automático no interviene en la prueba
os.environ["MESAYA_COMPANY_NAME"] = "Mesa Software SAS"
os.environ["MESAYA_COMPANY_NIT"] = "901.234.567-8"
os.environ["MESAYA_COMPANY_EMAIL"] = "datos@mesaya.test"
for k in ("MESAYA_ONLINE_PAYMENTS", "MESAYA_INVOICING", "MESAYA_DEMO"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402

from app import backup, config, db, mailer  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


SENT = []
mailer.configured = lambda: True
mailer.send = lambda to, subject, body: SENT.append((to, subject, body)) or True
import app.account as account_mod  # noqa: E402

account_mod.mailer = mailer

with TestClient(app) as c:
    # --- consentimiento
    base = {"name": "Café Uno", "email": "uno@cafe.co", "password": "secreto123", "tables": 2}
    r = c.post("/api/signup", json=base)
    check(r.status_code == 400 and "Términos" in r.json()["error"], "no se crea la cuenta sin aceptar términos y datos")
    r = c.post("/api/signup", json={**base, "accept_terms": True})
    check(r.status_code == 200 and r.json()["terms_current"] is True, "al aceptar se guarda fecha y versión")
    slug = r.json()["restaurant"]["slug"]
    row = db.row("SELECT terms_accepted_at, terms_version FROM restaurants WHERE slug=?", (slug,))
    check(row["terms_accepted_at"] and row["terms_version"] == config.TERMS_VERSION, "constancia de aceptación en la base de datos")

    # --- páginas legales
    t = c.get("/terminos")
    check(t.status_code == 200 and "Mesa Software SAS" in t.text and "901.234.567-8" in t.text, "Términos muestran los datos de tu empresa")
    p = c.get("/privacidad")
    check(p.status_code == 200 and "Ley 1581" in p.text and "datos@mesaya.test" in p.text and "{{" not in p.text, "Política de datos completa y sin marcadores")
    check("BORRADOR" in p.text, "avisa que es borrador mientras falten datos de la empresa (dirección, ciudad, teléfono)")

    # --- recuperar contraseña
    c.post("/api/logout")
    a = c.post("/api/forgot", json={"email": "nadie@nada.co"}).json()
    b = c.post("/api/forgot", json={"email": "uno@cafe.co"}).json()
    check(a == b and len(SENT) == 1, "misma respuesta exista o no el correo; solo se envía uno")
    link = re.search(r"https?://\S+/reset\?token=(\S+)", SENT[0][2])
    check(bool(link), "el correo trae un enlace de recuperación")
    token = link.group(1)
    check(token not in str(db.rows("SELECT * FROM password_resets")), "en la base solo se guarda el hash del token")
    check(c.post("/api/reset", json={"token": "falso", "password": "nuevaclave1"}).status_code == 400, "token falso rechazado")
    old = c.post("/api/login", json={"email": "uno@cafe.co", "password": "secreto123"})
    check(old.status_code == 200, "la clave anterior sigue sirviendo hasta usar el enlace")
    r = c.post("/api/reset", json={"token": token, "password": "nuevaclave1"})
    check(r.status_code == 200, "el enlace cambia la contraseña")
    check(c.post("/api/reset", json={"token": token, "password": "otraclave99"}).status_code == 400, "el enlace es de un solo uso")
    c.post("/api/logout")
    check(c.post("/api/login", json={"email": "uno@cafe.co", "password": "secreto123"}).status_code == 401, "la clave vieja ya no entra")
    check(c.post("/api/login", json={"email": "uno@cafe.co", "password": "nuevaclave1"}).status_code == 200, "entra con la nueva")
    db.run("UPDATE password_resets SET used_at=NULL, expires_at='2000-01-01 00:00:00'")
    check(c.post("/api/reset", json={"token": token, "password": "otraclave99"}).status_code == 400, "enlace vencido rechazado")
    check(c.post("/api/forgot", json={"email": "uno@cafe.co"}).status_code == 200 and c.post("/api/forgot", json={"email": "uno@cafe.co"}).status_code == 200,
          "se permiten varios intentos legítimos")
    check(c.post("/api/forgot", json={"email": "uno@cafe.co"}).status_code == 429, "límite por correo contra abuso (3/hora)")

    # --- soporte sin SMTP
    check(c.post("/api/superadmin/reset-link", json={"email": "uno@cafe.co"}).status_code == 403, "enlace de soporte exige la clave de administrador")
    sl = c.post("/api/superadmin/reset-link", json={"email": "uno@cafe.co"}, headers={"x-admin-key": "k" * 24}).json()
    check("/reset?token=" in sl["link"], "soporte puede generar el enlace para enviarlo por WhatsApp")

    # --- cambiar contraseña desde el panel (cierra las otras sesiones)
    other = TestClient(app)
    other.post("/api/login", json={"email": "uno@cafe.co", "password": "nuevaclave1"})
    check(other.get("/api/me").status_code == 200, "segunda sesión abierta")
    check(c.post("/api/password", json={"current": "mal", "password": "terceraclave1"}).status_code == 400, "exige la contraseña actual")
    check(c.post("/api/password", json={"current": "nuevaclave1", "password": "terceraclave1"}).status_code == 200, "cambio de contraseña")
    check(other.get("/api/me").status_code == 401 and c.get("/api/me").status_code == 200, "las otras sesiones se cierran y la actual sigue")

    # --- nueva versión de términos
    config.TERMS_VERSION = "9999"
    check(c.get("/api/me").json()["terms_current"] is False, "al subir la versión se vuelve a pedir aceptación")
    c.post("/api/accept-terms")
    check(c.get("/api/me").json()["terms_current"] is True, "se acepta de nuevo")

    # --- copias de seguridad
    cat = c.post("/api/categories", json={"name": "Platos"}).json()["id"]
    item = c.post("/api/items", json={"category_id": cat, "name": "Arepa", "price": 9000}).json()["id"]
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (config.UPLOAD_DIR / "foto.webp").write_bytes(b"RIFFfake")
    f1 = backup.make_backup()
    with zipfile.ZipFile(f1) as z:
        names = z.namelist()
    check({"mesaya.db", "MANIFEST.json", "uploads/foto.webp"} <= set(names), "la copia incluye base de datos, fotos y manifiesto")
    check("secret.key" not in " ".join(names), "la copia NO incluye la clave de cifrado")
    h = c.get("/healthz").json()
    check(h["ok"] and h["backup_age_hours"] is not None and h["backup_age_hours"] < 1 and not h["backup_stale"], "healthz informa la edad de la última copia")
    import time
    time.sleep(1.1)
    backup.make_backup()
    time.sleep(1.1)
    backup.make_backup()
    check(len(backup.list_backups()) == 2, "rotación: solo se conservan las últimas 2")

    # --- restaurar tras un desastre
    db.run("DELETE FROM items")
    (config.UPLOAD_DIR / "foto.webp").unlink()
    check(db.row("SELECT COUNT(*) n FROM items")["n"] == 0, "(simulamos la pérdida de datos)")
    backup.restore(backup.list_backups()[-1])
    check(db.row("SELECT COUNT(*) n FROM items")["n"] == 1 and (config.UPLOAD_DIR / "foto.webp").exists(), "restauración recupera datos y fotos")
    check(Path(str(config.DB_PATH) + ".before-restore").exists(), "queda una copia de seguridad de lo que había antes de restaurar")
    bad = tmp / "malo.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("otra_cosa.txt", "x")
    try:
        backup.restore(bad)
        check(False, "rechaza archivos que no son copias")
    except RuntimeError:
        check(True, "rechaza archivos que no son copias de MesaYa")

    # --- borrar cuenta (derecho de supresión)
    (config.UPLOAD_DIR / "logo_x.webp").write_bytes(b"x")
    db.run("UPDATE items SET image=? WHERE id=?", ("/uploads/logo_x.webp", item))
    check(c.post("/api/account/delete", json={"password": "mala", "confirm": slug}).status_code == 400, "borrar exige la contraseña")
    check(c.post("/api/account/delete", json={"password": "terceraclave1", "confirm": "otro"}).status_code == 400, "borrar exige escribir el código del restaurante")
    check(c.post("/api/account/delete", json={"password": "terceraclave1", "confirm": slug}).status_code == 200, "cuenta eliminada")
    left = sum(db.row(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("restaurants", "items", "categories", "tables_", "orders"))
    check(left == 0, "se borran carta, mesas y pedidos (cascada)")
    check(not (config.UPLOAD_DIR / "logo_x.webp").exists(), "se borran las fotos del restaurante")
    check(c.post("/api/login", json={"email": "uno@cafe.co", "password": "terceraclave1"}).status_code == 401, "ya no puede entrar")

# --- validaciones de producción
config.BASE_URL, config.ADMIN_KEY, config.DEMO_MODE = "http://localhost:8000", "corta", True
probs = " | ".join(config.blocking_problems())
check("https://" in probs and "ADMIN_KEY" in probs and "MESAYA_DEMO" in probs, "producción se niega a arrancar con HTTP, clave débil o modo demo")
config.BASE_URL, config.ADMIN_KEY, config.DEMO_MODE = "https://carta.ejemplo.co", "x" * 32, False
config.COMPANY = {k: "dato" for k in config.COMPANY}
check(config.blocking_problems() == [], "con la configuración correcta no hay bloqueos")

print("\nOperación ✔")
