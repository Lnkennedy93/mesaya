"""Fase 7 de la auditoría: limpieza de sesiones, unicidad de pedidos, healthz y errores de validación.
python -m tests.test_fase7"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, db  # noqa: E402
from app.main import app  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as c:
    # ---------------- healthz: sin datos de más y también por HEAD
    g, h = c.get("/healthz"), c.head("/healthz")
    check(g.status_code == 200 and g.json()["ok"] and "engine" not in g.json(), "healthz responde ok y no dice qué motor de base de datos usa")
    check(h.status_code == 200, "HEAD /healthz también responde (los monitores de disponibilidad lo usan)")

    # ---------------- errores de validación sin la estructura interna de FastAPI
    r = c.post("/api/login", content=b"{roto", headers={"content-type": "application/json"})
    check(r.status_code == 422 and r.json() == {"error": "Revisa los datos ingresados"}, "un cuerpo inválido da 422 con un mensaje claro, no el detalle interno")

    me = c.post("/api/signup", json={"accept_terms": True, "name": "Fase Siete", "email": "f7@x.co", "password": "secreto123", "tables": 3}).json()
    rid = me["restaurant"]["id"]
    cat = c.post("/api/categories", json={"name": "Platos"}).json()["id"]
    plato = c.post("/api/items", json={"category_id": cat, "name": "Burger", "price": 10000}).json()["id"]
    t = c.get("/api/tables").json()["tables"][0]

    # ---------------- la idempotencia tiene una red de seguridad en la base
    base = f"/api/public/{me['restaurant']['slug']}/orders"
    body = {"table": t["label"], "key": t["secret"], "diner_id": "d", "diner_name": "Ana", "items": [{"item_id": plato, "qty": 1}], "request_id": "intento-1"}
    a, b = c.post(base, json=body), c.post(base, json=body)
    check(a.json()["order_id"] == b.json()["order_id"] and b.json().get("duplicate"), "reintentar el mismo envío sigue devolviendo el mismo pedido")
    dup = False
    try:
        db.run("INSERT INTO orders(restaurant_id, table_label, seq, status, created_at, client_ref) VALUES (?,?,?,?,?,?)",
               (rid, t["label"], 99, "new", auth.now(), "intento-1"))
    except Exception:
        dup = True
    check(dup, "y si algo se saltara el candado, la base rechaza el pedido duplicado")
    db.run("INSERT INTO orders(restaurant_id, table_label, seq, status, created_at, client_ref) VALUES (?,?,?,?,?,?)", (rid, t["label"], 98, "new", auth.now(), ""))
    db.run("INSERT INTO orders(restaurant_id, table_label, seq, status, created_at, client_ref) VALUES (?,?,?,?,?,?)", (rid, t["label"], 97, "new", auth.now(), ""))
    check(db.row("SELECT COUNT(*) n FROM orders WHERE client_ref=''")["n"] == 2, "los pedidos sin client_ref (versiones viejas del celular) no chocan entre sí")

    # ---------------- limpieza de sesiones y enlaces vencidos
    old = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(FMT)
    new = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(FMT)
    db.run("INSERT INTO sessions(token, restaurant_id, role, expires_at) VALUES (?,?,?,?)", ("vencida", rid, "staff", old))
    db.run("INSERT INTO sessions(token, restaurant_id, role, expires_at) VALUES (?,?,?,?)", ("vigente", rid, "staff", new))
    db.run("INSERT INTO password_resets(token_hash, restaurant_id, expires_at) VALUES (?,?,?)", ("h1", rid, old))
    db.run("INSERT INTO password_resets(token_hash, restaurant_id, expires_at) VALUES (?,?,?)", ("h2", rid, new))
    auth.purge_expired()
    check(db.row("SELECT 1 FROM sessions WHERE token='vencida'") is None and db.row("SELECT 1 FROM sessions WHERE token='vigente'") is not None, "se borran las sesiones vencidas y se conservan las vigentes")
    check(db.row("SELECT 1 FROM password_resets WHERE token_hash='h1'") is None and db.row("SELECT 1 FROM password_resets WHERE token_hash='h2'") is not None, "y los enlaces de reseteo vencidos")
    check(c.get("/api/me").status_code == 200, "la sesión de la persona que está usando el panel sigue viva")

print("Fase 7 ✔")
