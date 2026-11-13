"""Resumen: pedidos por mesa, con su contenido y valor, filtrables por mesa y fechas.   python -m tests.test_history"""
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as o, TestClient(app) as kit, TestClient(app) as cust:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Café Historial", "email": "h@x.co", "password": "secreto123", "tables": 3}).json()
    slug, pin = me["restaurant"]["slug"], me["restaurant"]["staff_pin"]
    cat = o.post("/api/categories", json={"name": "Platos"}).json()["id"]
    cafe = o.post("/api/items", json={"category_id": cat, "name": "Café", "price": 5000}).json()["id"]
    pan = o.post("/api/items", json={"category_id": cat, "name": "Pan", "price": 3000}).json()["id"]
    tabs = {t["label"]: t for t in o.get("/api/tables").json()["tables"]}
    base = f"/api/public/{slug}"
    kit.post("/api/staff-login", json={"slug": slug, "pin": pin})

    def order(label, items, who="Ana", note=""):
        t = tabs[label]
        r = cust.post(f"{base}/orders", json={"table": label, "key": t["secret"], "diner_id": "d" + label + who, "diner_name": who, "note": note, "items": [{"item_id": i, "qty": q} for i, q in items]})
        check(r.status_code == 200, f"pedido en mesa {label}")
        return r.json()["order_id"]

    o1 = order("1", [(cafe, 2), (pan, 1)], "Ana", "sin azúcar")   # 13.000
    o2 = order("1", [(cafe, 1)], "Beto")                          # 5.000
    o3 = order("2", [(pan, 3)], "Cami")                           # 9.000
    pl = o.post("/api/takeaway", json={"enabled": True}).json()["takeaway_url"].split("pl=")[1]
    s = cust.post(f"{base}/takeaway/start", json={"pl": pl}).json()
    cust.post(f"{base}/orders", json={"table": s["table"], "key": s["key"], "diner_id": "x", "diner_name": "Dani", "items": [{"item_id": cafe, "qty": 1}]})  # 5.000 para llevar
    kit.post(f"/api/orders/{o2}/status", json={"status": "cancelled"})

    h = o.get("/api/orders/history").json()
    check(h["count"] == 3 and h["total"] == 13000 + 9000 + 5000, "sin filtros: 3 pedidos y $27.000 (el cancelado no cuenta)")
    check([(t["label"], t["orders"], t["total"]) for t in h["tables"]] == [("Mesa 1", 1, 13000), ("Mesa 2", 1, 9000), ("Para llevar", 1, 5000)], "cantidad de pedidos y valor por mesa, con «Para llevar» al final")
    check(len(h["orders"]) == 4 and h["orders"][0]["id"] > h["orders"][-1]["id"], "la lista trae todos, el más reciente primero (incluye el cancelado)")
    m1 = o.get("/api/orders/history", params={"table": "1"}).json()
    check(m1["count"] == 1 and len(m1["orders"]) == 2 and {x["id"] for x in m1["orders"]} == {o1, o2}, "filtrar por la mesa 1 muestra solo sus pedidos")
    ped = next(x for x in m1["orders"] if x["id"] == o1)
    check(ped["total"] == 13000 and ped["diner_name"] == "Ana" and ped["note"] == "sin azúcar" and ped["status"] == "new"
          and [(i["name"], i["qty"], i["unit_price"], i["line_total"]) for i in ped["items"]] == [("Café", 2, 5000, 10000), ("Pan", 1, 3000, 3000)], "cada pedido trae su contenido, cantidades, valor por línea y total")
    check(next(x for x in m1["orders"] if x["id"] == o2)["status"] == "cancelled", "y se ve cuál fue cancelado")
    check(len(o.get("/api/orders/history", params={"table": "PL"}).json()["orders"]) == 1 and o.get("/api/orders/history", params={"table": "PL"}).json()["orders"][0]["takeaway"], "«PL» filtra los pedidos para llevar")
    check(o.get("/api/orders/history", params={"table": "9"}).json()["orders"] == [], "una mesa sin pedidos sale vacía")
    check(h["tables"] == o.get("/api/orders/history", params={"table": "2"}).json()["tables"], "el resumen por mesa no cambia al filtrar")

    today = (datetime.utcnow() - timedelta(hours=5)).strftime("%Y-%m-%d")  # hora de Colombia (zona del negocio por defecto)
    yday = (datetime.utcnow() - timedelta(days=1, hours=5)).strftime("%Y-%m-%d")
    check(o.get("/api/orders/history", params={"from": yday, "to": yday}).json()["orders"] == [], "un rango de ayer no trae los pedidos de hoy")
    check(o.get("/api/orders/history", params={"from": today, "to": today}).json()["count"] == 3, "y uno de hoy sí")
    db.run("UPDATE orders SET created_at=? WHERE id=?", ((datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"), o3))
    check(o.get("/api/orders/history", params={"from": today, "to": today}).json()["count"] == 2, "un pedido de hace 5 días queda fuera del rango de hoy")
    check(o.get("/api/orders/history").json()["count"] == 3, "pero entra en los últimos 7 días (por defecto)")
    check(o.get("/api/orders/history", params={"from": "ayer"}).status_code == 400 and o.get("/api/orders/history", params={"from": today, "to": yday}).status_code == 400
          and o.get("/api/orders/history", params={"from": "2020-01-01", "to": today}).status_code == 400, "fechas mal escritas, invertidas o de más de 93 días se rechazan")
    check(kit.get("/api/orders/history").status_code == 403 and cust.get("/api/orders/history").status_code == 401, "solo el dueño lo ve (ni la cocina ni los clientes)")

    csv_all = o.get("/api/export/orders.csv").text
    csv_m2 = o.get("/api/export/orders.csv", params={"from": yday, "to": today, "table": "1"}).text
    import csv as _csv
    import io as _io
    mesas = lambda txt: {r[2] for r in list(_csv.reader(_io.StringIO(txt.lstrip("﻿"))))[1:]}  # noqa: E731
    check(mesas(csv_all) >= {"1", "2"} and mesas(csv_m2) == {"1"}, "el CSV exporta lo filtrado (mesa y fechas); sin filtros, todo")
    o.post("/api/superadmin/modules", headers={"x-admin-key": "k"}, json={"email": "h@x.co", "disabled": ["home"]})
    check(o.get("/api/orders/history").status_code == 403, "si el superusuario apaga «Resumen», el historial también se cierra")

print("Historial de pedidos ✔")
