"""Prueba de humo del flujo completo:  python -m tests.test_flow
(usa una base de datos temporal, no toca la tuya)"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"
os.environ["MESAYA_DEMO"] = "1"
os.environ["MESAYA_ONLINE_PAYMENTS"] = "1"
os.environ["MESAYA_INVOICING"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as c:
    # registro con prueba gratis
    r = c.post("/api/signup", json={"accept_terms": True, "name": "Café Prueba", "email": "a@b.co", "password": "secreto123", "tables": 3})
    check(r.status_code == 200 and r.json()["trial_days_left"] >= 13, "signup + 14 días de prueba sin tarjeta")
    slug = r.json()["restaurant"]["slug"]
    check(c.post("/api/signup", json={"accept_terms": True, "name": "Otro", "email": "a@b.co", "password": "secreto123"}).status_code == 409,
          "correo duplicado rechazado")

    # importar carta desde texto
    txt = "# Entradas\nEmpanadas - 8.000 - Rellenas de carne\nPapas criollas | 12000\nBEBIDAS\nLimonada 6.500\n"
    draft = c.post("/api/import/text", json={"text": txt}).json()
    check(len(draft["categories"]) == 2 and draft["categories"][0]["items"][0]["price"] == 8000, "importador de texto")
    check(c.post("/api/import/commit", json=draft).json()["added"] == 3, "carta importada")
    menu = c.get("/api/menu").json()["categories"]
    emp = menu[0]["items"][0]

    # opciones con recargo
    c.put(f"/api/items/{emp['id']}", json={
        "category_id": menu[0]["id"], "name": "Empanadas", "price": 8000,
        "options": [{"name": "Tamaño", "required": True, "multi": False,
                     "options": [{"name": "x6", "price": 0}, {"name": "x12", "price": 7000}]}]})

    tables = c.get("/api/tables").json()["tables"]
    t = tables[0]
    pub = c.get(f"/api/public/{slug}/menu", params={"t": t["label"], "k": t["secret"]}).json()
    check(pub["can_order"], "QR de mesa válido permite pedir")
    check(not c.get(f"/api/public/{slug}/menu", params={"t": t["label"], "k": "malo"}).json()["can_order"],
          "QR con código falso no permite pedir")

    base = f"/api/public/{slug}"
    order = {"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana",
             "items": [{"item_id": emp["id"], "qty": 2, "options": [{"group": "Tamaño", "name": "x12"}]}]}
    check(c.post(f"{base}/orders", json={**order, "items": [{"item_id": emp["id"], "qty": 1}]}).status_code == 400,
          "opción obligatoria exigida")
    check(c.post(f"{base}/orders", json={**order, "key": "zzz"}).status_code == 403, "pedido con llave falsa rechazado")
    check(c.post(f"{base}/orders", json=order).status_code == 200, "pedido creado")

    # el precio lo calcula el servidor
    bill = c.get(f"{base}/bill", params={"table": t["label"], "k": t["secret"]}).json()["lines"]
    check(bill[0]["unit_price"] == 15000 and bill[0]["line_total"] == 30000, "precio con extras calculado en servidor")

    # cocina
    c.post("/api/logout")
    check(c.get("/api/orders").status_code == 401, "cocina exige sesión")
    me = c.post("/api/login", json={"email": "a@b.co", "password": "secreto123"}).json()
    c.post("/api/logout")
    check(c.post("/api/staff-login", json={"slug": slug, "pin": "0000x"}).status_code == 401, "PIN incorrecto")
    check(c.post("/api/staff-login", json={"slug": slug, "pin": me["restaurant"]["staff_pin"]}).status_code == 200,
          "cocina entra con PIN")
    orders = c.get("/api/orders").json()["orders"]
    check(len(orders) == 1 and orders[0]["table_label"] == t["label"], "pedido aparece en cocina con número de mesa")
    oid = orders[0]["id"]
    check(c.post(f"/api/orders/{oid}/status", json={"status": "preparing"}).status_code == 200, "→ en preparación")
    check(c.post("/api/settings", json={}).status_code == 405 and c.put("/api/settings", json={"name": "x"}).status_code == 403,
          "cocina no puede cambiar ajustes")

    # apagar agotado
    c.post(f"/api/items/{emp['id']}/availability", json={"available": False})
    r = c.post(f"{base}/orders", json=order)
    check(r.status_code == 409, "plato agotado no se puede pedir")
    c.post(f"/api/items/{emp['id']}/availability", json={"available": True})
    c.post(f"/api/orders/{oid}/status", json={"status": "ready"})

    # pago dividido: cada uno paga lo suyo
    c.post(f"{base}/orders", json={**order, "diner_id": "d2", "diner_name": "Luis", "items": [{"item_id": menu[1]["items"][0]["id"], "qty": 1}]})
    lines = c.get(f"{base}/bill", params={"table": t["label"], "k": t["secret"]}).json()["lines"]
    mine = [l["id"] for l in lines if l["diner_id"] == "d1"]
    r = c.post(f"{base}/pay", json={"table": t["label"], "key": t["secret"], "item_ids": mine, "tip_pct": 10, "provider": "mock"})
    check(r.status_code == 200 and r.json()["tip"] == 3000 and r.json()["total"] == 33000, "Ana paga lo suyo con propina")
    r = c.post(f"{base}/pay", json={"table": t["label"], "key": t["secret"], "item_ids": mine, "provider": "mock"})
    check(r.status_code == 409, "no se puede pagar dos veces lo mismo")
    lines = c.get(f"{base}/bill", params={"table": t["label"], "k": t["secret"]}).json()["lines"]
    check(sorted(l["state"] for l in lines) == ["paid", "unpaid"], "la cuenta muestra PAGADO / pendiente")
    st = c.post(f"/api/floor/{t['label']}/settle", json={"method": "cash"}).json()
    check(st["total"] > 0, "caja cobra lo restante")

    # llamadas
    check(c.post(f"{base}/call", json={"table": t["label"], "key": t["secret"], "type": "waiter"}).status_code == 200, "llamar mesero")
    check(len(c.get("/api/calls").json()["calls"]) == 1, "la llamada llega al panel")

    # reportes (dueño)
    c.post("/api/logout")
    c.post("/api/login", json={"email": "a@b.co", "password": "secreto123"})
    a = c.get("/api/analytics?days=7").json()
    check(a["orders"] == 2 and a["sales"] == 30000 + menu[1]["items"][0]["price"], "analítica de ventas")
    check(c.get("/api/export/orders.csv").text.count("\n") >= 3, "export CSV")
    qr = c.get(f"/api/qr/{t['id']}.svg")
    check(qr.status_code == 200 and b"<svg" in qr.content, "QR por mesa en SVG")

    # límites de plan y backoffice
    check(c.post("/api/tables", json={"count": 50}).status_code == 402, "límite de mesas del plan")
    check(c.get("/api/superadmin/restaurants").status_code == 403, "backoffice protegido")
    check(c.post("/api/superadmin/activate", json={"email": "a@b.co", "plan": "pro"}, headers={"x-admin-key": "k"}).status_code == 200,
          "activar suscripción")
    check(c.get("/api/me").json()["plan"]["name"] == "Pro", "plan Pro activo")

print("\nTodo bien ✔")
