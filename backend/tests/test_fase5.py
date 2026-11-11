"""Fase 5 de la auditoría: acceso del personal, sesiones, tope de propina y conciliación de pagos.
python -m tests.test_fase5"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"
os.environ["MESAYA_ONLINE_PAYMENTS"] = "1"
os.environ["MESAYA_SECRET_KEY"] = "cFhmZ3N3N2pFb0F4dDJyV2xRR2hQZ3ZtQ0hCQ2ZQZmM="  # solo pruebas

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, db  # noqa: E402
from app.main import app  # noqa: E402

H = {"x-admin-key": "k"}


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def ip(n, p="9"):
    return {"x-forwarded-for": f"{p}.{n}.1.1"}


with TestClient(app) as o, TestClient(app) as cust, TestClient(app) as kit, TestClient(app) as atk:
    me0 = o.post("/api/signup", json={"accept_terms": True, "name": "Acceso SA", "email": "a@x.co", "password": "secreto123", "tables": 4}).json()
    r0 = me0["restaurant"]
    slug, pin = r0["slug"], r0["staff_pin"]
    base = f"/api/public/{slug}"
    check(len(pin) == 6 and pin.isdigit(), "el PIN nuevo tiene 6 dígitos")
    cat = o.post("/api/categories", json={"name": "Platos"}).json()["id"]
    plato = o.post("/api/items", json={"category_id": cat, "name": "Burger", "price": 10000}).json()["id"]
    sec = {t["label"]: t["secret"] for t in o.get("/api/tables").json()["tables"]}
    check(all(len(v) == 16 for v in sec.values()), "las claves de mesa nuevas son de 64 bits")
    o.put("/api/settings", json={"breb_enabled": 1, "breb_key": "3001234567", "breb_key_type": "celular", "breb_holder": "Acceso SA"})

    pedir = lambda mesa: cust.post(f"{base}/orders", json={"table": mesa, "key": sec[mesa], "diner_id": "d", "diner_name": "Ana", "items": [{"item_id": plato, "qty": 1}]})  # noqa: E731
    lineas = lambda mesa: [x for x in cust.get(f"{base}/bill", params={"table": mesa, "k": sec[mesa]}).json()["lines"] if x["state"] == "unpaid"]  # noqa: E731
    pagar_breb = lambda mesa: cust.post(f"{base}/pay", json={"table": mesa, "key": sec[mesa], "item_ids": [x["id"] for x in lineas(mesa)], "tip_pct": 0, "provider": "breb"}).json()["payment_id"]  # noqa: E731

    # ---------------- sesiones guardadas con hash
    cookie = o.cookies.get(auth.COOKIE)
    check(db.row("SELECT 1 FROM sessions WHERE token=?", (cookie,)) is None and db.row("SELECT 1 FROM sessions WHERE token=?", (auth.tok(cookie),)),
          "la base guarda el hash de la sesión, no la cookie")
    check(o.get("/api/me").status_code == 200, "y la sesión sigue funcionando")

    # ---------------- el personal no ve datos del dueño
    mi = kit.post("/api/staff-login", json={"slug": slug, "pin": pin}).json()
    for resp in (mi, kit.get("/api/me").json()):
        check(not ({"staff_pin", "email", "nit", "breb_key", "fiscal_address"} & set(resp["restaurant"])) and "takeaway_url" not in resp and "integrations" not in resp,
              "/api/me del personal no trae PIN, correo, datos fiscales ni la clave del QR para llevar")
    check(mi["restaurant"]["name"] and mi["restaurant"]["currency"] == "COP" and "features" in mi, "pero sí lo que la cocina usa")
    check(o.get("/api/me").json()["restaurant"]["staff_pin"] == pin, "el dueño sí lo ve")

    # ---------------- reseñas con la clave de la mesa
    fb = f"{base}/feedback"
    check(cust.post(fb, json={"table": "1", "rating": 5}).status_code == 403 and cust.post(fb, json={"table": "1", "key": "mala", "rating": 5}).status_code == 403,
          "calificar sin la clave de la mesa: 403")
    check(cust.post(fb, json={"table": "1", "key": sec["1"], "rating": 5}).status_code == 200, "con la clave, sí")

    # ---------------- propina: tope en el servidor
    check(pedir("1").status_code == 200, "pedido de la mesa 1")
    n = [x["id"] for x in lineas("1")]
    cash = lambda tip: cust.post(f"{base}/pay", json={"table": "1", "key": sec["1"], "item_ids": n, "tip_pct": tip, "provider": "cashier", "method": "cash"}).status_code  # noqa: E731
    check(cash(16) == 400 and cash(100) == 400 and cash(-1) == 400 and cash(15) == 200, "pagar: propina de 16 % o más (o negativa) da 400; 15 % pasa")
    check(cust.post(f"{base}/quote", json={"subtotal": 10000, "tip_pct": 16}).status_code == 400 and cust.post(f"{base}/quote", json={"subtotal": 10000, "tip_pct": 15}).status_code == 200,
          "cotizar: mismo tope")
    check(kit.post("/api/floor/1/settle", json={"method": "cash", "tip": 1501}).status_code == 400, "caja: propina de más del 15 % de la cuenta da 400")
    check(kit.post("/api/floor/1/settle", json={"method": "cash", "tip": 1500}).status_code == 200, "caja: 15 % exacto pasa")

    # ---------------- ajustes
    chk = lambda body: o.put("/api/settings", json=body).status_code  # noqa: E731
    check(chk({"google_review_url": "javascript:alert(1)"}) == 400 and chk({"google_review_url": "http://x.co"}) == 400 and chk({"google_review_url": "https://g.page/r/x"}) == 200,
          "el enlace de reseñas debe ser https://")
    check(chk({"brand_color": "#12"}) == 400 and chk({"brand_color": "#zzzzzz"}) == 400 and chk({"brand_color": "#abcdef"}) == 200, "color de marca válido")
    check(chk({"staff_pin": "1234"}) == 400 and chk({"staff_pin": "12345a"}) == 400, "un PIN nuevo de menos de 6 dígitos se rechaza")
    check(chk({"staff_pin": pin, "name": "Acceso SA"}) == 200, "reenviar el PIN de siempre al guardar otros ajustes no molesta")
    check(chk({"staff_pin": "654321"}) == 200, "PIN nuevo de 6 dígitos")
    check(kit.get("/api/me").status_code == 401, "quien estaba dentro con el PIN anterior queda fuera")
    check(kit.post("/api/staff-login", json={"slug": slug, "pin": pin}).status_code == 401 and kit.post("/api/staff-login", json={"slug": slug, "pin": "654321"}).status_code == 200,
          "el PIN anterior ya no sirve")
    bad = o.post("/api/import/commit", json={"categories": [{"name": "X", "items": [{"name": "Y", "price": 1e30}]}]})
    check(bad.status_code == 400 and bad.json()["error"].startswith("Precio"), "importar un precio absurdo: 400, no 500")
    check(len(o.get("/api/menu").json()["categories"]) == 1, "y no deja una categoría a medias")

    # ---------------- suscripciones: nada de «activa para siempre» por omisión
    act = lambda **b: o.post("/api/superadmin/activate", headers=H, json={"email": "a@x.co", **b}).status_code  # noqa: E731
    check(act(plan="pro") == 400 and act(plan="pro", period_days=30) == 200 and act(plan="pro") == 200, "activar una cuenta sin periodo da 400; renovar o seguir activa, no")

    # ---------------- pagos: aprobación tardía y cobro duplicado
    kit.post("/api/staff-login", json={"slug": slug, "pin": "654321"})
    estado = lambda pid: db.row("SELECT status FROM payments WHERE id=?", (pid,))["status"]  # noqa: E731
    cancel = lambda pid, mesa: cust.post(f"{base}/pay/{pid}/cancel", json={"table": mesa, "key": sec[mesa]})  # noqa: E731
    # a) el cliente cancela y después el equipo confirma que el dinero sí llegó
    pedir("2")
    p1 = pagar_breb("2")
    cancel(p1, "2")
    check(estado(p1) == "failed", "cancelar un pago pendiente lo marca fallido")
    kit.post(f"/api/payments/{p1}/confirm")
    check(estado(p1) == "paid" and not lineas("2"), "…pero si el dinero llegó, la confirmación lo deja pagado y la cuenta cubierta")
    check(cust.post(f"{base}/pay/{p1}/claim", json={"table": "2", "key": sec["2"]}).status_code == 409 and estado(p1) == "paid", "un «ya pagué» tardío no revierte un pago confirmado")
    cancel(p1, "2")
    check(estado(p1) == "paid", "ni cancelar lo revierte")
    # b) el pago fallido y la caja cobra lo mismo: si luego llega el dinero, es un cobro doble
    pedir("3")
    p2 = pagar_breb("3")
    cancel(p2, "3")
    check(kit.post("/api/floor/3/settle", json={"method": "cash"}).status_code == 200 and not lineas("3"), "la caja cobra la mesa 3")
    kit.post(f"/api/payments/{p2}/confirm")
    check(estado(p2) == "conflict", "si después aparece el dinero del pago anterior queda como cobro duplicado, no como pagado")
    rv = kit.get("/api/payments/review").json()["payments"]
    check([x["status"] for x in rv] == ["conflict"] and rv[0]["id"] == p2, "el equipo lo ve para devolverlo")
    check(db.row("SELECT COUNT(*) n FROM invoices")["n"] == 0, "y no se factura")
    kit.post(f"/api/payments/{p2}/reject")
    check(estado(p2) == "refunded" and not kit.get("/api/payments/review").json()["payments"], "marcarlo devuelto lo saca de la lista")
    # c) un pago por confirmar bloquea el cobro en caja con un motivo claro
    pedir("4")
    p3 = pagar_breb("4")
    cust.post(f"{base}/pay/{p3}/claim", json={"table": "4", "key": sec["4"]})
    rs = kit.post("/api/floor/4/settle", json={"method": "cash"})
    check(rs.status_code == 409 and "por confirmar" in rs.json()["error"], "caja: con un pago por confirmar, avisa en vez de responder «ok» sin cobrar")
    kit.post(f"/api/payments/{p3}/confirm")
    check(estado(p3) == "paid", "confirmado el pago, la mesa queda cobrada")

    # ---------------- fuerza bruta: el PIN se corta por restaurante aunque cambie la IP; el login, por cuenta
    codes = [atk.post("/api/staff-login", headers=ip(i), json={"slug": slug, "pin": "000000"}).status_code for i in range(32)]
    check(codes[:29] == [401] * 29 and codes[29:] == [429] * 3, "30 PIN malos por hora por restaurante (ya había 1 en la cuenta), desde cualquier IP")
    check(kit.post("/api/staff-login", headers=ip(99, "5"), json={"slug": slug, "pin": "654321"}).status_code == 429, "durante el bloqueo ni el PIN bueno entra")
    check(atk.post("/api/login", headers=ip(1, "7"), json={"email": "no@existe.co", "password": "x"}).status_code == 401, "un correo inexistente da 401, igual que una clave mala")
    codes = [atk.post("/api/login", headers=ip(i, "8"), json={"email": "a@x.co", "password": "mala"}).status_code for i in range(11)]
    check(codes[:10] == [401] * 10 and codes[10] == 429, "10 claves malas por cuenta cada 15 minutos, desde cualquier IP")

print("Fase 5 ✔")
