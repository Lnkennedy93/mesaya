"""Fidelización de clientes: agregar, listar, eliminar y aislamiento entre negocios.   python -m tests.test_customers"""
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


GOOD = {"document": "1.020.304.050", "name": "  Ana   María  Pérez ", "email": "Ana@Correo.co", "phone": "300 123 4567", "consent": True}

with TestClient(app) as a, TestClient(app) as b:
    for cl, mail in ((a, "a@b.co"), (b, "b@b.co")):
        cl.post("/api/signup", json={"accept_terms": True, "name": "Café " + mail, "email": mail, "password": "secreto123", "tables": 2})

    with TestClient(app) as anon:
        check(anon.get("/api/customers").status_code == 401, "sin sesión: 401")

    check(a.post("/api/customers", json=GOOD).status_code == 200, "cliente agregado")
    c = a.get("/api/customers").json()["customers"]
    check(len(c) == 1 and c[0]["document"] == "1020304050" and c[0]["name"] == "Ana María Pérez" and c[0]["email"] == "ana@correo.co" and c[0]["phone"] == "3001234567",
          "se guarda normalizado: cédula sin puntos, nombre limpio, correo en minúsculas, celular sin espacios")
    check(a.post("/api/customers", json=GOOD).status_code == 409, "misma cédula dos veces: 409")
    check(b.post("/api/customers", json=GOOD).status_code == 200, "otro negocio sí puede tener esa cédula")

    for field, val, msg in (("document", "12ab", "cédula con letras"), ("document", "123", "cédula muy corta"), ("email", "no-es-correo", "correo inválido"),
                            ("phone", "abc", "celular inválido"), ("name", "Al", "nombre muy corto")):
        r = a.post("/api/customers", json={**GOOD, "document": "999888777", field: val})
        check(r.status_code in (400, 422), "rechaza " + msg)
    check(a.post("/api/customers", json={**GOOD, "document": "999888777", "consent": False}).status_code == 400, "sin autorización de datos: 400")
    check(len(a.get("/api/customers").json()["customers"]) == 1, "los rechazados no se guardaron")

    # exportar a Excel: .xlsx válido, todo como texto (la cédula conserva ceros; una fórmula no se ejecuta)
    import io, zipfile
    import xml.etree.ElementTree as ET
    a.post("/api/customers", json={**GOOD, "document": "0012345678", "name": "=HYPERLINK(\"http://x\")\x01 Raro", "email": "raro@correo.co"})
    x = a.get("/api/customers.xlsx")
    check(x.status_code == 200 and "spreadsheetml.sheet" in x.headers["content-type"] and ".xlsx" in x.headers["content-disposition"], "exportar: descarga un .xlsx")
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheet = ET.fromstring(zipfile.ZipFile(io.BytesIO(x.content)).read("xl/worksheets/sheet1.xml"))
    grid = [["".join(t.itertext()) for t in r.findall("m:c", ns)] for r in sheet.find("m:sheetData", ns)]
    check(grid[0][0] == "Cédula" and len(grid) == 3, "exportar: encabezado + un renglón por cliente")
    check(["0012345678"] == [r[0] for r in grid if r[0].startswith("00")] and any(r[1].startswith("=HYPERLINK") and "\x01" not in r[1] for r in grid),
          "exportar: cédula con ceros intacta, fórmula como texto y sin caracteres de control")
    with TestClient(app) as anon:
        check(anon.get("/api/customers.xlsx").status_code == 401, "exportar exige sesión")
    check(len(ET.fromstring(zipfile.ZipFile(io.BytesIO(b.get("/api/customers.xlsx").content)).read("xl/worksheets/sheet1.xml")).find("m:sheetData", ns)) == 2,
          "exportar: cada negocio solo recibe sus clientes")
    a.delete("/api/customers/" + str(next(c2["id"] for c2 in a.get("/api/customers").json()["customers"] if c2["document"] == "0012345678")))

    cid = c[0]["id"]
    check(b.delete(f"/api/customers/{cid}").status_code == 200 and len(a.get("/api/customers").json()["customers"]) == 1, "otro negocio no puede borrar mis clientes")
    check(a.delete(f"/api/customers/{cid}").status_code == 200 and a.get("/api/customers").json()["customers"] == [], "eliminar cliente")
    check(len(b.get("/api/customers").json()["customers"]) == 1, "los clientes del otro negocio siguen")

print("\nTodo OK")
