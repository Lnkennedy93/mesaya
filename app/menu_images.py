"""Fotos de los platos dentro de un PDF: se extraen con su posición en la página y se asocian al plato más cercano.

Entiende las disposiciones habituales: foto a la izquierda del texto, a la derecha, o encima del nombre.
Las fotos se re-codifican a WebP (tamaño razonable, sin metadatos): el PDF nunca se guarda tal cual."""
import hashlib
import io
from dataclasses import dataclass

MAX_PICS = 400
MAX_PIXELS = 40_000_000  # protege de imágenes-bomba dentro del PDF
MIN_PX = 80
MIN_PT = 28


@dataclass
class Pic:
    page: int
    x0: float
    x1: float
    top: float
    bottom: float
    webp: bytes
    key: str  # huella del contenido: la misma foto usada en varios platos se guarda una sola vez


def _walk(obj):
    from pdfminer.layout import LTFigure
    for o in obj:
        yield o
        if isinstance(o, LTFigure):
            yield from _walk(o)


def _palette_bytes(entry) -> bytes:
    from pdfminer.pdftypes import resolve1
    v = resolve1(entry)
    if hasattr(v, "get_data"):
        return bytes(v.get_data())
    return bytes(v) if isinstance(v, (bytes, bytearray)) else b""


def decode_image(im):
    """LTImage de pdfminer → PIL.Image RGB, o None si el formato no se soporta."""
    from PIL import Image
    from pdfminer.pdftypes import resolve1
    stream = im.stream
    w, h = im.srcsize
    if not w or not h or w * h > MAX_PIXELS:
        return None
    filters = [str(f[0]) for f in stream.get_filters()] if hasattr(stream, "get_filters") else []
    data = stream.get_data()
    if any(("DCT" in f or "JPX" in f) for f in filters):  # JPEG / JPEG2000: ya vienen comprimidos
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")
    cs = list(im.colorspace or [])
    name = str(cs[0]).strip("/'") if cs else "DeviceRGB"
    bits = im.bits or 8
    mode = {"DeviceGray": "L", "CalGray": "L", "DeviceRGB": "RGB", "CalRGB": "RGB", "DeviceCMYK": "CMYK"}.get(name)
    palette = None
    if name == "ICCBased" and len(cs) > 1:
        mode = {1: "L", 3: "RGB", 4: "CMYK"}.get(resolve1(cs[1]).get("N"))
    elif name == "Indexed" and len(cs) >= 4 and bits == 8:
        palette = _palette_bytes(cs[3])
        base = resolve1(cs[1])
        base_name = str(base[0] if isinstance(base, list) else base).strip("/'")
        if base_name in ("DeviceRGB", "CalRGB", "ICCBased") and len(palette) >= 3:
            mode = "P"
    if mode is None:
        return None
    if mode == "L" and bits == 1:
        if len(data) != ((w + 7) // 8) * h:
            return None
        return Image.frombytes("1", (w, h), data).convert("RGB")
    comps = {"L": 1, "RGB": 3, "CMYK": 4, "P": 1}[mode]
    if bits != 8 or len(data) != w * h * comps:
        return None
    img = Image.frombytes(mode, (w, h), data)
    if mode == "P":
        img.putpalette(palette[:768])
    return img.convert("RGB")


def to_webp(img, max_px: int = 1000) -> bytes:
    img = img.copy()
    img.thumbnail((max_px, max_px))
    out = io.BytesIO()
    img.save(out, "WEBP", quality=82)
    return out.getvalue()


def pics_from_page(page, pno: int, budget: int) -> list[Pic]:
    """Fotos de una página de pdfminer (ya filtradas: tamaño mínimo, no fondos, proporción razonable)."""
    from pdfminer.layout import LTImage
    pics = []
    area = max(page.width * page.height, 1)
    for im in _walk(page):
        if len(pics) >= budget:
            break
        if not isinstance(im, LTImage):
            continue
        wpt, hpt = im.x1 - im.x0, im.y1 - im.y0
        pw, ph = im.srcsize
        if min(pw, ph) < MIN_PX or min(wpt, hpt) < MIN_PT or wpt * hpt > 0.55 * area:
            continue
        if not 0.35 <= wpt / max(hpt, 1) <= 3.0:
            continue
        try:
            img = decode_image(im)
            if img is None:
                continue
            key = hashlib.md5(img.tobytes()).hexdigest()
            pics.append(Pic(pno, im.x0, im.x1, page.height - im.y1, page.height - im.y0, to_webp(img), key))
        except Exception:  # una imagen rara no debe tumbar la lectura de la carta
            continue
    return pics


# ---------------------------------------------------------------- asociación foto ↔ plato
def _cost_left(it, g, pw):
    gap = it["x0"] - g.x1
    if -6 <= gap <= max(45, 0.08 * pw) and g.top - 10 <= it["top"] <= g.bottom:
        return abs(it["top"] - g.top) + 0.3 * max(gap, 0)
    return None


def _cost_right(it, g, pw):
    gap = g.x0 - it["x1"]
    if -6 <= gap <= max(45, 0.08 * pw) and g.top - 10 <= it["top"] <= g.bottom:
        return abs(it["top"] - g.top) + 0.3 * max(gap, 0)
    return None


def _cost_above(it, g, pw):
    gap = it["top"] - g.bottom
    overlap = min(it["x1"], g.x1) - max(it["x0"], g.x0)
    if -4 <= gap <= 28 and overlap >= 0.4 * min(max(it["x1"] - it["x0"], 1), max(g.x1 - g.x0, 1)):
        return 40 + max(gap, 0)
    return None


def match(items: list[dict], pics: list[Pic], page_widths: list[float]) -> dict[int, int]:
    """Índice de plato → índice de foto. Prueba foto a la izquierda / encima / a la derecha y se queda con la
    disposición que más fotos empareja (cada foto y cada plato se usan una sola vez)."""
    best: dict[int, int] = {}
    best_key = (-1, 0.0)
    for fn in (_cost_left, _cost_above, _cost_right):
        edges = []
        for i, it in enumerate(items):
            pw = page_widths[it["page"] - 1] if it["page"] - 1 < len(page_widths) else 600
            for j, g in enumerate(pics):
                if g.page != it["page"]:
                    continue
                c = fn(it, g, pw)
                if c is not None:
                    edges.append((c, i, j))
        edges.sort()
        used_i, used_j, got, total = set(), set(), {}, 0.0
        for c, i, j in edges:
            if i in used_i or j in used_j:
                continue
            used_i.add(i)
            used_j.add(j)
            got[i] = j
            total += c
        key = (len(got), -total)
        if key > best_key:
            best, best_key = got, key
    return best
