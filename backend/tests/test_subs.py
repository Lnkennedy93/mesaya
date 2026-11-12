"""Fase 4 de la auditoría: la suscripción vence y se cancela sin borrar datos, auditoría del superusuario y pedidos idempotentes.
python -m tests.test_subs"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"

from fastapi.testclient import TestClient  # noqa: E402

from app import config, db, mailer  # noqa: E402
from app.main import app  # noqa: E402

H = {"x-admin-key": "k"}
FMT = "%Y-%m-%d %H:%M:%S"


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def dias(paid):
    return (datetime.strptime(paid, FMT) - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() / 86400


sent = []
mailer.send = lambda to, subject, body: sent.append((to, subject)) or True  # el correo real no se envía en pruebas

with TestClient(app) as o, TestClient(app) as cust, TestClient(app) as kit:
    me0 = o.post("/api/signup", json={"accept_terms": True, "name": "Sub SA", "email": "s@x.co", "password": "secreto123", "tables": 7}).json()
    slug, pin = me0["restaurant"]["slug"], me0["restaurant"]["staff_pin"]
    kit.post("/api/staff-login", json={"slug": slug, "pin": pin})
    cat = o.post("/api/categories", json={"name": "Platos"}).json()["id"]
    plato = o.post("/api/items", json={"category_id": cat, "name": "Burger", "price": 10000}).json()["id"]
    sec = {t["label"]: t["secret"] for t in o.get("/api/tables").json()["tables"]}
    act = lambda **b: o.post("/api/superadmin/activate", headers=H, json={"email": "s@x.co", **b})  # noqa: E731
    me = lambda: o.get("/api/me").json()  # noqa: E731
    pedir = lambda mesa, **b: cust.post(f"/api/public/{slug}/orders", json={"table": mesa, "key": sec[mesa], "diner_id": "d", "diner_name": "Ana", "items": [{"item_id": plato, "qty": 1}], **b})  # noqa: E731

    # ---------------- entradas inválidas del superusuario
    check(act(status="activo").status_code == 400, "un estado mal escrito se rechaza (antes bajaba al cliente a Gratis)")
    check(act(plan=["x"]).status_code == 400 and act(plan="nada").status_code == 400, "un plan inválido da 400, no 500")
    check(act(plan="pro", extra_tables="abc").status_code == 400, "mesas adicionales no numéricas: 400")
    check(act(plan="pro", period_days=0).status_code == 400 and act(plan="pro", period_days="x").status_code == 400 and act(plan="pro", period_days=99999).status_code == 400, "periodo fuera de rango: 400")

    # ---------------- la suscripción tiene fecha de vencimiento
    check(act(plan="pro", period_days=30).status_code == 200, "activa 30 días")
    r = me()["restaurant"]
    check(r["subscription_status"] == "active" and 29.9 < dias(r["paid_until"]) < 30.1 and me()["sub_days_left"] in (30, 31) and me()["active"], "queda activa hasta dentro de 30 días")
    act(plan="pro", period_days=30)
    check(59.9 < dias(me()["restaurant"]["paid_until"]) < 60.1, "renovar suma al periodo que todavía le queda (60 días)")
    act(plan="pro")
    check(59.9 < dias(me()["restaurant"]["paid_until"]) < 60.1, "activar sin periodo conserva la fecha (compatibilidad)")
    act(plan="pro", no_expiry=True)
    check(me()["restaurant"]["paid_until"] == "" and me()["sub_days_left"] is None and me()["active"], "«sin vencimiento» (demo) no vence nunca")
    act(plan="pro", period_days=10)
    db.run("UPDATE restaurants SET paid_until=? WHERE email='s@x.co'", ((datetime.now(timezone.utc) - timedelta(days=2)).strftime(FMT),))
    m = me()
    check(not m["active"] and m["plan"]["tables"] == 3 and m["sub_days_left"] <= -1, "vencida: pasa al plan Gratis (3 mesas) y el panel sabe cuántos días lleva vencida")
    check(pedir("1").status_code == 200 and pedir("5").status_code == 402, "vencida: las 3 primeras mesas reciben pedidos y el resto no")
    check(o.get("/api/tables").status_code == 200 and len(o.get("/api/tables").json()["tables"]) == 7 and o.get("/api/menu").json()["categories"], "y el panel, las 7 mesas y la carta siguen ahí: no se bloquea nada ni se borra")
    act(plan="pro", period_days=30)
    r = me()
    check(r["active"] and 29.9 < dias(r["restaurant"]["paid_until"]) < 30.1, "renovar una vencida cuenta desde hoy")
    check(pedir("5").status_code == 200, "y vuelve a recibir pedidos en todas las mesas")

    # ---------------- cancelar la suscripción sin borrar nada
    check(kit.post("/api/subscription/cancel").status_code == 403, "la cocina (PIN) no puede cancelar")
    r1 = o.post("/api/subscription/cancel")
    c1 = r1.json()["restaurant"]["cancel_requested_at"]
    check(r1.status_code == 200 and c1 and r1.json()["active"], "cancelar: queda registrado y sigue activa hasta que termine lo pagado")
    check(o.post("/api/subscription/cancel").json()["restaurant"]["cancel_requested_at"] == c1, "pedirlo otra vez no cambia nada")
    check(o.get("/api/menu").json()["categories"][0]["items"], "la carta sigue ahí")
    listado = next(x for x in o.get("/api/superadmin/restaurants", headers=H).json()["restaurants"] if x["email"] == "s@x.co")
    check(listado["cancel_requested_at"] and listado["paid_until"], "el superusuario ve la cancelación pedida y la fecha")
    act(plan="pro", period_days=30)
    check(me()["restaurant"]["cancel_requested_at"] == "", "volver a activarla borra la cancelación")
    act(plan="pro", no_expiry=True)
    r2 = o.post("/api/subscription/cancel").json()
    check(not r2["active"] and r2["restaurant"]["subscription_status"] == "inactive", "sin fecha de vencimiento no hay periodo que respetar: pasa a Gratis de inmediato")
    check(o.post("/api/subscription/cancel").status_code == 400, "sin suscripción activa no hay nada que cancelar")
    check(o.get("/api/menu").json()["categories"][0]["items"], "y la carta sigue intacta")

    # ---------------- auditoría del superusuario
    check(o.get("/api/superadmin/audit").status_code == 403, "la auditoría exige la clave de administrador")
    n0 = len(sent)
    o.post("/api/superadmin/modules", headers=H, json={"email": "s@x.co", "disabled": ["reviews"]})
    o.post("/api/superadmin/modules", headers=H, json={"email": "s@x.co", "disabled": []})
    o.post("/api/superadmin/set-password", headers=H, json={"email": "s@x.co", "password": "otraclave123"})
    o.post("/api/superadmin/reset-link", headers=H, json={"email": "s@x.co"})
    ev = o.get("/api/superadmin/audit", headers=H).json()["events"]
    acc = [e["action"] for e in ev]
    check({"activate", "modules", "set-password", "reset-link"} <= set(acc), f"queda constancia de activar, funciones, clave y enlace {sorted(set(acc))}")
    check(all(e["email"] == "s@x.co" and e["ip"] and e["created_at"] for e in ev), "cada registro trae cuenta, IP y hora")
    check(any("apagadas: reviews" in e["detail"] for e in ev) and any(e["action"] == "activate" and "vence" in e["detail"] for e in ev), "y el detalle de lo que se cambió")
    check(ev[0]["id"] > ev[-1]["id"], "del más reciente al más antiguo")
    check(len(sent) - n0 == 2 and all(t == "s@x.co" for t, _ in sent[n0:]), "al dueño le llega un aviso cuando cambian su clave o generan un enlace")
    check(o.post("/api/superadmin/set-password", headers=H, json={"email": "no@x.co", "password": "otraclave123"}).status_code == 404 and len(sent) - n0 == 2, "una cuenta inexistente no genera aviso")

    # ---------------- pedidos idempotentes: reintentar tras perder la señal no duplica
    act(plan="pro", period_days=30)
    a = pedir("2", request_id="intento-1")
    b = pedir("2", request_id="intento-1")
    check(a.status_code == 200 and b.status_code == 200 and a.json()["order_id"] == b.json()["order_id"] and b.json().get("duplicate"), "el mismo intento devuelve el mismo pedido")
    check(db.row("SELECT COUNT(*) n FROM orders WHERE table_label='2' AND client_ref='intento-1'")["n"] == 1, "y en cocina hay UN solo pedido")
    c = pedir("2", request_id="intento-2")
    check(c.json()["order_id"] != a.json()["order_id"] and not c.json().get("duplicate"), "otro intento (otro carrito) sí crea otro pedido")
    d = pedir("3", request_id="intento-1")
    check(d.json()["order_id"] != a.json()["order_id"], "el mismo id en otra mesa no se confunde")
    e1, e2 = pedir("4"), pedir("4")
    check(e1.json()["order_id"] != e2.json()["order_id"], "sin request_id (versiones viejas del celular) cada envío es un pedido, como antes")
    bad = pedir("2", request_id="x" * 65)
    check(bad.status_code == 422 and bad.json() == {"error": "Revisa los datos ingresados"}, "un request_id demasiado largo se rechaza, sin mostrar la estructura interna de FastAPI")

print("Suscripciones y auditoría ✔")
