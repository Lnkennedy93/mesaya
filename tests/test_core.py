"""Producto base (pagos y factura APAGADOS): pedir -> cocina -> terminar mesa.   python -m tests.test_core"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_SECRET_KEY"] = "cFhmZ3N3N2pFb0F4dDJyV2xRR2hQZ3ZtQ0hCQ2ZQZmM="
for k in ("MESAYA_ONLINE_PAYMENTS", "MESAYA_INVOICING", "MESAYA_DEMO"):
    os.environ.pop(k, None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as c:
    me = c.post("/api/signup", json={"accept_terms": True, "name": "Café Simple", "email": "s@s.co", "password": "secreto123", "tables": 2}).json()
    slug = me["restaurant"]["slug"]
    check(me["features"] == {"payments": False, "invoicing": False}, "pagos y factura apagados por defecto")
    cat = c.post("/api/categories", json={"name": "Platos"}).json()["id"]
    item = c.post("/api/items", json={"category_id": cat, "name": "Bandeja", "price": 30000}).json()["id"]
    t = c.get("/api/tables").json()["tables"][0]
    base = f"/api/public/{slug}"
    q = {"table": t["label"], "k": t["secret"]}

    pub = c.get(f"{base}/menu", params={"t": t["label"], "k": t["secret"]}).json()
    check(pub["features"]["payments"] is False and [p["id"] for p in pub["providers"]] == ["cashier"], "la carta no ofrece pagos en línea")
    check(pub["restaurant"]["invoicing"] is False, "sin factura electrónica")

    order = {"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 2}]}
    check(c.post(f"{base}/orders", json=order).status_code == 200, "el cliente hace el pedido")
    c.post("/api/logout")
    pin = c.post("/api/login", json={"email": "s@s.co", "password": "secreto123"}).json()["restaurant"]["staff_pin"]
    check(len(c.get("/api/orders").json()["orders"]) == 1, "el pedido llega a cocina")

    for provider in ("mock", "nequi", "breb", "stripe"):
        r = c.post(f"{base}/pay", json={"table": t["label"], "key": t["secret"], "item_ids": [1], "provider": provider})
        check(r.status_code == 400, f"el método «{provider}» no está disponible")

    check(c.post(f"{base}/call", json={"table": t["label"], "key": t["secret"], "type": "bill"}).status_code == 200, "el cliente toca «Terminar mesa»")
    check(c.get(f"{base}/bill", params=q).json()["calls"] == ["bill"], "la carta muestra «cuenta solicitada»")
    check([x["type"] for x in c.get("/api/calls").json()["calls"]] == ["bill"], "cocina/sala ve el aviso de cuenta")
    tb = next(x for x in c.get("/api/floor").json()["tables"] if x["label"] == t["label"])
    check(tb["unpaid"] == 60000 and "bill" in tb["calls"], "sala muestra la mesa con $60.000 por cobrar")

    c.put("/api/settings", json={"inv_provider": "factus"})
    r = c.post(f"/api/floor/{t['label']}/settle", json={"method": "cash"}).json()
    check(r["total"] == 60000, "el equipo cierra la mesa")
    check(c.get("/api/calls").json()["calls"] == [], "el aviso de cuenta se resuelve solo")
    lines = c.get(f"{base}/bill", params=q).json()["lines"]
    check(all(l["state"] == "paid" for l in lines), "la carta muestra la mesa cerrada")
    check(c.get("/api/invoices").json()["invoices"] == [], "no se genera ninguna factura electrónica")
    tb = next(x for x in c.get("/api/floor").json()["tables"] if x["label"] == t["label"])
    check(tb["unpaid"] == 0, "la mesa queda libre")
    check(c.post(f"{base}/feedback", json={"table": t["label"], "rating": 5, "comment": "Rico"}).status_code == 200, "el cliente puede calificar")

print("\nProducto base ✔")
