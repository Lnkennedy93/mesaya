"""Generadores de cartas de prueba (PDF con varios diseños, Word, Excel). Requiere fpdf2 (solo desarrollo)."""
import io
import zipfile

from fpdf import FPDF

MENU = [
    ("Entradas", [("Empanadas de carne", 8000, "Con aji casero"), ("Patacones con hogao", 12000, "Vegetariano")]),
    ("Platos fuertes", [("Bandeja paisa", 32000, "Frijoles, arroz, chicharron, huevo y platano"), ("Sancocho de gallina", 28000, "Con arroz y aguacate"),
                        ("Trucha al ajillo", 30000, "")]),
    ("Bebidas", [("Limonada de coco", 9000, "Jarra de 400 ml"), ("Jugo natural", 7000, "")]),
]


def money(v):
    return "$ {:,.0f}".format(v).replace(",", ".")


def pdf_out(pdf) -> bytes:
    return bytes(pdf.output())


# ---- A: precio al final del renglón con puntos guía; títulos en mayúscula más grandes
def layout_leaders():
    p = FPDF()
    p.add_page()
    p.set_font("Helvetica", "B", 22)
    p.cell(0, 14, "EL FOGON PAISA", align="C", new_x="LMARGIN", new_y="NEXT")
    p.set_font("Helvetica", "", 9)
    p.cell(0, 6, "Tel: 300 123 4567 - Calle 10 # 5-20, Medellin", align="C", new_x="LMARGIN", new_y="NEXT")
    for cat, items in MENU:
        p.ln(4)
        p.set_font("Helvetica", "B", 15)
        p.cell(0, 9, cat.upper(), new_x="LMARGIN", new_y="NEXT")
        for name, price, desc in items:
            p.set_font("Helvetica", "B", 11)
            dots = "." * max(3, 62 - len(name))
            p.cell(0, 6, f"{name} {dots} {money(price)}", new_x="LMARGIN", new_y="NEXT")
            if desc:
                p.set_font("Helvetica", "I", 9)
                p.cell(0, 5, desc, new_x="LMARGIN", new_y="NEXT")
    return pdf_out(p)


# ---- B: nombre a la izquierda y precio alineado a la derecha en otra celda
def layout_right_aligned():
    p = FPDF()
    p.add_page()
    for cat, items in MENU:
        p.ln(3)
        p.set_font("Helvetica", "B", 16)
        p.cell(0, 10, cat, new_x="LMARGIN", new_y="NEXT")
        for name, price, desc in items:
            p.set_font("Helvetica", "B", 11)
            p.cell(140, 6, name)
            p.cell(0, 6, money(price), align="R", new_x="LMARGIN", new_y="NEXT")
            if desc:
                p.set_font("Helvetica", "", 9)
                p.multi_cell(120, 4.5, desc, new_x="LMARGIN", new_y="NEXT")
    return pdf_out(p)


# ---- C: dos columnas con el título como banda (como la carta Cassarola)
def layout_two_columns():
    p = FPDF()
    p.add_page()
    y = 20
    for cat, items in MENU:
        p.set_xy(15, y)
        p.set_font("Helvetica", "B", 15)
        p.cell(0, 8, cat)
        y += 12
        for k in range(0, len(items), 2):
            h = 0
            for col, (name, price, desc) in enumerate(items[k:k + 2]):
                x = 15 + col * 98
                p.set_xy(x, y)
                p.set_font("Helvetica", "B", 10)
                p.cell(60, 5, name)
                p.cell(28, 5, money(price), align="R")
                if desc:
                    p.set_xy(x, y + 5)
                    p.set_font("Helvetica", "", 8)
                    p.multi_cell(88, 4, desc)
                h = max(h, 15)
            y += h
        y += 6
    return pdf_out(p)


# ---- E: el precio va en el renglón de abajo, solo
def layout_price_below():
    p = FPDF()
    p.add_page()
    for cat, items in MENU:
        p.set_font("Helvetica", "B", 16)
        p.cell(0, 10, cat, new_x="LMARGIN", new_y="NEXT")
        for name, price, desc in items:
            p.set_font("Helvetica", "B", 11)
            p.cell(0, 6, name, new_x="LMARGIN", new_y="NEXT")
            p.cell(0, 6, money(price), new_x="LMARGIN", new_y="NEXT")
            if desc:
                p.set_font("Helvetica", "", 9)
                p.cell(0, 5, desc, new_x="LMARGIN", new_y="NEXT")
    return pdf_out(p)


# ---- D: sin estilos (todo igual: mismo tamaño y sin negrita)
def layout_plain():
    p = FPDF()
    p.add_page()
    p.set_font("Courier", "", 10)
    for cat, items in MENU:
        p.cell(0, 6, cat.upper(), new_x="LMARGIN", new_y="NEXT")
        for name, price, desc in items:
            p.cell(0, 5, f"{name}   {money(price)}", new_x="LMARGIN", new_y="NEXT")
            if desc:
                p.cell(0, 5, "  " + desc, new_x="LMARGIN", new_y="NEXT")
        p.ln(3)
    return pdf_out(p)


# ---- F: varios tamaños/precios en un mismo renglón
def layout_sizes():
    p = FPDF()
    p.add_page()
    p.set_font("Helvetica", "B", 16)
    p.cell(0, 10, "Pizzas", new_x="LMARGIN", new_y="NEXT")
    for name in ("Margarita", "Pepperoni", "Hawaiana", "Cuatro quesos"):
        p.set_font("Helvetica", "B", 11)
        p.cell(60, 6, name)
        p.cell(40, 6, "Personal $ 18.000")
        p.cell(40, 6, "Mediana $ 28.000")
        p.cell(0, 6, "Grande $ 38.000", new_x="LMARGIN", new_y="NEXT")
    return pdf_out(p)


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(paragraphs=None, table=None):
    body = ""
    for text, bold, size in (paragraphs or []):
        b = "<w:b/>" if bold else ""
        s = f'<w:sz w:val="{size * 2}"/>' if size else ""
        parts = text.split("\t")
        runs = "<w:tab/>".join(f"<w:t>{x}</w:t>" for x in parts)
        body += f"<w:p><w:r><w:rPr>{b}{s}</w:rPr>{runs}</w:r></w:p>"
    if table:
        body += "<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in row) + "</w:tr>" for row in table) + "</w:tbl>"
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", xml)
    return out.getvalue()


def xlsx(rows):
    strings, srows = [], []
    for r in rows:
        cells = ""
        for ci, v in enumerate(r):
            ref = "ABCDEFG"[ci] + str(len(srows) + 1)
            if isinstance(v, (int, float)):
                cells += f'<c r="{ref}"><v>{v}</v></c>'
            else:
                strings.append(v)
                cells += f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'
        srows.append(f"<row>{cells}</row>")
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}"/>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}">' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData>' + "".join(srows) + "</sheetData></worksheet>")
    return out.getvalue()




# ---- G: carta con fotos pesadas (como "Menu-Cassarola-con-fotos.pdf": pasa de 10 MB)
def layout_with_heavy_photo(megabytes: float = 14.0) -> bytes:
    import os as _os
    from PIL import Image
    side = int((megabytes * 1024 * 1024 / 3) ** 0.5)
    noise = Image.frombytes("RGB", (side, side), _os.urandom(side * side * 3))  # el ruido no se comprime: peso garantizado
    png = io.BytesIO()
    noise.save(png, "PNG", compress_level=1)
    p = FPDF()
    p.add_page()
    for cat, items in MENU:
        p.set_font("Helvetica", "B", 16)
        p.cell(0, 10, cat, new_x="LMARGIN", new_y="NEXT")
        for name, price, desc in items:
            p.set_font("Helvetica", "B", 11)
            p.cell(140, 6, name)
            p.cell(0, 6, money(price), align="R", new_x="LMARGIN", new_y="NEXT")
    p.add_page()
    p.image(io.BytesIO(png.getvalue()), x=10, y=10, w=190)
    return pdf_out(p)


# ---- H: fotos de platos junto al texto (cada foto es de un color único para comprobar la asociación)
ITEMS = [(n, p, d) for _, items in MENU for (n, p, d) in items]


def item_color(k: int):
    return (30 + 30 * k, 200 - 22 * k, 60 + 25 * ((k * 3) % 7))


def _solid_png(color, px=120) -> io.BytesIO:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (px, px), color).save(b, "PNG")
    b.seek(0)
    return b


def layout_item_photos(mode: str = "left", two_columns: bool = False, with_noise_images: bool = True) -> bytes:
    """mode: 'left' | 'right' | 'above'. Con two_columns, los platos se reparten en 2 columnas con su foto al lado."""
    p = FPDF()
    p.set_auto_page_break(False)
    p.add_page()
    if with_noise_images:  # banner ancho (proporción 3.2:1) e ícono diminuto: NO son fotos de platos
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (640, 200), (240, 200, 10)).save(b, "PNG")
        b.seek(0)
        p.image(b, x=10, y=8, w=190, h=59)
        p.image(_solid_png((5, 5, 5), 60), x=10, y=70, w=8, h=8)
    y = 85
    for k, (name, price, desc) in enumerate(ITEMS):
        col = (k % 2) if two_columns else 0
        if two_columns and k % 2 == 0 and k:
            y += 30
        elif not two_columns and k:
            y += 30
        x = 10 + col * 100
        tx = x + (26 if mode == "left" else 0)
        if mode == "left":
            p.image(_solid_png(item_color(k)), x=x, y=y, w=22, h=22)
        elif mode == "right":
            p.image(_solid_png(item_color(k)), x=x + (62 if two_columns else 150), y=y, w=22, h=22)
        else:
            p.image(_solid_png(item_color(k)), x=x, y=y - 24, w=22, h=22)
        p.set_xy(tx, y)
        p.set_font("Helvetica", "B", 11)
        w_name = 36 if two_columns else (100 if mode == "left" else 110)
        p.cell(w_name, 6, name)
        p.cell(26 if two_columns else 30, 6, money(price), align="R")
        if desc:
            p.set_xy(tx, y + 7)
            p.set_font("Helvetica", "", 8)
            p.cell(60, 4, desc[:40])
        if mode == "above":
            y += 4
    return pdf_out(p)


# ---- H: página web impresa a PDF (tarjetas): nombre en negrita, descripción, precio y la foto a la derecha.
#         Cada foto trae perfil ICC y máscara de transparencia (esquinas redondeadas) y debajo se dibujó un marcador con
#         el logo; además hay un plato sin foto con un cuadro gris plano. Así salen las capturas de sitios de pedidos.
WEB_DISHES = ["Taco de birria", "Totopos", "Quesadilla al pastor", "Sopa del dia"]  # el último no tiene foto


def web_photo(color, px=312) -> io.BytesIO:
    from PIL import Image, ImageCms, ImageDraw
    im = Image.new("RGBA", (px, px), color + (255,))
    ImageDraw.Draw(im).rectangle([px // 2, 0, px, px], fill=tuple(min(255, v + 60) for v in color) + (255,))  # dos tonos: no es un color plano
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, px - 1, px - 1], 30, fill=255)
    im.putalpha(mask)
    b = io.BytesIO()
    im.save(b, "PNG", icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    b.seek(0)
    return b


def _logo_placeholder(px=104) -> io.BytesIO:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (px, px), "white")
    d = ImageDraw.Draw(im)
    for x in range(0, px, 8):
        d.rectangle([x, 0, x + 3, px], fill=(200, 30, 30))
    b = io.BytesIO()
    im.save(b, "PNG")
    b.seek(0)
    return b


def _flat_placeholder(px=104) -> io.BytesIO:
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (px, px), (60, 55, 55, 255))
    m = Image.new("L", (px, px), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, px - 1, px - 1], 12, outline=255, width=2)
    im.putalpha(m)
    b = io.BytesIO()
    im.save(b, "PNG")
    b.seek(0)
    return b


def layout_web_cards() -> bytes:
    p = FPDF()
    p.set_auto_page_break(False)
    p.add_page()
    y = 20
    for k, name in enumerate(WEB_DISHES):
        if name == "Totopos":  # encabezado de categoría con contador, como «Totopos 1» en las páginas de pedidos
            p.set_xy(10, y)
            p.set_font("Helvetica", "B", 16)
            p.cell(60, 8, "Totopos 1")
            y += 14
        p.set_xy(10, y)
        p.set_font("Helvetica", "B", 13)
        p.cell(80, 6, name)
        p.set_xy(10, y + 8)
        p.set_font("Helvetica", "", 9)
        p.cell(82, 4, "Una descripcion larga que llega casi hasta la foto")
        p.set_xy(10, y + 14)
        p.set_font("Helvetica", "B", 11)
        p.cell(30, 5, money(9000 + 1000 * k))
        p.image(_logo_placeholder(), x=95, y=y - 1, w=28, h=28)  # el marcador va debajo...
        p.image(web_photo(item_color(k)) if name != "Sopa del dia" else _flat_placeholder(), x=95, y=y - 1, w=28, h=28)  # ...y la foto encima
        y += 40
    return pdf_out(p)
