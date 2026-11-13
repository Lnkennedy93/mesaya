"""Registro de clientes fidelizados por QR, y pago con QR (Bre-B / Nequi) en los pedidos para llevar.
python -m tests.test_loyalty_qr"""
import io
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(b, "PNG")
    return b.getvalue()


with TestClient(app) as o, TestClient(app) as o2, TestClient(app) as cust, TestClient(app) as kit:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Fidelidad SAS", "email": "f@x.co", "password": "secreto123", "tables": 2}).json()
    slug, pin = me["restaurant"]["slug"], me["restaurant"]["staff_pin"]
    other = o2.post("/api/signup", json={"accept_terms": True, "name": "Otro Local", "email": "g@x.co", "password": "secreto123", "tables": 1}).json()["restaurant"]["slug"]
    base = f"/api/public/{slug}"
    form = {"document": "1.020.304.050", "name": "  Ana   María  Pérez ", "email": "ANA@Correo.co", "phone": "300 123 4567", "consent": True}

    # ---------------- registro de clientes por QR
    check(o.get("/api/customers/qr").json() == {"url": "", "card_url": ""}, "al inicio no hay QR de registro ni de «ver mi tarjeta»")
    check(cust.post(f"{base}/customers/signup", json={"k": "x", **form}).status_code == 403, "sin QR generado, nadie se puede registrar")
    url = o.post("/api/customers/qr", json={}).json()["url"]
    check(f"/r/{slug}/registro?k=" in url, "el dueño genera el QR de registro")
    k = url.split("k=")[1]
    check(o.post("/api/customers/qr", json={}).json()["url"] == url, "pedirlo otra vez no lo cambia")
    svg = o.get("/api/qr/customers.svg")
    check(svg.status_code == 200 and "svg" in svg.headers["content-type"], "el QR se dibuja")
    check(kit.get("/api/qr/customers.svg").status_code == 401, "sin sesión de dueño no se ve")
    info = cust.get(f"{base}/customers/signup", params={"k": k})
    check(info.status_code == 200 and info.json()["name"] == "Fidelidad SAS", "al escanear, el cliente ve el nombre del restaurante")
    check(cust.get(f"{base}/customers/signup", params={"k": "mala"}).status_code == 403, "una clave equivocada no entra")
    check(cust.post(f"{base}/customers/signup", json={"k": "mala", **form}).status_code == 403, "ni registra con una clave equivocada")
    check(cust.post(f"{base}/customers/signup", json={"k": k, **{**form, "consent": False}}).status_code == 400, "sin autorizar el tratamiento de datos no se guarda")
    check(cust.post(f"{base}/customers/signup", json={"k": k, **{**form, "document": "12"}}).status_code == 400
          and cust.post(f"{base}/customers/signup", json={"k": k, **{**form, "email": "x"}}).status_code == 400
          and cust.post(f"{base}/customers/signup", json={"k": k, **{**form, "phone": "abc"}}).status_code == 400, "cédula, correo y celular se validan")
    check(o.get("/api/customers").json()["customers"] == [], "lo rechazado no queda guardado")
    check(cust.post(f"{base}/customers/signup", json={"k": k, **form}).status_code == 200, "el cliente se registra solo")
    rows = o.get("/api/customers").json()["customers"]
    check(len(rows) == 1 and rows[0]["document"] == "1020304050" and rows[0]["name"] == "Ana María Pérez" and rows[0]["email"] == "ana@correo.co" and rows[0]["phone"] == "3001234567",
          "queda en la fidelización del dueño, con los datos ordenados")
    check(cust.post(f"{base}/customers/signup", json={"k": k, **{**form, "name": "Otro Nombre"}}).status_code == 200 and len(o.get("/api/customers").json()["customers"]) == 1,
          "registrarse dos veces no duplica ni revela que ya existía")
    check(o2.get("/api/customers").json()["customers"] == [], "la base de otro restaurante no recibe nada")
    check(cust.post(f"/api/public/{other}/customers/signup", json={"k": k, **form}).status_code == 403, "la clave de un restaurante no sirve en otro")
    check(o.post("/api/customers/qr", json={"rotate": True}).json()["url"] != url and cust.get(f"{base}/customers/signup", params={"k": k}).status_code == 403, "renovar el QR invalida el impreso")
    db.run("DELETE FROM rate_hits")

    # ---------------- para llevar: método de pago y pago con QR
    cat = o.post("/api/categories", json={"name": "Postres"}).json()["id"]
    item = o.post("/api/items", json={"category_id": cat, "name": "Brownie", "price": 8000}).json()["id"]
    pl = o.post("/api/takeaway", json={"enabled": True}).json()["takeaway_url"].split("pl=")[1]
    s1 = cust.post(f"{base}/takeaway/start", json={"pl": pl}).json()
    call = lambda **b: cust.post(f"{base}/call", json={"table": s1["table"], "key": s1["key"], "type": "bill", **b})  # noqa: E731
    check(call(method="cash").status_code == 400, "sin pedidos no hay nada que pagar")
    cust.post(f"{base}/orders", json={"table": s1["table"], "key": s1["key"], "diner_id": "d1", "diner_name": "Luz", "items": [{"item_id": item, "qty": 2}]})
    check(call().status_code == 400 and call(method="bitcoin").status_code == 400, "hay que elegir cómo se paga")
    check(call(method="qr").status_code == 400, "sin QR subido no se puede elegir «QR»")
    check(o.post("/api/pay-qr", files={"file": ("qr.png", png(), "image/png")}).status_code == 200, "el dueño sube su QR de cobro")
    check(call(method="qr").status_code == 400, "con el QR subido pero el pago ágil apagado en «Para llevar», tampoco")
    m = cust.get(f"{base}/menu", params={"t": s1["table"], "k": s1["key"]}).json()["restaurant"]
    check(m["pay_qr"] and m["takeaway_qr"] is False, "la carta para llevar no ofrece el QR mientras esté apagado")
    check(o.put("/api/settings", json={"takeaway_qr": 1}).json()["restaurant"]["takeaway_qr"] == 1, "el dueño habilita el pago ágil con QR")
    m = cust.get(f"{base}/menu", params={"t": s1["table"], "k": s1["key"]}).json()["restaurant"]
    check(m["takeaway_qr"] is True, "ahora la carta para llevar lo ofrece")
    check(call(method="card").status_code == 200, "el cliente avisa que pagará con datáfono")
    kit.post("/api/staff-login", json={"slug": slug, "pin": pin})
    check([(x["table_label"], x["method"]) for x in kit.get("/api/calls").json()["calls"]] == [(s1["table"], "card")], "cocina/sala ve el aviso de ese pedido para llevar")
    db.run("DELETE FROM rate_hits")  # (el tope de avisos por mesa es por 5 minutos)
    _q = call(method="qr")
    check(_q.status_code == 200 and [x["method"] for x in kit.get("/api/calls").json()["calls"]] == ["qr"], "cambia a «QR» sin duplicar el aviso")
    check(cust.post(f"{base}/call", json={"table": s1["table"], "key": s1["key"], "type": "waiter"}).status_code == 400, "seguir sin mesero que llamar en para llevar")
    check(kit.post(f"/api/floor/{s1['table']}/settle", json={"method": "qr"}).status_code == 200 and kit.get("/api/calls").json()["calls"] == [], "el mostrador revisa el comprobante y cobra «por QR»")
    db.run("DELETE FROM rate_hits")
    check(call(method="cash").status_code in (400, 409), "ya pagado, no hay nada más que pagar")
    check(o.put("/api/settings", json={"takeaway_qr": 0}).status_code == 200, "el dueño apaga el pago ágil")

print("Fidelización por QR y para llevar ✔")
