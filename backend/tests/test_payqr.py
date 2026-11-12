"""Pago por QR (Bre-B o Nequi): el dueño sube su QR, el cliente lo elige al pedir la cuenta y cocina/sala lo ve y cobra.
python -m tests.test_payqr"""
import io
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(b, "PNG")
    return b.getvalue()


with TestClient(app) as o, TestClient(app) as kit, TestClient(app) as cust:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Pago QR", "email": "q@x.co", "password": "secreto123", "tables": 2}).json()
    slug, pin = me["restaurant"]["slug"], me["restaurant"]["staff_pin"]
    check(me["restaurant"]["pay_qr"] == "", "un restaurante nuevo no tiene QR de pago")
    cat = o.post("/api/categories", json={"name": "Platos"}).json()["id"]
    item = o.post("/api/items", json={"category_id": cat, "name": "Bandeja", "price": 30000}).json()["id"]
    t = o.get("/api/tables").json()["tables"][0]
    base = f"/api/public/{slug}"
    cust.post(f"{base}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 2}]})
    ask = lambda **kw: cust.post(f"{base}/call", json={"table": t["label"], "key": t["secret"], "type": "bill", **kw})  # noqa: E731

    check(ask(method="qr").status_code == 400, "sin QR subido, el cliente no puede elegir «QR»")
    check(o.post("/api/pay-qr", files={"file": ("x.txt", b"hola", "text/plain")}).status_code == 400, "un archivo que no es imagen se rechaza")
    up = o.post("/api/pay-qr", files={"file": ("qr.png", png(), "image/png")})
    path = up.json().get("pay_qr", "")
    check(up.status_code == 200 and path, "el dueño sube su QR")
    check(o.get("/api/me").json()["restaurant"]["pay_qr"] == path, "y aparece en sus ajustes")
    check(cust.get(f"{base}/menu", params={"t": t["label"], "k": t["secret"]}).json()["restaurant"]["pay_qr"] == path, "la carta pública lo recibe")
    check(cust.get(path).status_code == 200, "la imagen se puede abrir")

    st = kit.post("/api/staff-login", json={"slug": slug, "pin": pin}).json()["restaurant"]
    check(st["pay_qr"] == path and kit.post("/api/pay-qr", files={"file": ("qr.png", png(), "image/png")}).status_code == 403, "el equipo ve que hay QR pero no puede cambiarlo")

    check(ask(method="qr").status_code == 200, "el cliente pide la cuenta y elige «QR»")
    check([(x["type"], x["method"]) for x in kit.get("/api/calls").json()["calls"]] == [("bill", "qr")], "cocina/sala ve la cuenta como «paga con QR»")
    check(kit.post(f"/api/floor/{t['label']}/settle", json={"method": "qr"}).status_code == 200 and kit.get("/api/calls").json()["calls"] == [], "el mesero revisa el comprobante, cobra «por QR» y la mesa queda cerrada")

    cust.post(f"{base}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 1}]})
    check(o.delete("/api/pay-qr").status_code == 200 and o.get("/api/me").json()["restaurant"]["pay_qr"] == "", "el dueño quita el QR")
    check(ask(method="qr").status_code == 400, "y el cliente ya no puede elegirlo")

print("Pago por QR ✔")
