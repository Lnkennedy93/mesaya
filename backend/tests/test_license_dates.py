"""Licencia con fecha de inicio y de fin elegidas en el calendario del superusuario.   python -m tests.test_license_dates"""
import os
import tempfile
from datetime import datetime, timedelta
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


D = lambda n: (datetime.utcnow() + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731

with TestClient(app) as c, TestClient(app) as dueno:
    dueno.post("/api/signup", json={"accept_terms": True, "name": "Café Fechas", "email": "f@b.co", "password": "secreto123", "tables": 7})
    a = lambda **b: c.post("/api/superadmin/activate", headers=H, json={"email": "f@b.co", "plan": "pro", **b})  # noqa: E731
    row = lambda: next(r for r in c.get("/api/superadmin/restaurants", headers=H).json()["restaurants"] if r["email"] == "f@b.co")  # noqa: E731
    db.run("UPDATE restaurants SET trial_ends_at='2000-01-01 00:00:00' WHERE email='f@b.co'")  # prueba ya terminada: así se ve qué da la licencia por sí sola
    check(row()["effective_plan"] == "Gratis", "sin licencia, plan Gratis")

    check(a(starts_on="2026-13-40", ends_on=D(10)).status_code == 400, "una fecha imposible se rechaza")
    check(a(starts_on=D(10), ends_on=D(5)).status_code == 400, "el fin no puede ser anterior al inicio")
    check(a(starts_on=D(-20), ends_on=D(-10)).status_code == 400, "un fin que ya pasó se rechaza")
    check(a(starts_on=D(0), ends_on=D(5000)).status_code == 400, "la vigencia tiene tope")
    check(a(starts_on=D(3)).status_code == 400, "solo el inicio, sin fin ni periodo: se pide una vigencia")

    # licencia programada: empieza en 5 días y termina en 35
    check(a(starts_on=D(5), ends_on=D(35)).status_code == 200, "se programa una licencia con inicio y fin")
    r = row()
    check(r["license_start"] and r["paid_until"] and r["subscription_status"] == "active", "quedan guardados el inicio y el fin")
    # (zona horaria del negocio: Colombia, -300 min) el día empieza a las 00:00 locales = 05:00 UTC y el de fin se incluye completo = 04:59:59 UTC del día siguiente
    check(r["license_start"] == f"{D(5)} 05:00:00" and r["paid_until"] == f"{D(36)} 04:59:59", "el día de inicio empieza a las 00:00 y el de fin cuenta completo, en la hora del negocio")
    check(r["active"] is False and r["effective_plan"] == "Gratis", "mientras no llega la fecha de inicio, el negocio sigue sin la licencia")
    me = dueno.get("/api/me").json()
    check(me["active"] is False and me["sub_days_left"] is None and me["restaurant"]["license_start"] == r["license_start"], "el dueño ve que su licencia aún no empieza")

    # ya empezó (inicio ayer) y termina en 10 días
    check(a(starts_on=D(-1), ends_on=D(10)).status_code == 200, "se cambia a una licencia que ya empezó")
    r = row()
    check(r["active"] is True and r["effective_plan"] == "Pro", "con la fecha de inicio ya cumplida, el plan está activo")
    check(dueno.get("/api/me").json()["sub_days_left"] in (10, 11), "y al dueño le cuentan los días que le quedan")

    # los otros modos siguen funcionando y borran el inicio programado
    check(a(starts_on=D(5), ends_on=D(35)).status_code == 200 and a(period_days=30).status_code == 200 and row()["license_start"] == "" and row()["active"], "renovar por días empieza hoy (sin inicio programado)")
    check(a(no_expiry=True).status_code == 200 and row()["paid_until"] == "", "sin vencimiento sigue funcionando")
    check(a(starts_on=D(2), ends_on=D(9)).status_code == 200 and c.post("/api/superadmin/activate", headers=H, json={"email": "f@b.co", "plan": "pro", "status": "inactive"}).status_code == 200
          and row()["license_start"] == "" and not row()["active"], "desactivar limpia el inicio programado")
    ev = c.get("/api/superadmin/audit", headers=H).json()["events"]
    check(any("inicia" in e["detail"] and "vence" in e["detail"] for e in ev), "el cambio queda en la auditoría con inicio y fin")

print("Licencia con fechas ✔")
