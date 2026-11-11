"""Producto base (pagos y factura APAGADOS): pedir -> cocina -> terminar mesa.   python -m tests.test_core"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
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

    # sala: cuando cocina marca el pedido «Listo», aparece bajo SU mesa hasta que se entregue
    oid = c.get("/api/orders").json()["orders"][0]["id"]
    mesa = lambda: next(x for x in c.get("/api/floor").json()["tables"] if x["label"] == t["label"])  # noqa: E731
    plato = {"name": "Bandeja", "qty": 2, "options_text": "", "note": ""}
    ped = mesa()["orders"]
    check(len(ped) == 1 and ped[0]["id"] == oid and ped[0]["status"] == "new" and ped[0]["items"] == [plato], "sala: el pedido nuevo se desglosa (platos y cantidades) bajo su mesa")
    c.post(f"/api/orders/{oid}/status", json={"status": "preparing"})
    check([o["status"] for o in mesa()["orders"]] == ["preparing"], "sala: mientras se prepara sigue visible con su estado")
    c.post(f"/api/orders/{oid}/status", json={"status": "ready"})
    ped = mesa()["orders"]
    check(len(ped) == 1 and ped[0]["status"] == "ready" and ped[0]["items"] == [plato], "sala: al quedar listo el mismo pedido pasa a «listo» con sus platos")
    check(all(x["orders"] == [] for x in c.get("/api/floor").json()["tables"] if x["label"] != t["label"]), "sala: las otras mesas no reciben el pedido")
    c.post(f"/api/orders/{oid}/status", json={"status": "served"})
    check(mesa()["orders"] == [], "sala: al entregar el pedido desaparece de la mesa")

    for provider in ("mock", "nequi", "breb", "stripe"):
        r = c.post(f"{base}/pay", json={"table": t["label"], "key": t["secret"], "item_ids": [1], "provider": provider})
        check(r.status_code == 400, f"el método «{provider}» no está disponible")

    ask = lambda **kw: c.post(f"{base}/call", json={"table": t["label"], "key": t["secret"], "type": "bill", **kw})  # noqa: E731
    check(ask().status_code == 400 and ask(method="bitcoin").status_code == 400, "pedir la cuenta exige elegir efectivo o tarjeta")
    check(c.get("/api/calls").json()["calls"] == [], "sin método no se crea el aviso")
    check(ask(method="card").status_code == 200, "el cliente toca «Terminar mesa» y elige tarjeta")
    check(c.get(f"{base}/bill", params=q).json()["calls"] == ["bill"], "la carta muestra «cuenta solicitada»")
    check([(x["type"], x["method"]) for x in c.get("/api/calls").json()["calls"]] == [("bill", "card")], "cocina/sala ve la cuenta con «tarjeta» (llevar datáfono)")
    check(ask(method="cash").status_code == 200 and [(x["type"], x["method"]) for x in c.get("/api/calls").json()["calls"]] == [("bill", "cash")], "cambiar a efectivo actualiza el mismo aviso, sin duplicarlo")
    r = c.post(f"{base}/pay", json={"table": t["label"], "key": t["secret"], "item_ids": [1], "provider": "cashier"})
    check(r.status_code == 400, "pagar en caja desde el flujo de pagos también exige el método")
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
    # mesa cerrada en sala: el cliente solo puede opinar; llamar al mesero queda deshabilitado (también en el servidor)
    from app import db as _db
    _db.run("DELETE FROM rate_hits")
    check(c.get(f"{base}/bill", params=q).json()["closed"] is True, "la carta sabe que la mesa está cerrada")
    for tipo in ("waiter", "bill"):
        r = c.post(f"{base}/call", json={"table": t["label"], "key": t["secret"], "type": tipo, "method": "cash"})
        check(r.status_code == 409, f"mesa cerrada: no se puede pedir «{tipo}» ({r.status_code})")
    check(c.get("/api/calls").json()["calls"] == [], "mesa cerrada: no se creó ningún aviso")
    check(c.post(f"{base}/feedback", json={"table": t["label"], "key": t["secret"], "rating": 5, "comment": "Rico"}).status_code == 200, "el cliente puede calificar")
    # un pedido nuevo en esa mesa la reabre sola (el siguiente grupo puede usarla)
    check(c.post(f"{base}/orders", json={**order, "diner_id": "d2"}).status_code == 200, "mesa cerrada: un pedido nuevo se acepta")
    check(c.get(f"{base}/bill", params=q).json()["closed"] is False, "con un pedido nuevo la mesa deja de estar cerrada")
    check(c.post(f"{base}/call", json={"table": t["label"], "key": t["secret"], "type": "waiter"}).status_code == 200, "y el botón de mesero vuelve a funcionar")

print("\nProducto base ✔")
