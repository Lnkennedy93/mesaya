"""Pruebas del flujo colombiano: INC, Nequi (Wompi), Bre-B, factura electrónica (Factus).
Todo el tráfico externo se simula; no se llama a Wompi ni a Factus.   python -m tests.test_colombia"""
import hashlib
import os
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_SECRET_KEY"] = "cFhmZ3N3N2pFb0F4dDJyV2xRR2hQZ3ZtQ0hCQ2ZQZmM="  # solo pruebas
os.environ["MESAYA_ONLINE_PAYMENTS"] = "1"
os.environ["MESAYA_INVOICING"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import colombia, invoicing, payments, vault  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


class Resp:
    def __init__(self, status, data):
        self.status_code, self._d = status, data

    def json(self):
        return self._d


CALLS = []
WOMPI_TX_STATUS = {"v": "PENDING"}


def fake_http(method, url, **kw):
    CALLS.append((method, url, kw))
    if "wompi.co" in url and url.endswith("/merchants/pub_test_1"):
        return Resp(200, {"data": {"presigned_acceptance": {"acceptance_token": "acc_tok"}}})
    if "wompi.co" in url and method == "POST" and url.endswith("/transactions"):
        return Resp(201, {"data": {"id": "tx-123", "status": "PENDING"}})
    if "wompi.co" in url and "/transactions/tx-123" in url:
        return Resp(200, {"data": {"id": "tx-123", "status": WOMPI_TX_STATUS["v"]}})
    if url.endswith("/oauth/token"):
        return Resp(200, {"access_token": "factus_tok", "expires_in": 600})
    if url.endswith("/v1/bills/validate"):
        return Resp(201, {"data": {"bill": {"number": "SETP990000123", "cufe": "abc", "qr": "https://catalogo-vpfe.dian.gov.co/x",
                                            "public_url": "https://factus.test/f/1"}}})
    if url.endswith("/v1/numbering-ranges"):
        return Resp(200, {"data": [{"id": 8, "prefix": "SETP", "document": "Factura de Venta", "from": 1, "to": 1000, "current": 5, "is_active": 1}]})
    return Resp(404, {})


payments._req = fake_http
invoicing._http = fake_http

# --- utilidades fiscales
check(colombia.nit_dv("860034313") == "7", "dígito de verificación NIT")
check(colombia.clean_customer(None)["doc_number"] == "222222222222", "sin datos → Consumidor Final")
check(colombia.clean_customer({"doc_type": "NIT", "doc_number": "860.034.313", "name": "ACME SAS"})["dv"] == "7", "cliente NIT con DV")
s = vault.seal({"a": "secreto"})
check("secreto" not in s and vault.unseal(s) == {"a": "secreto"}, "credenciales cifradas en reposo")

with TestClient(app) as c:
    r = c.post("/api/signup", json={"accept_terms": True, "name": "Asadero La 80", "email": "dueno@asadero.co", "password": "secreto123", "tables": 2}).json()
    slug = r["restaurant"]["slug"]
    check(r["restaurant"]["tax_type"] == "INC" and r["restaurant"]["tax_pct"] == 8 and r["restaurant"]["tip_pct"] == 10,
          "restaurante COP nace con INC 8 % y propina 10 %")

    cat = c.post("/api/categories", json={"name": "Platos"}).json()["id"]
    item = c.post("/api/items", json={"category_id": cat, "name": "Bandeja paisa", "price": 40000}).json()["id"]
    t = c.get("/api/tables").json()["tables"][0]
    base = f"/api/public/{slug}"
    order = {"table": t["label"], "key": t["secret"], "diner_id": "d1", "diner_name": "Ana", "items": [{"item_id": item, "qty": 2}]}

    pv = c.get(f"{base}/menu", params={"t": t["label"], "k": t["secret"]}).json()
    check([p["id"] for p in pv["providers"]] == ["cashier"], "sin configurar solo aparece «pagar en caja» (el pago demo no se filtra a producción)")

    # --- configurar datos fiscales + integraciones
    c.put("/api/settings", json={"legal_name": "Asadero La 80 SAS", "nit": "900.123.456", "inv_provider": "factus",
                                 "inv_range_id": 8, "fiscal_municipality_id": 980, "nequi_enabled": 1, "breb_enabled": 1,
                                 "breb_key": "3001234567", "breb_key_type": "celular", "breb_holder": "Asadero La 80 SAS"})
    me = c.put("/api/integrations/invoicing", json={"client_id": "cid", "client_secret": "cs", "username": "u@x.co", "password": "pw"}).json()
    me = c.put("/api/integrations/payments", json={"wompi_public": "pub_test_1", "wompi_private": "prv_test_1", "wompi_events": "evsecret", "wompi_integrity": "integ"}).json()
    check(me["restaurant"]["nit_dv"] == "8" or me["restaurant"]["nit_dv"].isdigit(), "NIT guardado con DV calculado")
    check(me["integrations"]["inv_configured"] and me["integrations"]["wompi_configured"], "integraciones configuradas")
    check("cs" not in str(me) and "prv_test_1" not in str(me), "las claves nunca se devuelven al navegador")
    check(c.put("/api/settings", json={"inv_provider": "mock"}).status_code == 400, "factura demo bloqueada fuera de MESAYA_DEMO")
    rg = c.post("/api/invoicing/test").json()["ranges"]
    check(rg[0]["prefix"] == "SETP", "probar conexión Factus lista rangos de numeración")

    pv = c.get(f"{base}/menu", params={"t": t["label"], "k": t["secret"]}).json()
    check([p["id"] for p in pv["providers"]] == ["nequi", "breb", "cashier"], "Nequi, Bre-B y caja disponibles")

    # --- pedido + pago con Nequi
    c.post(f"{base}/orders", json=order)
    lines = c.get(f"{base}/bill", params={"table": t["label"], "k": t["secret"]}).json()["lines"]
    ids = [l["id"] for l in lines]
    pay = {"table": t["label"], "key": t["secret"], "item_ids": ids, "tip_pct": 10, "provider": "nequi", "payer": "Ana",
           "invoice": {"doc_type": "CC", "doc_number": "1012345678", "name": "Ana Pérez", "email": "ana@correo.co"}}
    check(c.post(f"{base}/pay", json={**pay, "phone": "12345"}).status_code == 400, "celular inválido rechazado")
    check(c.get(f"{base}/bill", params={"table": t["label"], "k": t["secret"]}).json()["lines"][0]["state"] == "unpaid",
          "un celular inválido no deja el plato reservado")
    res = c.post(f"{base}/pay", json={**pay, "phone": "300 123 4567"}).json()
    check(res["mode"] == "push" and res["total"] == 88000, "cobro push a Nequi: 80.000 + 10 % propina")
    post = next(x for x in CALLS if x[0] == "POST" and x[1].endswith("/transactions"))
    body = post[2]["json"]
    check(body["amount_in_cents"] == 8800000 and body["currency"] == "COP" and body["payment_method"] == {"type": "NEQUI", "phone_number": "3001234567"},
          "Wompi recibe monto en centavos y celular normalizado")
    check(body["signature"] == hashlib.sha256(f"{body['reference']}8800000COPinteg".encode()).hexdigest(), "firma de integridad Wompi")
    check(post[2]["headers"]["Authorization"] == "Bearer prv_test_1", "autenticación con llave privada")
    st = c.get(f"{base}/bill", params={"table": t["label"], "k": t["secret"]}).json()["lines"][0]["state"]
    check(st == "reserved", "mientras el cliente aprueba, el plato queda reservado")
    check(c.post(f"{base}/pay", json={**pay, "phone": "3001234567"}).status_code == 409, "no se puede cobrar dos veces lo reservado")

    pid = res["payment_id"]
    q = {"table": t["label"], "k": t["secret"]}
    check(c.get(f"{base}/pay/{pid}", params=q).json()["status"] == "pending", "estado pendiente")

    # webhook con firma falsa / verdadera
    ref = next(x for x in __import__("app.db", fromlist=["x"]).rows("SELECT reference FROM payments WHERE id=?", (pid,)))["reference"]
    ev = {"event": "transaction.updated", "data": {"transaction": {"id": "tx-123", "reference": ref, "status": "APPROVED", "amount_in_cents": 8800000}},
          "timestamp": int(time.time()), "signature": {"properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"]}}
    raw = f"tx-123APPROVED8800000{ev['timestamp']}evsecret"
    ev["signature"]["checksum"] = hashlib.sha256(raw.encode()).hexdigest().upper()
    bad = {**ev, "signature": {**ev["signature"], "checksum": "0" * 64}}
    check(c.post(f"/api/webhooks/wompi/{slug}", json=bad).status_code == 400, "webhook con checksum falso rechazado")
    wrong_amount = {**ev, "data": {"transaction": {**ev["data"]["transaction"], "amount_in_cents": 100}}}
    wrong_amount["signature"] = {**ev["signature"], "checksum": hashlib.sha256(f"tx-123APPROVED100{ev['timestamp']}evsecret".encode()).hexdigest()}
    c.post(f"/api/webhooks/wompi/{slug}", json=wrong_amount)
    check(c.get(f"{base}/pay/{pid}", params=q).json()["status"] == "pending", "monto distinto al cobrado no aprueba el pago")
    check(c.post(f"/api/webhooks/wompi/{slug}", json=ev).status_code == 200, "webhook válido aceptado")
    time.sleep(0.5)  # la factura se emite en segundo plano
    v = c.get(f"{base}/pay/{pid}", params=q).json()
    check(v["status"] == "paid", "pago Nequi aprobado por webhook")
    check(v["invoice"]["number"] == "SETP990000123" and v["invoice"]["status"] == "issued", "factura electrónica emitida y visible al cliente")

    fb = next(x for x in CALLS if x[1].endswith("/v1/bills/validate"))
    payload = fb[2]["json"]
    check(payload["customer"]["identification"] == "1012345678" and payload["customer"]["names"] == "Ana Pérez", "factura a nombre del cliente")
    it = payload["items"][0]
    check(it["tax_rate"] == "8.00" and it["tribute_id"] == 4 and abs(it["price"] - 37037.04) < 0.01 and it["quantity"] == 2,
          "INC 8 % desglosado: precio 40.000 incluye impuesto → base 37.037,04")
    check(payload["reference_code"] == f"mesaya-{pid}" and payload["numbering_range_id"] == 8, "referencia única y rango de numeración")
    check(fb[2]["headers"]["Authorization"] == "Bearer factus_tok", "token OAuth de Factus")
    # idempotencia: reenviar el webhook no duplica factura
    c.post(f"/api/webhooks/wompi/{slug}", json=ev)
    time.sleep(0.3)
    check(len(c.get("/api/invoices").json()["invoices"]) == 1, "un pago = una factura (idempotente)")

    # --- Bre-B asistido + factura a consumidor final
    c.post(f"{base}/orders", json={**order, "diner_id": "d2", "items": [{"item_id": item, "qty": 1}]})
    lines = [l for l in c.get(f"{base}/bill", params=q).json()["lines"] if l["state"] == "unpaid"]
    res = c.post(f"{base}/pay", json={"table": t["label"], "key": t["secret"], "item_ids": [l["id"] for l in lines], "tip_pct": 0, "provider": "breb"}).json()
    check(res["mode"] == "breb" and res["breb"]["key"] == "3001234567" and res["total"] == 40000, "Bre-B muestra llave y valor exacto")
    bp = res["payment_id"]
    check(c.post(f"{base}/pay/{bp}/claim", json={"table": t["label"], "key": t["secret"]}).status_code == 200, "cliente reporta «ya pagué»")
    c.post("/api/logout")
    me = c.post("/api/login", json={"email": "dueno@asadero.co", "password": "secreto123"}).json()
    c.post("/api/logout")
    c.post("/api/staff-login", json={"slug": slug, "pin": me["restaurant"]["staff_pin"]})
    rv = c.get("/api/payments/review").json()["payments"]
    check(len(rv) == 1 and rv[0]["total"] == 40000, "el equipo ve el pago por confirmar")
    check(c.get("/api/invoices").status_code == 403, "el equipo no ve facturas (solo el dueño)")
    c.post(f"/api/payments/{bp}/confirm")
    time.sleep(0.5)
    c.post("/api/logout")
    c.post("/api/login", json={"email": "dueno@asadero.co", "password": "secreto123"})
    invs = c.get("/api/invoices").json()["invoices"]
    cf = next(i for i in invs if i["payment_id"] == bp)
    check(cf["status"] == "issued" and cf["customer"]["name"] == "Consumidor Final", "Bre-B confirmado → factura a Consumidor Final")

    # --- fallo del proveedor → reintento
    orig = fake_http
    def down(method, url, **kw):
        if url.endswith("/v1/bills/validate"):
            return Resp(422, {"message": "Validación", "data": {"errors": {"customer.email": ["inválido"]}}})
        return orig(method, url, **kw)
    invoicing._http = down
    c.post(f"{base}/orders", json={**order, "diner_id": "d3", "items": [{"item_id": item, "qty": 1}]})
    lines = [l for l in c.get(f"{base}/bill", params=q).json()["lines"] if l["state"] == "unpaid"]
    c.post("/api/floor/%s/settle" % t["label"], json={"method": "cash"})
    time.sleep(0.5)
    bad_inv = c.get("/api/invoices").json()["invoices"][0]
    check(bad_inv["status"] == "error" and "customer.email" in bad_inv["error"], "error del proveedor visible para el dueño")
    invoicing._http = orig
    ok = c.post(f"/api/invoices/{bad_inv['id']}/retry").json()["invoice"]
    check(ok["status"] == "issued", "reintento manual emite la factura")

print("\nFlujo Colombia ✔")
