"""Fase 2 de la auditoría: cobro atómico, cuentas abandonadas, validaciones, transiciones de estado y auditoría de cancelaciones.
python -m tests.test_money"""
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402

from app import db, panel  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


with TestClient(app) as o, TestClient(app) as cust, TestClient(app) as k1, TestClient(app) as k2:
    me = o.post("/api/signup", json={"accept_terms": True, "name": "Cobros SAS", "email": "m@x.co", "password": "secreto123", "tables": 4}).json()
    slug, pin, rid = me["restaurant"]["slug"], me["restaurant"]["staff_pin"], me["restaurant"]["id"]
    base = f"/api/public/{slug}"
    cat = o.post("/api/categories", json={"name": "Platos"}).json()["id"]
    extras = [{"name": "Extras", "required": False, "multi": True, "options": [{"name": "Queso", "price": 1000}, {"name": "Tocino", "price": 2000}]}]
    plato = o.post("/api/items", json={"category_id": cat, "name": "Burger", "price": 10000, "options": extras}).json()["id"]
    sec = {t["label"]: t["secret"] for t in o.get("/api/tables").json()["tables"]}
    for k in (k1, k2):
        k.post("/api/staff-login", json={"slug": slug, "pin": pin})

    def order(label, items, name="Ana"):
        return cust.post(f"{base}/orders", json={"table": label, "key": sec[label], "diner_id": "d1", "diner_name": name, "items": items})

    def line(qty=1, opts=()):
        return {"item_id": plato, "qty": qty, "options": [{"group": "Extras", "name": n} for n in opts]}

    # ---------------- validaciones de pedido
    check(order("1", [line(0)]).status_code == 400, "cantidad 0 se rechaza (antes se convertía en 1)")
    check(order("1", [line(21)]).status_code == 400 and order("1", [line(-1)]).status_code == 400, "cantidad 21 o negativa se rechaza")
    check(order("1", [line(1, ["Queso", "Queso"])]).status_code == 400, "repetir una opción no sube el precio: se rechaza")
    r = order("1", [line(2, ["Queso", "Tocino"])])
    check(r.status_code == 200, "un pedido válido entra")
    check(cust.get(f"{base}/bill", params={"table": "1", "k": sec["1"]}).json()["lines"][0]["unit_price"] == 13000, "el precio con opciones se recalcula en el servidor")
    check(o.post("/api/items", json={"category_id": cat, "name": "Malo", "price": 100, "options": [
        {"name": "G", "options": [{"name": "Desc", "price": -5000}]}]}).status_code == 400, "una opción con precio negativo no se guarda")
    check(o.post("/api/items", json={"category_id": cat, "name": "Malo", "price": 100, "options": [
        {"name": "G", "options": [{"name": "X", "price": "abc"}]}]}).status_code == 400, "una opción con precio no numérico da 400, no 500")

    # ---------------- entradas con caracteres raros y valores inválidos
    check(cust.get(f"{base}/menu", params={"t": "1", "k": "ñ"}).status_code == 200, "una clave de mesa con ñ ya no da 500")
    check(cust.get(f"{base}/bill", params={"table": "1", "k": "ñ"}).status_code == 403, "ni en la cuenta: 403")
    check(TestClient(app).post("/api/staff-login", json={"slug": slug, "pin": "ñññ"}).status_code == 401, "un PIN con ñ da 401, no 500")
    check(cust.post(f"{base}/quote", json={"subtotal": "abc"}).status_code == 400, "cotizar con texto da 400")
    check(cust.post(f"{base}/quote", json={"subtotal": 1000, "tip_pct": "nan"}).status_code == 400, "cotizar con NaN da 400")
    check(cust.post(f"{base}/quote", json={"subtotal": 10000, "tip_pct": 10}).json()["total"] > 10000, "cotizar normal sigue funcionando")
    check(o.put("/api/settings", json={"tax_pct": -100}).status_code == 400, "impuesto -100 se rechaza (dividía por cero)")
    check(o.put("/api/settings", json={"tax_pct": 101}).status_code == 400 and o.put("/api/settings", json={"tip_pct": 90}).status_code == 400, "impuesto y propina fuera de rango")
    check(o.put("/api/settings", json={"tz_offset": 9999}).status_code == 400 and o.put("/api/settings", json={"name": "  "}).status_code == 400, "zona horaria inválida y nombre vacío")
    check(o.put("/api/settings", json={"tax_pct": 8, "accepting_orders": 7}).status_code == 200 and o.get("/api/me").json()["restaurant"]["accepting_orders"] == 1, "un interruptor se guarda como 0/1")
    o.put("/api/settings", json={"tax_pct": 0})

    # ---------------- mesas: etiqueta reservada, cantidades, numeración y tope
    check(o.post("/api/tables", json={"label": "PL-1"}).status_code == 400, "una mesa «PL-…» choca con Para llevar: se rechaza")
    check(o.post("/api/tables", json={"count": "abc"}).status_code == 400, "count no numérico da 400")
    check(o.post("/api/tables", json={"label": "Terraza"}).json()["added"] == 1, "agrega una mesa con nombre")
    check(o.post("/api/tables", json={"count": 2}).json()["added"] == 2, "agrega 2 numeradas")
    labels = sorted(t["label"] for t in o.get("/api/tables").json()["tables"])
    check(labels == ["1", "2", "3", "4", "5", "6", "Terraza"] or len(labels) == 7, f"quedan 7 mesas sin etiquetas repetidas {labels}")
    check(len(set(labels)) == len(labels), "ninguna etiqueta repetida")
    check(o.post("/api/tables", json={"count": 5}).status_code == 402, "pasarse del plan da 402")
    check(len(o.get("/api/tables").json()["tables"]) == 7, "y no agrega ninguna mesa a medias")
    url = panel.table_url({"slug": "s"}, {"label": "A #2&x", "secret": "kk"})
    check("A%20%232%26x" in url and "#" not in url.split("?")[1], "la etiqueta se codifica en el enlace del QR")
    sec = {t["label"]: t["secret"] for t in o.get("/api/tables").json()["tables"]}

    # ---------------- cobro: dos cobros simultáneos no cobran dos veces
    results = []

    def cobrar(cl):
        results.append(cl.post("/api/floor/1/settle", json={"method": "cash"}))

    ths = [threading.Thread(target=cobrar, args=(c,)) for c in (k1, k2)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    n_pagos = db.row("SELECT COUNT(*) n FROM payments WHERE restaurant_id=? AND table_label='1' AND status='paid'", (rid,))["n"]
    check(all(r.status_code == 200 for r in results), "los dos intentos responden 200")
    check(n_pagos == 1, f"solo se registra UN pago aunque se cobre dos veces a la vez ({n_pagos})")
    check(sorted(r.json()["total"] > 0 for r in results) == [False, True], "uno cobra y el otro ve que ya no hay nada por cobrar")
    check(k1.post("/api/floor/1/settle", json={"tip": -5}).status_code == 400 and k1.post("/api/floor/1/settle", json={"tip": "x"}).status_code == 400, "propina negativa o no numérica: 400")

    # ---------------- transiciones de estado y auditoría
    oid = order("2", [line(1)]).json()["order_id"]
    st = lambda i, **b: k1.post(f"/api/orders/{i}/status", json=b)  # noqa: E731
    check(st(oid, status="otro").status_code == 400, "un estado que no existe se rechaza")
    check(st(oid, status="preparing").status_code == 200 and st(oid, status="ready").status_code == 200, "avanza nuevo → preparando → listo")
    n_ev = db.row("SELECT COUNT(*) n FROM order_events WHERE order_id=?", (oid,))["n"]
    check(st(oid, status="ready").status_code == 200 and db.row("SELECT COUNT(*) n FROM order_events WHERE order_id=?", (oid,))["n"] == n_ev, "repetir el mismo estado es inocuo y no ensucia la auditoría")
    check(st(oid, status="served").status_code == 200, "entregado")
    check(st(oid, status="new").status_code == 409 and st(oid, status="preparing").status_code == 409, "un pedido entregado no vuelve a un estado anterior")
    oid2 = order("3", [line(1)]).json()["order_id"]
    check(st(oid2, status="cancelled", reason="el cliente se arrepintió").status_code == 200, "cancela un pedido con motivo")
    ev = db.row("SELECT * FROM order_events WHERE order_id=? AND to_status='cancelled'", (oid2,))
    check(ev and ev["reason"] == "el cliente se arrepintió" and ev["role"] == "staff" and ev["from_status"] == "new", "queda registrado quién (rol), cuándo y por qué")
    check(st(oid2, status="ready").status_code == 409, "un pedido cancelado no se revive")
    oid3 = order("4", [line(1)]).json()["order_id"]
    check(k1.post("/api/floor/4/settle", json={"method": "cash"}).json()["total"] > 0, "se cobra la mesa 4")
    check(st(oid3, status="cancelled").status_code == 409, "un pedido ya cobrado no se puede cancelar (no desaparece la venta)")

    # ---------------- cerrar mesa sin cobrar y mesas con cuenta
    check(o.delete(f"/api/tables/{[t['id'] for t in o.get('/api/tables').json()['tables'] if t['label'] == '2'][0]}").status_code == 409, "no se borra una mesa con cuenta sin cobrar")
    oid4 = order("2", [line(1)]).json()["order_id"]
    check(k1.post("/api/floor/2/void", json={}).status_code == 409, "no se cierra sin cobrar con un pedido en curso")
    st(oid4, status="served")
    r = k1.post("/api/floor/2/void", json={"reason": "se fue sin pagar"})
    check(r.status_code == 200 and r.json()["voided"] == 2, "cierra sin cobrar los pedidos entregados")
    check(k1.get("/api/floor/2").json()["lines"] == [], "la mesa queda sin cuenta")
    ev = db.row("SELECT reason FROM order_events WHERE order_id=? AND to_status='cancelled'", (oid4,))
    check(ev and ev["reason"] == "sin cobrar: se fue sin pagar", "el cierre sin cobro queda auditado con su motivo")
    check(o.delete(f"/api/tables/{[t['id'] for t in o.get('/api/tables').json()['tables'] if t['label'] == '2'][0]}").status_code == 200, "ahora sí se puede borrar la mesa")

    # ---------------- cuentas olvidadas de otro turno
    old = fmt(datetime.now(timezone.utc) - timedelta(hours=30))
    ob = db.run("INSERT INTO orders(restaurant_id,table_label,seq,status,diner_id,diner_name,note,created_at) VALUES (?,?,?,?,?,?,?,?)", (rid, "6", 1, "served", "x", "Viejo", "", old))
    db.run("INSERT INTO order_items(order_id,item_id,name,options_text,note,qty,unit_price) VALUES (?,?,?,?,?,?,?)", (ob, plato, "Burger", "", "", 1, 10000))
    check(cust.get(f"{base}/bill", params={"table": "6", "k": sec["6"]}).json()["lines"] == [], "una cuenta sin cobrar de hace 30 h no aparece en la mesa")
    order("6", [line(1)], name="Nuevo")
    ls = cust.get(f"{base}/bill", params={"table": "6", "k": sec["6"]}).json()["lines"]
    check([l["diner_name"] for l in ls] == ["Nuevo"], "el grupo siguiente solo ve lo suyo")
    check(k1.post("/api/floor/6/settle", json={"method": "cash"}).json()["total"] == 10000, "y el cobro solo incluye lo suyo")

    # ---------------- número de pedido: se reinicia a la medianoche local, no a la UTC
    off = timedelta(minutes=db.row("SELECT tz_offset FROM restaurants WHERE id=?", (rid,))["tz_offset"])
    ls_utc = (datetime.now(timezone.utc) + off).replace(hour=0, minute=0, second=0, microsecond=0) - off
    hoy = db.row("SELECT COALESCE(MAX(seq),0) m FROM orders WHERE restaurant_id=? AND created_at>=?", (rid, fmt(ls_utc)))["m"]
    db.run("INSERT INTO orders(restaurant_id,table_label,seq,status,diner_id,diner_name,note,created_at) VALUES (?,?,?,?,?,?,?,?)", (rid, "7", 90, "served", "x", "Ayer", "", fmt(ls_utc - timedelta(hours=1))))
    check(order("7", [line(1)]).json()["seq"] == hoy + 1, "un pedido de anoche (hora local) no cuenta para el número de hoy")
    db.run("INSERT INTO orders(restaurant_id,table_label,seq,status,diner_id,diner_name,note,created_at) VALUES (?,?,?,?,?,?,?,?)", (rid, "7", 50, "served", "x", "Hoy", "", fmt(ls_utc + timedelta(seconds=1))))
    check(order("7", [line(1)]).json()["seq"] == 51, "uno de hoy (hora local) sí cuenta")

print("Dinero y datos ✔")
