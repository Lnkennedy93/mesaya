"""Fase 3 de la auditoría: candado por restaurante, índices, una consulta para Cocina y menos consultas por petición.
python -m tests.test_perf"""
import os
import tempfile
import threading
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402

from app import db, service  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


class Counter:
    """Cuenta las consultas que hace una petición (db.row y db.rows)."""

    def __init__(self):
        self.n = 0

    def __enter__(self):
        self._row, self._rows = db.row, db.rows
        db.row = lambda *a, **k: (setattr(self, "n", self.n + 1), self._row(*a, **k))[1]
        db.rows = lambda *a, **k: (setattr(self, "n", self.n + 1), self._rows(*a, **k))[1]
        return self

    def __exit__(self, *e):
        db.row, db.rows = self._row, self._rows


def signup(c, name, email):
    return c.post("/api/signup", json={"accept_terms": True, "name": name, "email": email, "password": "secreto123", "tables": 7}).json()


with TestClient(app) as a, TestClient(app) as b, TestClient(app) as cust, TestClient(app) as kit:
    ma, mb = signup(a, "Local A", "a@x.co"), signup(b, "Local B", "b@x.co")
    slug, pin, rid_a, rid_b = ma["restaurant"]["slug"], ma["restaurant"]["staff_pin"], ma["restaurant"]["id"], mb["restaurant"]["id"]
    kit.post("/api/staff-login", json={"slug": slug, "pin": pin})
    cat = a.post("/api/categories", json={"name": "Platos"}).json()["id"]
    plato = a.post("/api/items", json={"category_id": cat, "name": "Burger", "price": 10000}).json()["id"]
    sec = {t["label"]: t["secret"] for t in a.get("/api/tables").json()["tables"]}

    # ---------------- índices (los que el asesor de Supabase marcaba como faltantes)
    want = {"idx_order_items_order", "idx_orders_table", "idx_items_resto", "idx_items_cat", "idx_categories_resto", "idx_payments_resto",
            "idx_calls_resto", "idx_feedback_resto", "idx_sessions_resto", "idx_images_resto", "idx_invoices_resto", "idx_resets_resto"}
    if db.IS_PG:
        have = {r["indexname"] for r in db.rows("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema()")}
    else:
        have = {r["name"] for r in db.rows("SELECT name FROM sqlite_master WHERE type='index'")}
    check(want <= have, f"existen los 12 índices nuevos (faltan: {sorted(want - have)})")

    # ---------------- Cocina: una petición, y las consultas no crecen con el número de mesas
    def snap():
        with Counter() as n:
            r = kit.get("/api/kitchen")
        return r, n.n

    r0, q0 = snap()
    check(r0.status_code == 200 and set(r0.json()) == {"orders", "calls", "tables", "payments", "now"}, "el endpoint único devuelve pedidos, llamadas, mesas y pagos por revisar")
    for lb in sec:
        cust.post(f"/api/public/{slug}/orders", json={"table": lb, "key": sec[lb], "diner_id": "d", "diner_name": "Ana", "items": [{"item_id": plato, "qty": 1}]})
        cust.post(f"/api/public/{slug}/call", json={"table": lb, "key": sec[lb], "type": "waiter"})
    r1, q1 = snap()
    check(q1 <= q0 + 2, f"con 7 mesas con pedido hacen casi las mismas consultas que sin ninguna ({q0} → {q1}): ya no hay una por mesa o por pedido")
    j = r1.json()
    check(len(j["orders"]) == 7 and all(len(o["items"]) == 1 for o in j["orders"]), "cada pedido trae sus platos")
    check(len(j["calls"]) == 7 and len(j["tables"]) == 7, "y las llamadas y las 7 mesas")
    check(all(t["unpaid"] == 10000 and len(t["orders"]) == 1 for t in j["tables"]), "la cuenta por mesa sale bien con la consulta única")
    check(j["orders"] == kit.get("/api/orders").json()["orders"] and j["tables"] == kit.get("/api/floor").json()["tables"] and j["calls"] == kit.get("/api/calls").json()["calls"],
          "el resultado es igual al de los endpoints separados (siguen existiendo para otras pantallas)")
    check(TestClient(app).get("/api/kitchen").status_code == 401, "sin sesión: 401")
    with Counter() as n:
        kit.get("/api/me")
    check(n.n == 1, f"una petición autenticada hace UNA consulta de sesión+restaurante (antes dos): {n.n}")
    check(kit.get("/api/me").json()["role"] == "staff", "y el rol de la sesión llega bien")

    # ---------------- la cuenta de todas las mesas = la unión de las de cada mesa
    todo = service.bill_lines(rid_a)
    por_mesa = [l for lb in sec for l in service.bill_lines(rid_a, lb)]
    check(sorted(l["id"] for l in todo) == sorted(l["id"] for l in por_mesa) and len(todo) == 7, "bill_lines sin mesa = todas las mesas juntas")
    check(service.bill_lines(rid_b) == [], "y no mezcla restaurantes")

    # ---------------- candado por restaurante (PostgreSQL; en SQLite el archivo se bloquea entero)
    if db.IS_PG:
        entro, suelta = threading.Event(), threading.Event()

        def sostener():
            with db.tx(rid_a):
                entro.set()
                suelta.wait(15)

        h = threading.Thread(target=sostener)
        h.start()
        entro.wait(10)
        t0 = time.time()
        with db.tx(rid_b):
            pass
        check(time.time() - t0 < 1.5, "mientras un local tiene su transacción abierta, otro local escribe sin esperar")
        esperas = []

        def mismo():
            t1 = time.time()
            with db.tx(rid_a):
                esperas.append(time.time() - t1)

        h2 = threading.Thread(target=mismo)
        h2.start()
        time.sleep(0.8)
        check(h2.is_alive(), "pero el mismo local sí espera (sus escrituras siguen serializadas)")
        suelta.set()
        h.join()
        h2.join()
        check(esperas and esperas[0] >= 0.7, f"y entra apenas se libera ({esperas[0]:.1f} s)")
        # el cobro simultáneo sigue sin duplicarse con el candado por restaurante
        res = []
        k2 = TestClient(app)
        k2.__enter__()
        k2.post("/api/staff-login", json={"slug": slug, "pin": pin})
        ths = [threading.Thread(target=lambda c=c: res.append(c.post("/api/floor/1/settle", json={"method": "cash"}))) for c in (kit, k2)]
        [t.start() for t in ths]
        [t.join() for t in ths]
        k2.__exit__(None, None, None)
        check(db.row("SELECT COUNT(*) n FROM payments WHERE restaurant_id=? AND table_label='1' AND status='paid'", (rid_a,))["n"] == 1,
              "dos cobros simultáneos en el mismo local siguen dando un solo pago")
    else:
        print("(candado por restaurante: solo se prueba en PostgreSQL)")

print("Rendimiento ✔")
