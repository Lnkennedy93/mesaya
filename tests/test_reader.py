"""Lector local de cartas (sin IA ni red): PDFs de distintos diseños generados al vuelo, Word, Excel y OCR simulado.
Requiere fpdf2 (solo desarrollo):  pip install -r requirements-dev.txt   →   python -m tests.test_reader"""
import io
import sys
import zipfile

from app import menu_reader as mr
from tests.menu_fixtures import *  # noqa: F401,F403


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


def flat(res):
    return {i["name"]: i for c in res["categories"] for i in c["items"]}


def cats(res):
    return [(c["name"], [i["name"] for i in c["items"]]) for c in res["categories"]]


def ok_menu(res, label, check_order=True):
    f = flat(res)
    check(len(f) == 7, f"{label}: 7 platos (encontró {len(f)}: {list(f)[:9]})")
    check([c[0].lower() for c in cats(res)] == ["entradas", "platos fuertes", "bebidas"], f"{label}: categorías {[c[0] for c in cats(res)]}")
    check(all(f[n]["price"] == p for c in MENU for (n, p, _) in c[1] for n in [n] if n in f) and set(f) == {n for c in MENU for (n, _, _) in c[1]},
          f"{label}: nombres y precios exactos")


# ============================================================ PDFs
for label, fn in (("puntos guía + títulos en mayúscula", layout_leaders), ("precio a la derecha", layout_right_aligned),
                  ("dos columnas con bandas", layout_two_columns), ("precio en el renglón de abajo", layout_price_below)):
    res = mr.read_local(fn(), "pdf")
    ok_menu(res, label)
    check(res["good"] and res["source"] == "local", f"{label}: confianza alta, lectura local")
    if fn is layout_leaders:
        check(not any("300" in i["name"] or "calle" in i["name"].lower() for i in flat(res).values()), "teléfono y dirección ignorados")
        check(flat(res)["Patacones con hogao"]["tags"] == ["vegetariano"], "etiqueta vegetariano detectada")
        check(flat(res)["Limonada de coco"]["price"] == 9000 and "400 ml" in flat(res)["Limonada de coco"]["description"], "«400 ml» queda en la descripción, no como precio")
    if fn is layout_two_columns:
        check(flat(res)["Sancocho de gallina"]["price"] == 28000 and flat(res)["Trucha al ajillo"]["price"] == 30000, "dos columnas: cada precio con su plato")
    if fn is layout_leaders:
        check(flat(res)["Bandeja paisa"]["description"].startswith("Frijoles"), "descripción asociada al plato correcto")

res = mr.read_local(layout_plain(), "pdf")
f = flat(res)
check(len(f) == 7 and f["Bandeja paisa"]["price"] == 32000, f"sin estilos: igual encuentra los platos y precios ({len(f)} platos)")

res = mr.read_local(layout_sizes(), "pdf")
f = flat(res)
check(len(f) == 12 and f["Margarita (Personal)"]["price"] == 18000 and f["Margarita (Grande)"]["price"] == 38000 and f["Cuatro quesos (Mediana)"]["price"] == 28000,
      f"tamaños: un plato por tamaño, «Margarita (Grande)» = 38.000 ({len(f)} platos)")
check(res["good"] and any("tamaños" in w for w in res["warnings"]), "tamaños: lectura buena y se avisa que se separaron")

# PDF escaneado (solo imagen) → no hay texto
from PIL import Image  # noqa: E402

img = Image.new("RGB", (800, 600), "white")
buf = io.BytesIO()
img.save(buf, "PDF")
try:
    mr.read_local(buf.getvalue(), "pdf")
    check(False, "PDF escaneado detectado")
except mr.Unreadable as e:
    check("escaneada" in str(e), "PDF escaneado: mensaje claro (necesita OCR o IA)")
try:
    mr.read_local(b"%PDF-1.4 esto no es un pdf", "pdf")
    check(False, "PDF dañado detectado")
except mr.Unreadable as e:
    check("dañado" in str(e), "PDF dañado: mensaje claro")

# decimales (menú en dólares)
p = FPDF()
p.add_page()
p.set_font("Helvetica", "B", 14)
p.cell(0, 8, "Drinks", new_x="LMARGIN", new_y="NEXT")
for n, v in (("Lemonade", "$ 4.50"), ("Iced tea", "$ 3.75"), ("Coffee", "$ 2.50")):
    p.set_font("Helvetica", "B", 11)
    p.cell(120, 6, n)
    p.cell(0, 6, v, align="R", new_x="LMARGIN", new_y="NEXT")
res = mr.read_local(pdf_out(p), "pdf", decimals=2)
check(flat(res).get("Lemonade", {}).get("price") == 4.5 and len(flat(res)) == 3, "moneda con decimales (USD): 4.50 → 4,5")
res0 = mr.read_local(pdf_out(p), "pdf", decimals=0)
check(len(flat(res0)) == 0 or not res0["good"], "con COP (sin decimales) «4.50» no se confunde con un precio")

# ============================================================ precios: casos límite
fp = lambda t, d=0: [round(v) for _, _, v in mr.find_prices(t, d)]  # noqa: E731
check(fp("Arroz $ 24.000") == [24000] and fp("Arroz 24,000") == [24000] and fp("Arroz 24000") == [24000], "formatos 24.000 / 24,000 / 24000")
check(fp("Jugo 400 ml con 2 huevos") == [] and fp("Carne 300 gr y arroz") == [], "cantidades (ml, gr, huevos) no son precios")
check(fp("Tamal 8k") == [8000] and fp("Combo $15.500 c/u") == [15500], "8k y signo $ pegado")
check(fp("Llama al 3001234567") == [], "un teléfono no es un precio")

# ============================================================ Word
paras = []
for cat, items in MENU:
    paras.append((cat, True, 16))
    for n, pr, d in items:
        paras.append((f"{n}\t{money(pr)}", True, 11))
        if d:
            paras.append((d, False, 9))
check(mr.sniff_office(docx(paras)) == "docx", "reconoce un .docx por su contenido")
res = mr.read_local(docx(paras), "docx")
ok_menu(res, "Word (párrafos con tabulador)")
rows = [("Plato", "Descripción", "Precio")] + [(n, d, money(pr)) for _, items in MENU for n, pr, d in items]
res = mr.read_local(docx(table=rows[1:]), "docx")
check(len(flat(res)) == 7 and flat(res)["Bandeja paisa"]["price"] == 32000, "Word: tabla nombre | descripción | precio (no se parte en columnas)")


# ============================================================ Excel
data = [("Categoría", "Plato", "Precio", "Descripción")] + [(c, n, pr, d) for c, items in MENU for n, pr, d in items]
check(mr.sniff_office(xlsx(data)) == "xlsx", "reconoce un .xlsx por su contenido")
res = mr.read_local(xlsx(data), "xlsx")
ok_menu(res, "Excel con encabezados (categoría, plato, precio)")

# ============================================================ OCR (el adaptador; el motor real es Tesseract)
fake = {"text": ["BEBIDAS", "Limonada", "de", "coco", "$", "9.000", "Jugo", "natural", "$", "7.000", "Gaseosa", "$", "5.000", "Tinto", "$", "3.000"],
        "conf": ["90"] * 16, "block_num": [1] * 16, "par_num": [1] * 16,
        "line_num": [1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 5, 5, 5],
        "left": [20, 20, 120, 160, 520, 540, 20, 80, 520, 540, 20, 520, 540, 20, 520, 540],
        "top": [10, 60, 60, 60, 60, 60, 110, 110, 110, 110, 160, 160, 160, 210, 210, 210],
        "width": [150, 90, 30, 60, 15, 80, 50, 70, 15, 80, 90, 15, 80, 60, 15, 80],
        "height": [34, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 24]}
frs = mr._ocr_lines(fake)
check(any(f.text == "Limonada de coco" for f in frs) and any(f.text.endswith("9.000") for f in frs), "OCR: palabras agrupadas en líneas, el precio queda separado del nombre")
res = mr.interpret([frs], [700.0])
check(sorted((i["name"], i["price"]) for c in res.categories for i in c["items"]) == [("Gaseosa", 5000.0), ("Jugo natural", 7000.0), ("Limonada de coco", 9000.0), ("Tinto", 3000.0)],
      "OCR: platos y precios correctos a partir de las líneas del OCR")
check(mr.ocr_available() in (True, False), "la disponibilidad de OCR se detecta sin romper")

print("\nLector local ✔")

# ============================================================ fotos de platos dentro del PDF
from PIL import Image  # noqa: E402,F811


def color_of(webp: bytes):
    return Image.open(io.BytesIO(webp)).convert("RGB").getpixel((60, 60))


def near(a, b, tol=14):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def photo_check(label, pdf, expect_all=True):
    res = mr.read_local(pdf, "pdf")
    items = [i for c in res["categories"] for i in c["items"]]
    got = {}
    for i in items:
        idx = i.get("image_idx")
        got[i["name"]] = color_of(res["images"][idx]) if idx is not None else None
    ok = all(got.get(n) is not None and near(got[n], item_color(k)) for k, (n, _, _) in enumerate(ITEMS))
    check(ok, f"fotos ({label}): cada plato recibe SU foto ({sum(v is not None for v in got.values())}/{len(ITEMS)})")
    check(len(res["images"]) == len(ITEMS), f"fotos ({label}): el banner ancho y el ícono diminuto no cuentan como fotos de platos ({len(res['images'])} fotos guardadas)")
    return res


for mode in ("left", "right", "above"):
    photo_check(f"foto a la {mode}" if mode != "above" else "foto encima", layout_item_photos(mode))
photo_check("dos columnas, foto a la izquierda", layout_item_photos("left", two_columns=True))
res = mr.read_local(layout_item_photos("left"), "pdf", with_images=False)
check(res["images"] == [] and all("image_idx" not in i for c in res["categories"] for i in c["items"]), "con_images=False no extrae fotos (más rápido)")
res = mr.read_local(layout_right_aligned(), "pdf")
check(res["images"] == [] and res["stats"]["pics"] == 0, "un PDF sin fotos no genera fotos ni avisos de fotos")
res = mr.read_local(layout_with_heavy_photo(3.0), "pdf")
check(res["images"] == [], "una foto de página completa (fondo) no se asigna a ningún plato")
print("\nFotos de platos ✔")
