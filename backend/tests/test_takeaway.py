"""Para llevar (un QR, máximo 10 pedidos en curso) y funciones del panel que el superusuario enciende o apaga.
python -m tests.test_takeaway"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

H = {"x-admin-key": "k"}


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


with TestClient(app) as o, TestClient(app) as cust, TestClient(app) as kit:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Postres Luna", "email": "p@x.co", "password": "secreto123", "tables": 2}).json()
    slug, pin = me["restaurant"]["slug"], me["restaurant"]["staff_pin"]
    cat = o.post("/api/categories", json={"name": "Postres"}).json()["id"]
    item = o.post("/api/items", json={"category_id": cat, "name": "Brownie", "price": 8000}).json()["id"]
    base = f"/api/public/{slug}"
    mod = lambda **b: o.post("/api/superadmin/modules", headers=H, json={"email": "p@x.co", **b})  # noqa: E731

    # ---------------- funciones del panel
    check(all(me["modules"].values()) and set(me["modules"]) == {"home", "menu", "tables", "reviews", "customers", "assistant", "settings", "takeaway"},
          "una cuenta nueva tiene las 8 funciones encendidas")
    check(o.post("/api/superadmin/modules", json={"email": "p@x.co", "disabled": []}).status_code == 403, "cambiar funciones exige la clave de administrador")
    check(mod(disabled=["nada"]).status_code == 400, "una función que no existe se rechaza")
    check(o.post("/api/superadmin/modules", headers=H, json={"email": "x@x.co", "disabled": []}).status_code == 404, "correo inexistente: 404")
    check(mod(disabled=["customers", "reviews", "assistant", "home", "settings", "menu", "tables"]).status_code == 200, "el superusuario apaga funciones")
    listed = next(r for r in o.get("/api/superadmin/restaurants", headers=H).json()["restaurants"] if r["email"] == "p@x.co")
    check(set(listed["disabled_modules"]) == {"customers", "reviews", "assistant", "home", "settings", "menu", "tables"}, "la lista del superusuario muestra lo apagado")
    m = o.get("/api/me").json()["modules"]
    check(m["takeaway"] and not any(m[k] for k in ("customers", "reviews", "assistant", "home", "settings", "menu", "tables")), "el panel del dueño recibe qué funciones tiene")
    gated = [("get", "/api/customers"), ("post", "/api/customers"), ("get", "/api/customers.xlsx"), ("get", "/api/feedback"), ("post", "/api/assistant"),
             ("get", "/api/analytics"), ("put", "/api/settings"), ("post", "/api/categories"), ("post", "/api/items"), ("post", "/api/import/text"),
             ("delete", "/api/menu"), ("post", "/api/tables"), ("get", "/api/qr/1.svg")]
    bad = [f"{mt} {p}" for mt, p in gated if getattr(o, mt)(p, **({"json": {}} if mt in ("post", "put") else {})).status_code != 403]
    check(not bad, f"el servidor rechaza (403) lo de las funciones apagadas {bad}")
    check(o.get("/api/menu").status_code == 200 and o.get("/api/tables").status_code == 200, "ver la carta y las mesas (lo que usa la sala) sigue funcionando")
    kit.post("/api/staff-login", json={"slug": slug, "pin": pin})
    check(kit.get("/api/orders").status_code == 200 and kit.get("/api/floor").status_code == 200, "la cocina y la sala no se ven afectadas")
    check(kit.post(f"/api/items/{item}/availability", json={"available": False}).status_code == 200, "la cocina todavía puede marcar un plato agotado")
    kit.post(f"/api/items/{item}/availability", json={"available": True})  # (y lo vuelve a habilitar para seguir)
    check(o.get(f"{base}/menu").json()["categories"], "los clientes siguen viendo la carta aunque el panel la tenga apagada")
    check(mod(disabled=[]).status_code == 200 and o.get("/api/customers").status_code == 200, "al volver a encenderlas funcionan de nuevo")

    # ---------------- para llevar
    check(cust.post(f"{base}/takeaway/start", json={"pl": "x"}).status_code == 403, "sin activar, el QR para llevar no sirve")
    r = o.post("/api/takeaway", json={"enabled": True}).json()
    url = r["takeaway_url"]
    check(r["restaurant"]["takeaway"] == 1 and "?pl=" in url and r["takeaway_max"] == 10, "el dueño activa para llevar y recibe su QR")
    check(o.get("/api/qr/takeaway.svg").status_code == 200 and "svg" in o.get("/api/qr/takeaway.svg").headers["content-type"], "el QR para llevar se genera")
    pl = url.split("pl=")[1]
    check(cust.post(f"{base}/takeaway/start", json={"pl": "mala"}).status_code == 403, "una clave equivocada no entra")
    s1 = cust.post(f"{base}/takeaway/start", json={"pl": pl}).json()
    check(s1["table"].startswith("PL-") and s1["key"], "el QR da a cada cliente su propia «mesa» para llevar")
    check(cust.get(f"{base}/menu", params={"t": s1["table"], "k": s1["key"]}).json()["can_order"] is True, "con ese código puede pedir")
    check(cust.get(f"{base}/menu", params={"t": s1["table"], "k": "falsa"}).json()["table_ok"] is False, "una clave falsa no sirve")

    def order(sess, name="Ana", cl=cust):
        return cl.post(f"{base}/orders", json={"table": sess["table"], "key": sess["key"], "diner_id": "d-" + sess["table"], "diner_name": name,
                                                "items": [{"item_id": item, "qty": 1}]})
    check(order(s1, "").status_code == 400, "para llevar exige el nombre del cliente")
    _r = order(s1)
    check(_r.status_code == 200, "el primer pedido para llevar entra " + _r.text)
    check(cust.post(f"{base}/call", json={"table": s1["table"], "key": s1["key"], "type": "waiter"}).status_code == 400, "no hay mesero que llamar en un pedido para llevar")

    sess = [s1]
    for i in range(9):
        db.run("DELETE FROM rate_hits")
        s = cust.post(f"{base}/takeaway/start", json={"pl": pl}).json()
        sess.append(s)
        check(order(s, f"Cliente {i}").status_code == 200, f"pedido para llevar {i + 2} de 10") if i in (0, 8) else order(s, f"Cliente {i}")
    st = cust.get(f"{base}/bill", params={"table": s1["table"], "k": s1["key"]}).json()["takeaway"]
    check(st == {"active": 10, "max": 10, "full": True}, "con 10 pedidos en curso el cupo aparece lleno")
    db.run("DELETE FROM rate_hits")
    extra = cust.post(f"{base}/takeaway/start", json={"pl": pl}).json()
    r = order(extra, "Once")
    check(r.status_code == 409 and "tope" in r.json()["error"], "el pedido 11 se rechaza mientras haya 10 en curso")
    check(cust.get(f"{base}/bill", params={"table": extra["table"], "k": extra["key"]}).json()["lines"] == [], "el pedido rechazado no se guardó")
    check(db.row("SELECT COUNT(*) n FROM orders WHERE restaurant_id=1")["n"] == 10, "siguen siendo 10 pedidos")

    # un cliente no ve los pedidos de otro
    mine = cust.get(f"{base}/bill", params={"table": s1["table"], "k": s1["key"]}).json()["lines"]
    check(len(mine) == 1 and mine[0]["diner_name"] == "Ana", "cada cliente solo ve su propio pedido")

    # cocina: avanzar y entregar libera un cupo (entra el siguiente)
    oid = next(x["id"] for x in kit.get("/api/orders").json()["orders"] if x["table_label"] == s1["table"])
    for stt in ("preparing", "ready"):
        kit.post(f"/api/orders/{oid}/status", json={"status": stt})
    check(cust.get(f"{base}/bill", params={"table": extra["table"], "k": extra["key"]}).json()["takeaway"]["full"] is True, "listo para recoger todavía ocupa el cupo")
    kit.post(f"/api/orders/{oid}/status", json={"status": "served"})
    check(cust.get(f"{base}/bill", params={"table": extra["table"], "k": extra["key"]}).json()["takeaway"] == {"active": 9, "max": 10, "full": False},
          "al entregar un pedido se libera un cupo")
    check(order(extra, "Once").status_code == 200, "y entra el pedido que estaba esperando")
    check(order(sess[1], "Otro").status_code == 409, "con 10 de nuevo, el siguiente espera")
    kit.post(f"/api/orders/{oid}/status", json={"status": "cancelled"})  # cancelar un pedido ya entregado no cambia nada
    oid2 = next(x["id"] for x in kit.get("/api/orders").json()["orders"] if x["table_label"] == sess[1]["table"])
    kit.post(f"/api/orders/{oid2}/status", json={"status": "cancelled"})
    check(order(sess[2], "Otro").status_code == 200, "un pedido cancelado también libera su cupo")

    # los pedidos de mesa no cuentan para el tope y los de llevar no tocan las mesas
    t = o.get("/api/tables").json()["tables"][0]
    check(cust.post(f"{base}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": "m1", "items": [{"item_id": item, "qty": 1}]}).status_code == 200,
          "los pedidos de mesa no cuentan para el tope de para llevar")
    check(all(x["orders"] == [] for x in kit.get("/api/floor").json()["tables"] if x["label"] != t["label"]), "la sala no muestra pedidos para llevar como mesas")
    rep = o.get("/api/analytics").json()
    check(sum(1 for x in rep["top_tables"] if x["table"].startswith("PL-")) == 0 and any(x["table"] == "Para llevar" for x in rep["top_tables"]),
          "el reporte junta lo de para llevar en un solo renglón")

    # apagar la función o el QR corta el acceso
    check(mod(disabled=["takeaway"]).status_code == 200, "el superusuario apaga «Para llevar»")
    check(cust.post(f"{base}/takeaway/start", json={"pl": pl}).status_code == 403, "con la función apagada nadie puede iniciar un pedido para llevar")
    check(order(sess[2], "X").status_code == 403, "ni seguir pidiendo con un código que ya tenía")
    check(o.post("/api/takeaway", json={"enabled": True}).status_code == 403, "el dueño tampoco puede volver a activarla")
    mod(disabled=[])
    old = pl
    pl = o.post("/api/takeaway", json={"enabled": True, "rotate": True}).json()["takeaway_url"].split("pl=")[1]
    check(pl != old and cust.post(f"{base}/takeaway/start", json={"pl": old}).status_code == 403, "renovar el QR invalida el impreso")
    check(order(sess[2], "Y").status_code == 403, "y los códigos de clientes del QR anterior dejan de valer")
    o.post("/api/takeaway", json={"enabled": False})
    check(cust.post(f"{base}/takeaway/start", json={"pl": pl}).status_code == 403, "apagado por el dueño: no entran pedidos")

print("\nTodo OK")
