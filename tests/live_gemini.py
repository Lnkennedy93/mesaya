"""Prueba MANUAL contra la API real de Gemini (usa tu GEMINI_API_KEY del .env y consume una pequeña cuota).
Genera una carta de ejemplo (imagen y PDF) y la lee a través del endpoint de la app.   python -m tests.live_gemini"""
import io
import os
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app import ai_import  # noqa: E402
from app.main import app  # noqa: E402

MENU = [
    ("EL FOGÓN PAISA", None, None),
    ("ENTRADAS", None, None),
    ("Empanadas de carne (3 und)", "Con ají casero", "$ 8.000"),
    ("Patacones con hogao", "Vegetariano", "$ 12.000"),
    ("PLATOS FUERTES", None, None),
    ("Bandeja paisa", "Frijoles, arroz, chicharrón, carne molida, huevo y plátano", "$ 32.000"),
    ("Sancocho de gallina", "Con arroz y aguacate", "$ 28.000"),
    ("Trucha al ajillo", "Picante opcional", "$ 30.000"),
    ("BEBIDAS", None, None),
    ("Limonada de coco", None, "$ 9.000"),
    ("Jugo natural en agua", "Mora, lulo o maracuyá", "$ 7.000"),
    ("POSTRES", None, None),
    ("Tres leches", None, "$ 10.000"),
    ("Tel: 300 123 4567 · Calle 10 # 5-20, Medellín", None, None),
]


def menu_image() -> Image.Image:
    img = Image.new("RGB", (1000, 1250), "#fffaf0")
    d = ImageDraw.Draw(img)
    try:
        big, mid, small = (ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 44), ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 32),
                           ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24))
    except OSError:
        big = mid = small = ImageFont.load_default()
    y = 40
    for name, desc, price in MENU:
        if name.isupper() and price is None:
            y += 18
            d.text((60, y), name, fill="#8a1c1c", font=big if y < 80 else mid)
            y += 70 if y < 80 else 56
        elif price is None:
            d.text((60, y), name, fill="#555", font=small)
            y += 40
        else:
            d.text((60, y), name, fill="#111", font=mid)
            d.text((820, y), price, fill="#111", font=mid)
            y += 42
            if desc:
                d.text((60, y), desc, fill="#555", font=small)
                y += 38
            y += 12
    return img


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


print("Proveedor:", ai_import.provider())
img = menu_image()
png = io.BytesIO(); img.save(png, "PNG")
pdf = io.BytesIO(); img.save(pdf, "PDF")


def names(draft):
    return {i["name"].lower(): i for c in draft["categories"] for i in c["items"]}


with TestClient(app) as c:
    c.post("/api/signup", json={"accept_terms": True, "name": "Prueba IA", "email": "ia@x.co", "password": "secreto123", "tables": 1})
    check(c.get("/api/me").json()["ai_available"], "el servidor detecta la clave de IA")
    for label, data, fname in (("PNG", png.getvalue(), "carta.png"), ("PDF", pdf.getvalue(), "carta.pdf")):
        r = c.post("/api/import/ai", files={"file": (fname, data)})
        check(r.status_code == 200, f"{label}: la IA leyó el archivo (HTTP {r.status_code}) {'' if r.status_code == 200 else r.text[:200]}")
        draft = r.json()
        n = sum(len(x["items"]) for x in draft["categories"])
        print(f"     {label}: {len(draft['categories'])} categorías, {n} platos →", [x["name"] for x in draft["categories"]])
        it = names(draft)
        find = lambda frag: next((v for k, v in it.items() if frag in k), None)  # noqa: E731
        check(n >= 8 and len(draft["categories"]) >= 3, f"{label}: encontró las categorías y casi todos los platos")
        check(find("bandeja") and find("bandeja")["price"] == 32000, f"{label}: «$ 32.000» → 32000 (formato colombiano bien leído)")
        check(find("limonada") and find("limonada")["price"] == 9000, f"{label}: precio de la limonada")
        check(find("patacones") and "vegetariano" in find("patacones")["tags"], f"{label}: etiqueta «vegetariano» detectada")
        check(not any("tel" in k or "calle" in k for k in it), f"{label}: ignoró teléfono y dirección")
        check(find("empanadas") and "ají" in find("empanadas")["description"].lower(), f"{label}: descripción conservada")
    used = c.get("/api/me").json()
    from app import db
    check(db.row("SELECT ai_imports_used n FROM restaurants")["n"] == 2, "se descontaron 2 lecturas del plan")
    # confirmar: el borrador se convierte en carta real
    added = c.post("/api/import/commit", json=draft).json()["added"]
    menu = c.get("/api/menu").json()["categories"]
    price = next(i["price"] for k in menu for i in k["items"] if "bandeja" in i["name"].lower())
    check(added >= 8 and price == 32000, "al confirmar queda la carta creada con los precios correctos")
print("\nLectura con IA real ✔")
