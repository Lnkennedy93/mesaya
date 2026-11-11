"""Superusuario: lista de negocios, licencia, mesas, IA y contraseña.   python -m tests.test_superadmin"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

H = {"x-admin-key": "k"}


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as c, TestClient(app) as dueno:
    dueno.post("/api/signup", json={"accept_terms": True, "name": "Café Uno", "email": "uno@b.co", "password": "secreto123", "tables": 7})
    a = lambda path, **b: c.post("/api/superadmin/" + path, headers=H, json={"email": "uno@b.co", **b})

    check(c.get("/api/superadmin/restaurants").status_code == 403, "sin clave: 403")
    for _ in range(8):  # +1 del intento sin clave de arriba
        c.get("/api/superadmin/restaurants", headers={"x-admin-key": "mala"})
    check(c.get("/api/superadmin/restaurants", headers=H).status_code == 200, "9 fallos aún no bloquean")
    c.get("/api/superadmin/restaurants", headers={"x-admin-key": "mala"})
    check(c.get("/api/superadmin/restaurants", headers=H).status_code == 429, "tras 10 fallos la clave se bloquea un rato (429)")
    from app import db  # noqa: E402
    db.run("DELETE FROM rate_hits")

    r = c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"][0]
    check(r["name"] == "Café Uno" and r["tables_used"] == 7 and r["tables_limit"] == 7 and r["active"] and r["effective_plan"] == "Esencial",
          "lista: negocio con mesas usadas/límite y plan efectivo")

    check(a("activate", plan="pro", no_expiry=True).status_code == 200, "activar Pro")
    r = c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"][0]
    check(r["effective_plan"] == "Pro" and r["tables_limit"] == 13 and r["ai_asks"] == 300, "Pro activo: 13 mesas y 300 preguntas de IA")
    check(a("activate", plan="pro", extra_tables=5).status_code == 200 and
          c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"][0]["tables_limit"] == 18, "mesas adicionales también suman en Pro")

    check(a("activate", plan="basic", status="inactive").status_code == 200, "desactivar licencia")
    r = c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"][0]
    check(not r["active"] and r["effective_plan"] == "Gratis" and r["tables_limit"] == 3, "desactivada en plena prueba: queda en plan Gratis")

    check(a("activate", plan="basic", ai_addon=True, no_expiry=True).status_code == 200 and
          c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"][0]["ai_asks"] == 120, "reactivar Esencial con IA: 120 preguntas")
    check(a("activate", plan="basic", ai_addon=False).status_code == 200 and
          c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"][0]["ai_asks"] == 0, "quitar la IA al Esencial")
    check(c.post("/api/superadmin/activate", headers=H, json={"email": "nadie@b.co", "plan": "pro"}).status_code == 404, "correo inexistente: 404")

    # contraseña
    check(dueno.get("/api/me").status_code == 200, "el dueño tiene sesión abierta")
    check(a("set-password", password="corta").status_code == 400, "contraseña corta: 400")
    check(c.post("/api/superadmin/set-password", json={"email": "uno@b.co", "password": "NuevaClave99"}).status_code == 403, "cambiar contraseña exige la clave")
    check(a("set-password", password="NuevaClave99").status_code == 200, "contraseña cambiada")
    check(dueno.get("/api/me").status_code == 401, "sus sesiones abiertas se cerraron")
    with TestClient(app) as n:
        check(n.post("/api/login", json={"email": "uno@b.co", "password": "secreto123"}).status_code != 200, "la clave vieja ya no entra")
        check(n.post("/api/login", json={"email": "uno@b.co", "password": "NuevaClave99"}).status_code == 200, "la nueva sí entra")

print("\nTodo OK")
