"""Prueba MANUAL del asistente contra Gemini real (usa tu GEMINI_API_KEY del .env y consume unos centavos).
Crea un restaurante de ejemplo con pedidos y le hace preguntas.   python -m tests.live_assistant"""
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"
QUESTIONS = ["¿Cuántas empanadas se han vendido esta semana y cuánta plata se movió en total?",
             "¿Cuánto se demora la cocina en sacar un pedido?",
             "¿Cuántos clientes han pedido? ¿Y qué platos están apagados?",
             "Apaga la limonada, se acabó."]

with TestClient(app) as c:
    slug = c.post("/api/signup", json={"accept_terms": True, "name": "El Fogón", "email": "f@b.co", "password": "secreto123", "tables": 3}).json()["restaurant"]["slug"]
    c.post("/api/import/commit", json=c.post("/api/import/text", json={"text": "# Platos\nEmpanadas - 8.000\nLimonada - 6.500\nSopa - 12.000\n"}).json())
    items = {i["name"]: i["id"] for cat in c.get("/api/menu").json()["categories"] for i in cat["items"]}
    c.post("/api/superadmin/activate", headers={"x-admin-key": "k"}, json={"plan": "pro", "email": "f@b.co", "no_expiry": True})
    for n, (dish, qty) in enumerate([("Empanadas", 3), ("Sopa", 1), ("Empanadas", 2), ("Sopa", 2)]):
        t = c.get("/api/tables").json()["tables"][n % 3]
        c.post(f"/api/public/{slug}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": f"d{n}", "diner_name": "Ana",
                                                  "items": [{"item_id": items[dish], "qty": qty}]})
    for o in c.get("/api/orders").json()["orders"]:
        a = datetime.strptime(db.row("SELECT created_at FROM orders WHERE id=?", (o["id"],))["created_at"], FMT)
        db.run("UPDATE orders SET preparing_at=?, ready_at=? WHERE id=?", ((a + timedelta(minutes=3)).strftime(FMT), (a + timedelta(minutes=14)).strftime(FMT), o["id"]))
    c.post(f"/api/items/{items['Sopa']}/availability", json={"available": False})
    for q in QUESTIONS:
        r = c.post("/api/assistant", json={"question": q})
        print("\nP:", q, "\n", r.status_code, r.json())
