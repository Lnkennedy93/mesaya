"""Lector LOCAL de cartas: sin IA, sin internet, sin costo, y los archivos no salen del servidor.

Entiende:  PDF con texto (el que se exporta de Word, Canva, Google Docs...), Word (.docx), Excel (.xlsx)
           y, si el servidor tiene OCR instalado, fotos y PDF escaneados.

Cómo lee un PDF: extrae cada fragmento de texto con su posición y estilo (tamaño, negrita), reconstruye filas y
columnas, y decide por ESTILO: el título de sección es la letra más grande, el plato es el texto con precio y la
descripción es el texto más pequeño que lo sigue. Funciona bien con cartas de 1 o 2 columnas con el precio a la
derecha o al lado del nombre. Cuando el diseño es raro devuelve avisos o `needs_ai` y la app puede usar la IA.
"""
import io
import re
import shutil
import statistics
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from . import ai_import, menu_images

# ---------------------------------------------------------------- tipos
SMALL_WORDS = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "a", "al", "con", "sin", "en", "por", "para", "un", "una", "tu", "su"}
CONNECTORS = {"y", "de", "con", "o", "e", "del", "al", "en", "a", "la", "el", "los", "las", "sin", "por", "para"}
TAG_WORDS = {"vegano": "vegano", "vegana": "vegano", "vegetariano": "vegetariano", "vegetariana": "vegetariano",
             "picante": "picante", "sin gluten": "sin gluten"}
NOISE = re.compile(
    r"(?i)(\btel\b|\btel[eé]fono|whats\s?app|\bwa\.me|https?://|www\.|@\w+\.\w|@\w{3,}|instagram|facebook|tiktok|"
    r"\bcalle\b.*\d|\bcarrera\b.*\d|\bcra\.?\s*\d|\bcll\.?\s*\d|\bav(enida|\.)\s*\w+.*\d|direcci[oó]n|horario|"
    r"\b3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}\b|\(?\+?57\)?\s?\d{3}|todos los derechos|propina)")


class Unreadable(Exception):
    """El archivo no se puede leer localmente. El mensaje es presentable al usuario."""


@dataclass
class Frag:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float = 0.0
    bold: bool = False
    page: int = 1
    is_price: bool = False
    value: float = 0.0
    col: int = 0

    @property
    def style(self):
        return (round(self.size), self.bold)


# ---------------------------------------------------------------- precios
_NUM = re.compile(r"(?<![\w.,/])(?P<cur>\$\s*|COP\s*|COL\$\s*)?(?P<num>\d{1,3}(?:[.,]\d{3})+(?![\d])|\d{3,6}(?![\d])|\d{1,3}[.,]\d{2}(?![\d])|\d{1,3}(?=\s*[kK](?![a-zA-ZáéíóúñÁÉÍÓÚÑ])))(?P<k>\s*[kK](?![a-zA-ZáéíóúñÁÉÍÓÚÑ]))?")
_UNITS = re.compile(r"^\s*(ml|cc|lt|lts|l\b|gr?s?\b|kg|oz|cm|mm|und|unds|unidades?|personas?|pax|porciones?|%|libras?|lb)", re.I)


def find_prices(text: str, decimals: int = 0) -> list[tuple[int, int, float]]:
    """Posiciones (inicio, fin, valor) de los precios dentro de un texto."""
    out = []
    for m in _NUM.finditer(text):
        raw = m.group("num")
        cur, k = bool(m.group("cur")), bool(m.group("k"))
        thousands = bool(re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw))
        decimal = bool(re.fullmatch(r"\d{1,3}[.,]\d{2}", raw)) and not thousands
        tail = text[m.end():]
        if _UNITS.match(tail):
            continue
        at_end = not re.sub(r"[\s.:·\-–—…_*)]+", "", tail)  # nada útil después del número
        if decimal and not (decimals == 2 and (cur or at_end)):
            continue
        if not (cur or thousands or k or decimal or at_end):
            continue  # un 400 suelto en medio de una descripción no es un precio
        digits = re.sub(r"[.,]", "", raw) if thousands else raw.replace(",", ".")
        val = float(digits) * (1000 if k else 1)
        if not decimal and val < (500 if decimals == 0 else 1):
            continue
        out.append((m.start(), m.end(), val))
    return out


_DESDE = re.compile(r"(?i)^\s*(desde|from|c/u|cu|x\s?und)\s*[:.]?\s*")


def _strip_desde(f: Frag):
    """'Desde $ 29.900' / 'c/u 5.000': la palabra que precede al precio no es parte del nombre."""
    m = _DESDE.match(f.text)
    if not m:
        return f
    rest = f.text[m.end():]
    if not rest.strip():
        return None
    if find_prices(rest) and find_prices(rest)[0][0] <= 1:
        f.text = rest
    return f


def _strip_leaders(s: str) -> str:
    return re.sub(r"^[\s.·:\-–—…_*]+|[\s.·:\-–—…_*$]+$", "", s)


def split_price_frags(frags: list[Frag], decimals: int) -> list[Frag]:
    """Un fragmento 'Nombre ...... $ 12.000' se parte en nombre + precio; un fragmento que solo es precio queda como precio."""
    out = []
    for f in frags:
        prices = find_prices(f.text, decimals)
        if not prices:
            out.append(f)
            continue
        width = max(f.x1 - f.x0, 1)
        n = max(len(f.text), 1)
        cursor = 0
        for (s, e, v) in prices:
            pre = _strip_leaders(f.text[cursor:s])
            if pre:
                out.append(Frag(pre, f.x0 + width * cursor / n, f.x0 + width * s / n, f.top, f.bottom, f.size, f.bold, f.page))
            out.append(Frag(f.text[s:e].strip(), f.x0 + width * s / n, f.x0 + width * e / n, f.top, f.bottom, f.size, f.bold, f.page, True, v))
            cursor = e
        rest = _strip_leaders(f.text[cursor:])
        if rest:
            out.append(Frag(rest, f.x0 + width * cursor / n, f.x1, f.top, f.bottom, f.size, f.bold, f.page))
    return out


# ---------------------------------------------------------------- columnas y filas
def find_cuts(frags: list[Frag], page_width: float) -> list[float]:
    """Posiciones x que separan columnas de platos. Solo se parte si cada columna tiene sus propios precios
    (así una tabla nombre | descripción | precio NO se parte)."""
    narrow = [f for f in frags if (f.x1 - f.x0) < 0.62 * page_width]
    prices = [f for f in narrow if f.is_price]
    if len(prices) < 6 or not narrow:
        return []
    width = int(page_width) + 2
    cover = [0] * width
    for f in narrow:
        for x in range(max(0, int(f.x0)), min(width, int(f.x1) + 1)):
            cover[x] += 1
    lo, hi = min(int(f.x0) for f in narrow), max(int(f.x1) for f in narrow)
    gutters, start = [], None
    for x in range(lo, hi + 2):
        free = x <= hi and cover[x] <= max(2, 0.03 * len(narrow))  # tolera títulos centrados que cruzan el hueco
        if free and start is None:
            start = x
        elif not free and start is not None:
            if x - start >= 14 and start > lo + 0.15 * (hi - lo) and x < hi - 0.15 * (hi - lo):
                gutters.append((start + x) / 2)
            start = None
    best = []
    for mask in range(1, 1 << min(len(gutters), 4)):
        cuts = [g for i, g in enumerate(gutters[:4]) if mask >> i & 1]
        groups = Counter(sum(1 for c in cuts if f.x0 >= c) for f in prices)
        if len(groups) == len(cuts) + 1 and all(v >= max(3, 0.15 * len(prices)) for v in groups.values()):
            if len(cuts) > len(best) and not _is_label_matrix(frags, cuts):
                best = cuts
    return best


def apply_cuts(frags: list[Frag], cuts: list[float], page_width: float) -> None:
    for f in frags:
        f.col = sum(1 for c in cuts if f.x0 >= c - 1 and (f.x0 + f.x1) / 2 >= c) if (f.x1 - f.x0) < 0.62 * page_width else 0


def cuts_fit_sparse_page(frags: list[Frag], cuts: list[float], page_width: float) -> bool:
    """¿Sirven los cortes del resto del documento en una página con pocos platos? Sí si hay precios a ambos lados
    de cada corte y casi nada de texto angosto lo cruza."""
    narrow = [f for f in frags if (f.x1 - f.x0) < 0.62 * page_width]
    prices = [f for f in narrow if f.is_price]
    sides = Counter(sum(1 for c in cuts if f.x0 >= c) for f in prices)
    crossing = sum(1 for f in narrow for c in cuts if f.x0 < c - 2 and f.x1 > c + 2)
    return len(sides) == len(cuts) + 1 and crossing <= 2


def detect_columns(frags: list[Frag], page_width: float) -> int:
    cuts = find_cuts(frags, page_width)
    apply_cuts(frags, cuts, page_width)
    return len(cuts) + 1


def _is_label_matrix(frags: list[Frag], cuts: list[float]) -> bool:
    """Columnas 'Personal | Mediana | Grande': el texto de las columnas extra se repite renglón tras renglón."""
    for k in range(1, len(cuts) + 1):
        texts = [f.text.strip().lower() for f in frags if not f.is_price and sum(1 for c in cuts if f.x0 >= c) == k]
        if len(texts) >= 3 and len(set(texts)) / len(texts) <= 0.5:
            return True
    return False


@dataclass
class Row:
    frags: list[Frag]
    col: int
    top: float
    bottom: float
    page: int

    @property
    def text(self):
        return " ".join(f.text for f in self.frags if not f.is_price).strip()

    @property
    def prices(self):
        return [f for f in self.frags if f.is_price]

    def split_inline_desc(self):
        """Fila tipo tabla 'nombre | descripción | precio' con UN precio: (nombre, descripción en línea)."""
        tf = [f for f in self.frags if not f.is_price]
        if len(tf) < 2 or len(self.prices) != 1:
            return self.text, ""
        size = max(self.size, 1)
        groups, cur = [], [tf[0]]
        for f in tf[1:]:
            if f.x0 - cur[-1].x1 >= 2.5 * size:
                groups.append(cur)
                cur = [f]
            else:
                cur.append(f)
        groups.append(cur)
        if len(groups) < 2:
            return self.text, ""
        join = lambda g: " ".join(f.text for f in g)  # noqa: E731
        return join(groups[0]).strip(), " ".join(join(g) for g in groups[1:]).strip()

    @property
    def size(self):
        t = [f for f in self.frags if not f.is_price] or self.frags
        return statistics.median(f.size for f in t)

    @property
    def bold(self):
        t = [f for f in self.frags if not f.is_price] or self.frags
        return sum(f.bold for f in t) > len(t) / 2

    @property
    def style(self):
        return (round(self.size), self.bold)


def build_rows(frags: list[Frag]) -> list[Row]:
    rows = []
    for col in sorted({f.col for f in frags}):
        cf = sorted((f for f in frags if f.col == col), key=lambda f: (f.top, f.x0))
        cur: list[Frag] = []
        for f in cf:
            if cur and abs(f.top - cur[0].top) <= 0.5 * max(f.size, cur[0].size, 1):
                cur.append(f)
            else:
                if cur:
                    rows.append(_mk_row(cur, col))
                cur = [f]
        if cur:
            rows.append(_mk_row(cur, col))
    return rows


def _mk_row(frags, col):
    frags = sorted(frags, key=lambda f: f.x0)
    return Row(frags, col, min(f.top for f in frags), max(f.bottom for f in frags), frags[0].page)


# ---------------------------------------------------------------- interpretación
def smart_title(s: str) -> str:
    letters = [c for c in s if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return s
    words = s.lower().split()
    return " ".join(w if (i and w in SMALL_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" \t-–—·:")


@dataclass
class Result:
    categories: list
    prices_found: int = 0
    unmatched_prices: int = 0
    no_price_items: int = 0
    variants: int = 0
    variants_extra: int = 0
    variants_unlabeled: int = 0
    pics: list = field(default_factory=list)  # fotos (WebP) usadas por algún plato, sin repetidas
    pics_use: Counter = field(default_factory=Counter)
    pics_total: int = 0
    pics_matched: int = 0
    warnings: list = field(default_factory=list)


def interpret(pages: list[list[Frag]], page_widths: list[float], decimals: int = 0, pics: list | None = None) -> Result:
    # 1) fragmentos → precios separados; descartar ruido (teléfonos, redes, direcciones...)
    all_rows: list[Row] = []
    prepared = []
    for pno, (frags, pw) in enumerate(zip(pages, page_widths), 1):
        frags = [f for f in frags if f.text.strip() and not NOISE.search(f.text)]
        frags = [g for g in (_strip_desde(f) for f in frags) if g is not None]
        frags = split_price_frags(frags, decimals)
        prepared.append((frags, pw, find_cuts(frags, pw)))
    # las páginas con pocos platos (p. ej. la última) heredan el corte de columnas del resto del documento
    known = [(pw, c) for _, pw, c in prepared if c]
    doc_rel = None  # posición relativa (0-1) de los cortes más frecuentes del documento
    if known:
        most = Counter(len(c) for _, c in known).most_common(1)[0][0]
        doc_rel = [statistics.median(c[i] / pw for pw, c in known if len(c) == most) for i in range(most)]
    for frags, pw, cuts in prepared:
        if not cuts and doc_rel is not None:
            guess = [r * pw for r in doc_rel]
            if cuts_fit_sparse_page(frags, guess, pw):
                cuts = guess
        apply_cuts(frags, cuts, pw)
        all_rows += build_rows(frags)
    res = Result([])
    price_rows = [r for r in all_rows if r.prices]
    res.prices_found = sum(len(r.prices) for r in price_rows)
    if not price_rows:
        return res

    # 2) estilos: el del nombre de plato = el del texto que acompaña a un precio
    name_styles = Counter(r.style for r in price_rows if r.text)
    if not name_styles:
        name_styles = Counter(r.style for r in price_rows)
    name_style = name_styles.most_common(1)[0][0]
    name_size = name_style[0] or 1
    has_style = len({r.style for r in all_rows}) > 1

    def is_heading(r: Row, prev_gap: float) -> bool:
        t = r.text
        if r.prices or not t or len(t.split()) > 6 or t.endswith((".", ",", ";")):
            return False
        letters = [c for c in t if c.isalpha()]
        upper = letters and sum(c.isupper() for c in letters) / len(letters) > 0.8
        if has_style:
            if r.size >= name_size * 1.15 + 0.4:
                return True
            if upper and r.size >= name_size * 0.95 and r.style != name_style:
                return True
            if r.bold and not name_style[1] and r.size >= name_size and len(t.split()) <= 4:
                return True
            return False
        return bool(upper or t.endswith(":") or prev_gap > 1.8 * max(r.size, 1) and len(t.split()) <= 3)

    # 3) recorrer cada columna de cada página con una pequeña máquina de estados
    headings, items = [], []
    order = sorted({(r.page, r.col) for r in all_rows})
    for page, col in order:
        rows = sorted((r for r in all_rows if r.page == page and r.col == col), key=lambda r: r.top)
        cur, pending, prev_bottom = None, [], None
        for r in rows:
            gap = (r.top - prev_bottom) if prev_bottom is not None else 0
            prev_bottom = r.bottom
            txt = _clean(r.text)
            inline_desc = ""
            if r.prices and txt:
                txt, inline_desc = r.split_inline_desc()
                txt = _clean(txt)
            if r.prices and txt:
                prefix, first = "", None
                if pending:  # texto previo sin precio con el mismo estilo del plato: parte del nombre
                    prefix = _clean(" ".join(p[0] for p in pending))
                    txt = _clean(prefix + " " + txt)
                    first = pending[0][2]
                    pending = []
                cur = _new_item(page, col, r, txt, prefix, first)
                cur["desc"] = _clean(inline_desc)
                items.append(cur)
            elif r.prices:  # fila que solo trae el precio
                if pending:
                    cur = _new_item(page, col, r, _clean(" ".join(p[0] for p in pending)), "", pending[0][2])
                    cur["closed"] = True
                    items.append(cur)
                    pending = []
                elif cur is not None and not cur["prices"]:
                    cur["prices"] = [f.value for f in r.prices]
                else:
                    res.unmatched_prices += len(r.prices)
            elif txt:
                if is_heading(r, gap):
                    if pending:
                        res.no_price_items += _flush_pending(items, pending, page, col, r)
                        pending = []
                    headings.append({"page": page, "col": col, "top": r.top, "name": smart_title(_clean(txt)), "size": r.size})
                    cur = None
                    continue
                tight = gap <= 1.3 * max(r.size, 1)
                last_word = (cur["name"].split() or [""])[-1].lower().strip(",") if cur else ""
                if cur is None:
                    same_style_cont = False
                elif has_style:
                    same_style_cont = r.style == cur["style"]
                else:
                    same_style_cont = last_word in CONNECTORS or cur["name"].endswith(",")
                if cur is not None and not cur["closed"] and not cur["desc"] and tight and same_style_cont:
                    cur["name"] = _clean(cur["name"] + " " + txt)  # nombre que se partió en dos renglones
                    cur["bottom"] = max(cur["bottom"], r.bottom)
                elif has_style and r.style == name_style:
                    pending.append((txt, r.style, r))  # estilo de nombre de plato: empieza un plato nuevo (su precio viene después o no tiene)
                    cur = None
                elif cur is not None:
                    cur["desc"] = _clean(cur["desc"] + " " + txt)
                    cur["bottom"] = max(cur["bottom"], r.bottom)
                elif pending and has_style:  # nombre sin precio seguido de descripción: plato sin precio
                    res.no_price_items += _flush_pending(items, pending, page, col, r)
                    cur = items[-1]
                    pending = []
                    cur["desc"] = _clean(txt)
                elif not has_style:
                    pending.append((txt, r.style, r))
        if pending:
            res.no_price_items += _flush_pending(items, pending, page, col, None)

    # 3b) fotos: cada plato recibe la foto que está pegada a su texto
    if pics:
        res.pics_total = len(pics)
        match = menu_images.match(items, pics, page_widths)
        keys: dict[str, int] = {}
        for i, j in match.items():
            g = pics[j]
            if g.key not in keys:
                keys[g.key] = len(res.pics)
                res.pics.append(g.webp)
            items[i]["pic"] = keys[g.key]
            res.pics_use[keys[g.key]] += 1
        res.pics_matched = len(match)

    # 4) un título grande suelto en la primera página (nombre del restaurante) no es una categoría
    if len(headings) >= 2 and headings[0]["page"] == 1:
        h0 = headings[0]
        if h0["size"] >= 1.5 * statistics.median(h["size"] for h in headings[1:]):
            headings.pop(0)
    # 5) categoría de cada plato: encabezado más cercano por encima, preferiendo el de su misma columna
    cats: dict[str, list] = {}
    order_names: list[str] = []
    hs = sorted(headings, key=lambda h: (h["page"], h["top"], h["col"]))
    for it in sorted(items, key=lambda i: (i["page"], i["col"], i["top"])):
        above = [h for h in hs if (h["page"], h["top"]) <= (it["page"], it["top"] + 1)]
        own = [h for h in above if h["col"] == it["col"]]
        pool = own if own and own[-1]["page"] == it["page"] else above
        if own and own[-1]["page"] != it["page"] and above and above[-1]["page"] == it["page"]:
            pool = above  # en esta página no hay título en su columna pero sí en otra: la banda cruza columnas
        name = pool[-1]["name"] if pool else "Carta"
        if name not in cats:
            cats[name] = []
            order_names.append(name)
        cats[name].append(it)
    for n in sorted(order_names, key=lambda n: min((h["page"], h["top"]) for h in hs if h["name"] == n) if any(h["name"] == n for h in hs) else (0, 0)):
        pass
    res.categories = [{"name": n, "items": [o for i in cats[n] for o in _item_out(i, res)]} for n in order_names]
    if len(res.categories) == 1 and res.categories[0]["name"] == res.categories[0]["items"][0]["name"]:
        res.categories[0]["name"] = "Carta"
    return res


def _new_item(page, col, r: Row, name: str, prefix: str = "", first: Row | None = None) -> dict:
    v = _row_variants(r)
    g = first or r  # el nombre puede empezar en un renglón anterior al del precio
    item = {"page": page, "col": col, "top": g.top, "name": name, "desc": "", "prices": [f.value for f in r.prices], "style": r.style,
            "variants": None, "closed": False, "x0": min(f.x0 for f in g.frags + r.frags), "x1": max(f.x1 for f in r.frags + g.frags),
            "bottom": max(g.bottom, r.bottom), "pic": None}
    if v:
        item["name"] = _clean(prefix + " " + v[0])
        item["variants"] = v[1]
    return item


def _row_variants(r: Row):
    """'Margarita   Personal 18.000   Grande 30.000' → ('Margarita', [('Personal', 18000), ('Grande', 30000)]) o None."""
    frs = r.frags
    idx = [i for i, f in enumerate(frs) if f.is_price]
    if len(idx) < 2:
        return None
    segs, prev = [], -1
    for i in idx:
        segs.append(frs[prev + 1:i])
        prev = i
    seg0 = segs[0]
    size = max(r.size, 1)
    if len(seg0) < 2 or (seg0[-1].x0 - seg0[-2].x1) < 1.5 * size:
        return None
    others = [_clean(" ".join(f.text for f in seg)) for seg in segs[1:]]
    if not all(others):
        return None
    name = _clean(" ".join(f.text for f in seg0[:-1]))
    pairs = [(_clean(seg0[-1].text), frs[idx[0]].value)] + [(o, frs[i].value) for o, i in zip(others, idx[1:])]
    return name, pairs


def _flush_pending(items, pending, page, col, row) -> int:
    g = pending[0][2]
    items.append({"page": page, "col": col, "top": g.top, "name": _clean(" ".join(p[0] for p in pending)), "desc": "", "prices": [],
                  "style": pending[0][1], "variants": None, "closed": True, "x0": min(f.x0 for f in g.frags), "x1": max(f.x1 for f in g.frags),
                  "bottom": g.bottom, "pic": None})
    return 1


def _item_out(it: dict, res: Result) -> list[dict]:
    desc = it["desc"]

    def tags_of(name):
        low = (name + " " + desc).lower()
        return sorted({v for k, v in TAG_WORDS.items() if re.search(r"\b" + re.escape(k) + r"\b", low)})
    if it["variants"]:  # tamaños: un plato por cada uno ("Margarita (Grande)")
        res.variants += 1
        res.variants_extra += len(it["variants"]) - 1
        return [{"name": smart_title(f"{it['name']} ({lab})")[:90], "description": desc[:400], "price": pr, "tags": tags_of(it["name"]), "image_idx": it.get("pic")}
                for lab, pr in it["variants"]]
    name = smart_title(it["name"])
    prices = it["prices"] or [0.0]
    if len(prices) > 1:  # varios precios sin etiquetas claras: se toma el primero y se conservan los demás en la descripción
        res.variants_unlabeled += 1
        res.variants_extra += len(prices) - 1
        desc = _clean(desc + " (Otros precios: " + " / ".join(f"{p:,.0f}".replace(",", ".") for p in prices[1:]) + ")")
    return [{"name": name[:90], "description": desc[:400], "price": prices[0], "tags": tags_of(name), "image_idx": it.get("pic")}]


# ---------------------------------------------------------------- PDF
def frags_from_pdf(data: bytes) -> tuple[list[list[Frag]], list[float]]:
    pages, widths, _ = read_pdf(data, want_images=False)
    return pages, widths


def read_pdf(data: bytes, want_images: bool = False) -> tuple[list[list[Frag]], list[float], list]:
    """Texto con posiciones y, si se pide, las fotos de la carta (una sola pasada por el PDF)."""
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine
        from pdfminer.pdfparser import PDFSyntaxError
    except ImportError:  # sin la librería instalada
        raise Unreadable("Falta instalar la librería de lectura de PDF (pdfminer.six).")
    pages, widths, pics = [], [], []
    try:
        for pno, page in enumerate(extract_pages(io.BytesIO(data), laparams=LAParams(line_margin=0.3, boxes_flow=None)), 1):
            frags = []
            if want_images and len(pics) < menu_images.MAX_PICS:
                pics += menu_images.pics_from_page(page, pno, menu_images.MAX_PICS - len(pics))
            for box in page:
                if not isinstance(box, LTTextContainer):
                    continue
                for ln in box:
                    if not isinstance(ln, LTTextLine):
                        continue
                    chars = [c for c in ln if isinstance(c, LTChar)]
                    txt = ln.get_text().replace("\n", " ").strip()
                    if not chars or not txt:
                        continue
                    size = sum(c.size for c in chars) / len(chars)
                    bold = sum(("bold" in c.fontname.lower() or "black" in c.fontname.lower() or "heavy" in c.fontname.lower()) for c in chars) > len(chars) / 2
                    frags.append(Frag(txt, ln.x0, ln.x1, page.height - ln.y1, page.height - ln.y0, size, bold, pno))
            pages.append(frags)
            widths.append(page.width)
    except (PDFSyntaxError, Exception) as e:  # PDF dañado o protegido
        raise Unreadable("No se pudo abrir el PDF (¿está dañado o tiene contraseña?).") from e
    return pages, widths, pics


# ---------------------------------------------------------------- DOCX y XLSX (solo biblioteca estándar)
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def frags_from_docx(data: bytes) -> tuple[list[list[Frag]], list[float]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        root = ET.fromstring(z.read("word/document.xml"))
    except Exception as e:
        raise Unreadable("No se pudo abrir el documento de Word.") from e
    frags: list[Frag] = []
    state = {"y": 0.0}

    def para_frags(p, x_base=0.0):
        style = p.find(f"{_W}pPr/{_W}pStyle")
        sname = (style.get(f"{_W}val") if style is not None else "") or ""
        heading = bool(re.search(r"(?i)heading|t[ií]tulo|title", sname))
        text_parts, bold_n, total_n, size = [], 0, 0, 0.0
        for r in p.iter(f"{_W}r"):
            t = "".join((n.text or "") if n.tag == f"{_W}t" else ("\t" if n.tag == f"{_W}tab" else "") for n in r)
            if not t:
                continue
            rpr = r.find(f"{_W}rPr")
            b = rpr is not None and rpr.find(f"{_W}b") is not None and rpr.find(f"{_W}b").get(f"{_W}val") not in ("0", "false")
            sz = rpr.find(f"{_W}sz") if rpr is not None else None
            if sz is not None:
                size = max(size, int(sz.get(f"{_W}val", "0")) / 2)
            text_parts.append(t)
            total_n += len(t)
            bold_n += len(t) if b else 0
        text = "".join(text_parts)
        return text, (bold_n > total_n / 2 if total_n else False) or heading, (size or (16 if heading else 10)) + (4 if heading and not size else 0)

    def emit(text, bold, size, x=0.0):
        parts = text.split("\t")
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                x0 = x + i * 250
                frags.append(Frag(part, x0, x0 + len(part) * size * 0.5, state["y"], state["y"] + size, size, bold))

    body = root.find(f"{_W}body")
    for el in list(body):
        if el.tag == f"{_W}p":
            text, bold, size = para_frags(el)
            if text.strip():
                emit(text, bold, size)
            state["y"] += 14
        elif el.tag == f"{_W}tbl":
            for tr in el.iter(f"{_W}tr"):
                for ci, tc in enumerate(tr.findall(f"{_W}tc")):
                    text = " ".join(para_frags(p)[0] for p in tc.iter(f"{_W}p")).strip()
                    if text:
                        _, bold, size = para_frags(next(tc.iter(f"{_W}p")))
                        frags.append(Frag(text, ci * 250, ci * 250 + len(text) * size * 0.5, state["y"], state["y"] + size, size, bold))
                state["y"] += 14
    return [frags], [max([f.x1 for f in frags] or [600]) + 20]


def rows_from_xlsx(data: bytes) -> list[list[str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        sheet = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))[0]
        out = []
        for row in ET.fromstring(z.read(sheet)).iter(f"{{{ns['m']}}}row"):
            cells = {}
            for c in row.findall("m:c", ns):
                col = re.match(r"[A-Z]+", c.get("r", "A1")).group(0)
                idx = 0
                for ch in col:
                    idx = idx * 26 + ord(ch) - 64
                v = c.find("m:v", ns)
                t = c.get("t")
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
                else:
                    val = (v.text or "") if v is not None else ""
                    if re.fullmatch(r"-?\d+\.0", val):
                        val = val[:-2]
                cells[idx] = val.strip()
            if cells:
                out.append([cells.get(i, "") for i in range(1, max(cells) + 1)])
        return out
    except Exception as e:
        raise Unreadable("No se pudo abrir el archivo de Excel.") from e


def read_xlsx(data: bytes, decimals: int) -> Result:
    rows = rows_from_xlsx(data)
    if not rows:
        raise Unreadable("La hoja de Excel está vacía.")
    csv_text = "\n".join(";".join(c.replace(";", ",") for c in r) for r in rows)
    draft = ai_import.parse_csv(csv_text)
    if draft["categories"] and any(i["price"] for c in draft["categories"] for i in c["items"]):
        n = sum(len(c["items"]) for c in draft["categories"])
        return Result(draft["categories"], prices_found=n)
    # sin encabezados reconocibles: cada fila es una fila de tabla
    frags, y = [], 0.0
    for r in rows:
        for ci, v in enumerate(r):
            if v:
                frags.append(Frag(v, ci * 250, ci * 250 + len(v) * 5, y, y + 10, 10))
        y += 14
    return interpret([frags], [max(f.x1 for f in frags) + 20 if frags else 600], decimals)


# ---------------------------------------------------------------- OCR (opcional)
def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return bool(shutil.which("tesseract") or __import__("os").getenv("TESSERACT_CMD"))


def frags_from_image(data: bytes) -> tuple[list[list[Frag]], list[float]]:
    """OCR con Tesseract: agrupa palabras en líneas y usa la altura como tamaño de letra."""
    if not ocr_available():
        raise Unreadable("Este archivo es una imagen y el servidor no tiene OCR instalado (Tesseract).")
    import os

    import pytesseract
    from PIL import Image, ImageOps
    if os.getenv("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    if img.width < 1400:  # ampliar mejora el OCR de fotos pequeñas
        k = 1400 / img.width
        img = img.resize((int(img.width * k), int(img.height * k)))
    langs = "spa+eng"
    try:
        d = pytesseract.image_to_data(img, lang=langs, config="--psm 4", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError:
        d = pytesseract.image_to_data(img, lang="eng", config="--psm 4", output_type=pytesseract.Output.DICT)
    return [_ocr_lines(d)], [float(img.width)]


def _ocr_lines(d: dict) -> list[Frag]:
    lines: dict[tuple, list] = {}
    for i, w in enumerate(d["text"]):
        if not str(w).strip() or float(d["conf"][i]) < 30:
            continue
        lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(i)
    frags = []
    for idxs in lines.values():
        # dentro de una línea, una separación grande entre palabras separa nombre y precio
        idxs.sort(key=lambda i: d["left"][i])
        group = [idxs[0]]
        groups = []
        for i in idxs[1:]:
            prev = group[-1]
            gap = d["left"][i] - (d["left"][prev] + d["width"][prev])
            if gap > 3.0 * max(d["height"][prev], 1):
                groups.append(group)
                group = [i]
            else:
                group.append(i)
        groups.append(group)
        for g in groups:
            txt = " ".join(str(d["text"][i]).strip() for i in g)
            x0, x1 = d["left"][g[0]], d["left"][g[-1]] + d["width"][g[-1]]
            top = min(d["top"][i] for i in g)
            h = statistics.median(d["height"][i] for i in g)
            frags.append(Frag(txt, x0, x1, top, top + h, h * 0.8, False))
    return frags


# ---------------------------------------------------------------- punto de entrada
def sniff_office(data: bytes, filename: str = "") -> str | None:
    if data[:2] != b"PK":
        return None
    try:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return "docx"
    if any(n.startswith("xl/worksheets/") for n in names):
        return "xlsx"
    return None


def acceptable(res: Result) -> bool:
    """¿Vale la pena mostrarle este borrador al dueño sin pasar por la IA?"""
    n = sum(len(c["items"]) for c in res.categories)
    if n < 3 or res.prices_found == 0:
        return False
    priced = n - res.no_price_items
    ok_count = priced + res.variants_extra >= 0.85 * res.prices_found
    return ok_count and res.unmatched_prices <= 0.1 * res.prices_found and res.no_price_items <= 0.15 * n and res.variants_unlabeled <= 0.2 * n


def read_local(data: bytes, kind: str, decimals: int = 0, with_images: bool = True) -> dict:
    """kind: 'pdf' | 'image' | 'docx' | 'xlsx'. Devuelve el borrador con 'source', 'warnings' y 'good'.
    Lanza Unreadable si el archivo no se puede leer localmente (p. ej. PDF escaneado sin OCR)."""
    if kind == "pdf":
        pages, widths, pics = read_pdf(data, want_images=with_images)
        chars = sum(len(f.text) for p in pages for f in p)
        if chars < 20 * max(len(pages), 1):
            raise Unreadable("Este PDF es una imagen escaneada (no trae texto) y el servidor no tiene OCR para leerlo.")
        res = interpret(pages, widths, decimals, pics)
    elif kind == "image":
        pages, widths = frags_from_image(data)
        res = interpret(pages, widths, decimals)
    elif kind == "docx":
        pages, widths = frags_from_docx(data)
        res = interpret(pages, widths, decimals)
    elif kind == "xlsx":
        res = read_xlsx(data, decimals)
    else:
        raise Unreadable("Tipo de archivo no soportado.")
    draft = ai_import.normalize_draft({"categories": res.categories})
    warns = []
    n = sum(len(c["items"]) for c in draft["categories"])
    if res.unmatched_prices:
        warns.append(f"{res.unmatched_prices} precio(s) no se pudieron asignar a un plato; revísalos.")
    if res.variants_unlabeled:
        warns.append(f"{res.variants_unlabeled} plato(s) tienen varios precios sin etiqueta; se tomó el primero y los demás quedaron en la descripción.")
    if res.variants:
        warns.append(f"{res.variants} plato(s) tienen tamaños; se creó un plato por cada tamaño, por ejemplo «Nombre (Grande)».")
    if res.no_price_items:
        warns.append(f"{res.no_price_items} plato(s) quedaron sin precio ($0); complétalos antes de publicar.")
    if res.pics_total and res.pics_matched < 0.5 * res.pics_total:
        warns.append(f"Se encontraron {res.pics_total} fotos pero solo {res.pics_matched} se pudieron asociar a un plato; revisa las fotos.")
    shared = sum(1 for k, v in res.pics_use.items() if v >= 3)
    if shared:
        warns.append(f"{shared} foto(s) se repiten en 3 o más platos (puede ser un marcador o un empaque): quítalas donde no correspondan.")
    good = acceptable(res) and n > 0
    return {"categories": draft["categories"], "source": "local", "warnings": warns, "good": good, "images": res.pics,
            "stats": {"prices_found": res.prices_found, "items": n, "pics": res.pics_total, "pics_matched": res.pics_matched}}
