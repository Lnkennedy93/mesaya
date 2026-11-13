"""Tarjeta de sellos: programa del dueño, sellos al cobrar con la cédula o con el enlace/QR/NFC personal, y canje del premio.
python -m tests.test_stamps"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as o, TestClient(app) as o2, TestClient(app) as kit, TestClient(app) as cust, TestClient(app) as anon:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Café Sellos", "email": "s@x.co", "password": "secreto123", "tables": 3}).json()
    slug, pin = me["restaurant"]["slug"], me["restaurant"]["staff_pin"]
    other = o2.post("/api/signup", json={"accept_terms": True, "name": "Otro", "email": "z@x.co", "password": "secreto123", "tables": 1}).json()["restaurant"]["slug"]
    base = f"/api/public/{slug}"
    cat = o.post("/api/categories", json={"name": "Platos"}).json()["id"]
    item = o.post("/api/items", json={"category_id": cat, "name": "Café", "price": 5000}).json()["id"]
    t = o.get("/api/tables").json()["tables"][0]
    kit.post("/api/staff-login", json={"slug": slug, "pin": pin})
    k = o.post("/api/customers/qr", json={}).json()["url"].split("k=")[1]
    reg = lambda doc, **kw: anon.post(f"{base}/customers/signup", json={"k": k, "document": doc, "name": "Laura Gómez", "email": "l@c.co", "phone": "3001234567", "consent": True, **kw})  # noqa: E731

    # ---------------- programa apagado
    check(reg("1020304050").json() == {"ok": True}, "con el programa apagado el registro no entrega tarjeta")
    cid = o.get("/api/customers").json()["customers"][0]["id"]
    check(kit.post("/api/loyalty/stamp", json={"document": "1020304050"}).status_code == 400, "no se suman sellos si el programa está apagado")
    check(o.put("/api/settings", json={"stamps_on": 1, "stamps_goal": 1}).status_code == 400 and o.put("/api/settings", json={"stamps_goal": 31}).status_code == 400, "la meta va de 2 a 30 sellos")
    r = o.put("/api/settings", json={"stamps_on": 1, "stamps_goal": 3, "stamps_reward": "  Un   postre gratis "}).json()["restaurant"]
    check(r["stamps_on"] == 1 and r["stamps_goal"] == 3 and r["stamps_reward"] == "Un postre gratis", "el dueño activa la tarjeta: 3 sellos para «Un postre gratis»")
    st = kit.get("/api/me").json()["restaurant"]
    check(st["stamps_on"] == 1 and st["stamps_goal"] == 3, "el equipo también ve el programa")

    # ---------------- enlace personal
    g = reg("2030405060", name="Carlos Ruiz").json()
    check(g["ok"] and g["card"].startswith(f"/r/{slug}/tarjeta?c="), "quien se registra con el programa activo recibe el enlace de su tarjeta")
    key = g["card"].split("c=")[1].split("&")[0]
    check(g["card"].endswith("&nuevo=1"), "el enlace trae la marca de recién registrado (para darle la bienvenida)")
    check(reg("2030405060").json() == {"ok": True}, "registrarse otra vez no devuelve su tarjeta (no se filtra)")
    card = anon.get(f"{base}/loyalty/card", params={"c": key}).json()
    check(card["name"] == "Carlos" and card["stamps"] == 0 and card["goal"] == 3 and card["reward"] == "Un postre gratis" and card["restaurant"]["name"] == "Café Sellos", "la tarjeta muestra solo el primer nombre y su avance")
    check("document" not in card and "email" not in card and "phone" not in card, "y ningún dato personal más")
    check(anon.get(f"{base}/loyalty/card", params={"c": "mala"}).status_code == 404 and anon.get(f"/api/public/{other}/loyalty/card", params={"c": key}).status_code == 404, "una clave falsa o de otro restaurante no abre nada")
    qr = anon.get(f"{base}/loyalty/qr.svg", params={"c": key})
    check(qr.status_code == 200 and "svg" in qr.headers["content-type"], "la tarjeta se puede mostrar como QR")
    check(o.get(f"/api/customers/{cid}/card").json()["url"].count("/tarjeta?c=") == 1, "el dueño obtiene el enlace de un cliente que ya existía")
    check(o.get(f"/api/qr/card/{cid}.svg").status_code == 200 and kit.get(f"/api/qr/card/{cid}.svg").status_code == 403, "y su QR; el equipo no lo pide")

    # ---------------- acceso directo en la pantalla de inicio del celular
    mf = anon.get(f"{base}/loyalty/manifest.webmanifest", params={"c": key})
    m = mf.json()
    check(mf.status_code == 200 and "manifest+json" in mf.headers["content-type"] and m["start_url"] == f"/r/{slug}/tarjeta?c={key}" and m["display"] == "standalone" and "Café Sellos" in m["name"],
          "el acceso directo abre la tarjeta de ESTE cliente, con el nombre del restaurante")
    check([i["sizes"] for i in m["icons"]] == ["192x192", "512x512"], "con íconos de 192 y 512")
    from io import BytesIO  # noqa: E402
    from PIL import Image  # noqa: E402
    ic = anon.get(m["icons"][0]["src"])
    img = Image.open(BytesIO(ic.content))
    check(ic.status_code == 200 and ic.headers["content-type"] == "image/png" and img.size == (192, 192), "el ícono se dibuja (color de marca e inicial del restaurante)")
    check(Image.open(BytesIO(anon.get(f"{base}/loyalty/icon.png", params={"c": key, "s": 512}).content)).size == (512, 512), "y también en 512")
    check(anon.get(f"{base}/loyalty/manifest.webmanifest", params={"c": "mala"}).status_code == 404 and anon.get(f"{base}/loyalty/icon.png", params={"c": "mala"}).status_code == 404, "con una clave falsa no hay acceso directo")

    # ---------------- sellos
    s1 = kit.post("/api/loyalty/stamp", json={"card": key})
    check(s1.status_code == 200 and s1.json()["stamps"] == 1 and s1.json()["ready"] is False, "el equipo escanea la tarjeta y suma un sello")
    check(kit.post("/api/loyalty/stamp", json={"card": key}).status_code == 409, "no se puede sumar otro sello enseguida (una visita, un sello)")
    check(o.post("/api/loyalty/stamp", json={"card": key, "force": True}).status_code == 200 and o.post("/api/loyalty/stamp", json={"card": key, "force": True}).json()["stamps"] == 3, "el dueño puede forzarlo")
    check(kit.post("/api/loyalty/redeem", json={"document": "9999999"}).status_code == 404, "un cliente que no existe no se encuentra")
    look = kit.get("/api/loyalty/lookup", params={"document": "2030405060"}).json()
    check(look["ready"] and look["rewards"] == 1 and look["filled"] == 3, "con 3 sellos la tarjeta queda completa: premio disponible")
    check(anon.post("/api/loyalty/stamp", json={"card": key}).status_code == 401, "sin sesión del equipo no se suma ni se canjea")
    red = kit.post("/api/loyalty/redeem", json={"card": key})
    check(red.status_code == 200 and red.json()["stamps"] == 0 and kit.post("/api/loyalty/redeem", json={"card": key}).status_code == 409, "se canjea el premio y la tarjeta vuelve a cero")

    # ---------------- al cobrar con la cédula
    db.run("DELETE FROM stamp_log")
    cust.post(f"{base}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 1}]})
    done = kit.post(f"/api/floor/{t['label']}/settle", json={"method": "cash", "customer": "1.020.304.050"}).json()
    check(done["ok"] and done["stamp"]["stamps"] == 1 and done["stamp"]["name"] == "Laura Gómez", "al cobrar con la cédula del cliente se le suma el sello")
    cust.post(f"{base}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 1}]})
    again = kit.post(f"/api/floor/{t['label']}/settle", json={"method": "cash", "customer": "1020304050"}).json()
    check(again["ok"] and "ya se le sumó un sello" in again["stamp"]["error"], "otro cobro enseguida: el cobro se hace y el sello se rechaza con su motivo")
    cust.post(f"{base}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 1}]})
    nope = kit.post(f"/api/floor/{t['label']}/settle", json={"method": "cash", "customer": "5555555"}).json()
    check(nope["ok"] and "no está registrado" in nope["stamp"]["error"], "una cédula que no existe no impide el cobro")
    check(next(c for c in o.get("/api/customers").json()["customers"] if c["document"] == "1020304050")["stamps"] == 1, "la lista del dueño muestra los sellos")
    check(o2.get("/api/customers").json()["customers"] == [], "otro restaurante no ve nada de esto")
    o.put("/api/settings", json={"stamps_on": 0})
    check(anon.get(f"{base}/loyalty/card", params={"c": key}).status_code == 404, "apagar el programa cierra las tarjetas")

print("Tarjeta de sellos ✔")
