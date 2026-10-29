"""Límites de ritmo del comensal:  python -m tests.test_limits
Muchas mesas comparten la IP del WiFi del local: no deben bloquearse entre sí.
(usa una base de datos temporal, no toca la tuya)"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"
os.environ["MESAYA_DEMO"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


WIFI = {"x-forwarded-for": "190.0.0.1"}  # todas las mesas salen por la misma IP


def order(c, slug, n, key=None, ip=WIFI):
    return c.post(f"/api/public/{slug}/orders", headers=ip, json={
        "table": str(n), "key": key or f"k{n}", "diner_id": f"d{n}",
        "items": [{"item_id": ITEM, "qty": 1}]})


with TestClient(app) as c:
    r = c.post("/api/signup", json={"accept_terms": True, "name": "Café Límites", "email": "l@b.co", "password": "secreto123", "tables": 1})
    slug = r.json()["restaurant"]["slug"]
    rid = db.row("SELECT id FROM restaurants WHERE slug=?", (slug,))["id"]
    draft = c.post("/api/import/text", json={"text": "# Platos\nEmpanadas - 8.000\n"}).json()
    c.post("/api/import/commit", json=draft)
    ITEM = c.get("/api/menu").json()["categories"][0]["items"][0]["id"]
    for n in range(1, 61):
        db.run("INSERT INTO tables_(restaurant_id,label,secret) VALUES (?,?,?) ON CONFLICT(restaurant_id,label) DO UPDATE SET secret=excluded.secret", (rid, str(n), f"k{n}"))

    # 60 mesas, una sola IP (WiFi del local): todas deben poder pedir
    codes = [order(c, slug, n).status_code for n in range(1, 61)]
    check(codes.count(200) == 60, "60 mesas pidiendo desde la misma IP: ningún pedido rechazado")

    # una misma mesa no puede inundar la cocina
    spam = [order(c, slug, 1).status_code for _ in range(20)]
    check(spam.count(429) >= 1 and 200 in spam, "una mesa que repite pedidos sí es frenada")
    check(order(c, slug, 2).status_code in (200,), "…pero otra mesa de la misma IP sigue pudiendo pedir")

    # llamadas al mesero por mesa
    calls = [c.post(f"/api/public/{slug}/call", headers=WIFI, json={"table": str(n), "key": f"k{n}", "type": "waiter"}).status_code
             for n in range(1, 31)]
    check(calls.count(200) == 30, "30 mesas llaman al mesero desde la misma IP")

    # calificaciones por mesa (no llevan clave)
    fb = [c.post(f"/api/public/{slug}/feedback", headers=WIFI, json={"table": str(n), "rating": 5}).status_code for n in range(1, 21)]
    check(fb.count(200) == 20, "20 mesas califican desde la misma IP")

    # fuerza bruta de la clave de una mesa: se corta por IP
    atacante = {"x-forwarded-for": "6.6.6.6"}
    bad = [order(c, slug, 5, key=f"mala{i}", ip=atacante).status_code for i in range(40)]
    check(bad[:30] == [403] * 30 and bad[30:] == [429] * 10, "clave errónea: 30 intentos y luego bloqueo por IP")
    check(order(c, slug, 7).status_code == 200, "el bloqueo del atacante no afecta al WiFi del local")

    # las lecturas (/menu, /bill) comparten el mismo contador: no sirven para adivinar la clave sin límite
    intruso = {"x-forwarded-for": "7.7.7.7"}
    menus = [c.get(f"/api/public/{slug}/menu?t=5&k=x{i}", headers=intruso).json()["table_ok"] for i in range(30)]
    check(not any(menus), "/menu con clave errónea: table_ok siempre falso")
    check(c.get(f"/api/public/{slug}/bill?table=5&k=otra", headers=intruso).status_code == 429, "/bill: tras 30 intentos fallidos en /menu, la IP queda bloqueada")
    check(not c.get(f"/api/public/{slug}/menu?t=5&k=k5", headers=intruso).json()["table_ok"], "/menu: la IP bloqueada no confirma ni la clave correcta")
    check(c.get(f"/api/public/{slug}/menu?t=5&k=k5", headers=WIFI).json()["table_ok"], "/menu: el WiFi del local con su clave sigue funcionando")

print("\nLímites ✔")
