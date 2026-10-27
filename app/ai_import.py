"""Importar la carta en minutos a partir de lo que sube el restaurante: foto, PDF, texto pegado o CSV.

Proveedores de IA (visión): Gemini (GEMINI_API_KEY) o Claude (ANTHROPIC_API_KEY). Con MESAYA_AI_PROVIDER=auto
se usa Gemini si hay clave; si no, Claude. Sin ninguna clave siguen funcionando el texto pegado y los .txt/.csv.
La respuesta de la IA nunca se confía: `normalize_draft` la limpia y limita antes de mostrarla al dueño, que
revisa y confirma antes de que se agregue nada a su carta."""
import base64
import csv
import io
import json
import re
import time

import httpx

from . import config

PROMPT = """Eres un asistente que digitaliza cartas de restaurantes de Colombia. Extrae TODA la carta del documento adjunto
(puede tener varias páginas, columnas o fotos de pizarras) y responde SOLO con JSON válido con este formato exacto:
{"categories":[{"name":"Entradas","items":[{"name":"Arroz especial","description":"Con cerdo, pollo y camarón","price":24000,"tags":["popular"]}]}]}

Reglas:
- Agrupa los platos bajo la categoría que aparece en el documento (Entradas, Platos fuertes, Bebidas, Postres...). Si no hay categorías, usa "Carta".
- "price" es un NÚMERO sin símbolos ni separadores de miles: "$24.000" -> 24000, "24k" -> 24000, "12,5" -> 12.5. Si un plato tiene varios tamaños, crea un plato por tamaño ("Pizza grande") o usa el precio base. Si no hay precio legible usa 0.
- "description": ingredientes o aclaraciones que aparezcan impresas; vacío si no hay. No inventes nada.
- "tags": solo de esta lista y solo si el documento lo indica o es evidente: "vegano", "vegetariano", "picante", "sin gluten", "popular".
- Ignora teléfonos, direcciones, redes sociales, horarios y publicidad.
- No inventes platos ni precios. Conserva la ortografía del documento (corrige solo errores evidentes de lectura)."""

ALLOWED_TAGS = {"vegano", "vegetariano", "picante", "sin gluten", "popular"}
TAG_ALIASES = {"vegan": "vegano", "vegetarian": "vegetariano", "spicy": "picante", "gluten free": "sin gluten",
               "gluten-free": "sin gluten", "sin tacc": "sin gluten", "best seller": "popular", "recomendado": "popular"}
AI_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
TEXT_TYPES = {"text/plain", "text/csv"}


class AIError(RuntimeError):
    """Error presentable al usuario (nunca incluye claves ni respuestas crudas del proveedor)."""


# ---------------------------------------------------------------- utilidades
def _num(s) -> float:
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace("$", "").replace("COP", "").replace("USD", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):  # 12.000 / 12,000 -> miles
        return float(re.sub(r"[.,]", "", s))
    if re.fullmatch(r"\d+[kK]", s):
        return float(s[:-1]) * 1000
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def sniff_media_type(data: bytes, filename: str = "") -> str | None:
    """Decide el tipo por el CONTENIDO (no por lo que declare el navegador)."""
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    name = filename.lower()
    if name.endswith((".txt", ".csv", ".tsv")):
        head = data[:2000]
        if b"\x00" not in head:
            return "text/csv" if name.endswith((".csv", ".tsv")) else "text/plain"
    return None


def uses_ai(media_type: str) -> bool:
    return media_type in AI_TYPES


def provider() -> str | None:
    p = config.AI_PROVIDER
    if p == "gemini" and config.GEMINI_API_KEY:
        return "gemini"
    if p == "anthropic" and config.ANTHROPIC_API_KEY:
        return "anthropic"
    if p == "auto":
        if config.GEMINI_API_KEY:
            return "gemini"
        if config.ANTHROPIC_API_KEY:
            return "anthropic"
    return None


def ai_available() -> bool:
    return provider() is not None


def normalize_draft(raw) -> dict:
    """Valida y limpia lo que devuelve la IA: tipos, longitudes, etiquetas permitidas, precios numéricos."""
    cats_out = []
    cats = raw.get("categories", []) if isinstance(raw, dict) else []
    for c in (cats if isinstance(cats, list) else [])[:40]:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()[:60] or "Carta"
        items = []
        for it in (c.get("items", []) if isinstance(c.get("items"), list) else [])[:200]:
            if not isinstance(it, dict) or not str(it.get("name", "")).strip():
                continue
            tags = []
            for t in it.get("tags", []) if isinstance(it.get("tags"), list) else []:
                t = TAG_ALIASES.get(str(t).strip().lower(), str(t).strip().lower())
                if t in ALLOWED_TAGS and t not in tags:
                    tags.append(t)
            price = max(0.0, min(_num(it.get("price", 0)), 100_000_000))
            out_item = {"name": str(it["name"]).strip()[:90], "description": str(it.get("description", "") or "").strip()[:400],
                        "price": int(price) if price == int(price) else round(price, 2), "tags": tags}
            if isinstance(it.get("image_idx"), int) and it["image_idx"] >= 0:  # lo agrega el lector local de PDF
                out_item["image_idx"] = it["image_idx"]
            items.append(out_item)
        if items:
            cats_out.append({"name": name, "items": items})
    return {"categories": cats_out}


# ---------------------------------------------------------------- texto / CSV (sin IA)
def parse_text(text: str) -> dict:
    """Formato libre:
      # Entradas            (o una línea en MAYÚSCULAS / terminada en ':')
      Empanadas - 8.000 - Rellenas de carne
      Limonada | 6000
    """
    cats, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = re.match(r"^#+\s*(.+)$", line)
        if not head and (line.endswith(":") or (line.isupper() and len(line) > 2 and not re.search(r"\d{3}", line))):
            head = re.match(r"^(.+?):?$", line)
        if head:
            cur = {"name": head.group(1).strip().title(), "items": []}
            cats.append(cur)
            continue
        parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+|\t|;", line) if p.strip()]
        price, name = 0.0, parts[0]
        nums = [p for p in parts[1:] if re.fullmatch(r"\$?\s*[\d.,]+\s*(COP|USD)?", p)]
        others = [p for p in parts[1:] if p not in nums]
        if nums:
            price = _num(nums[0])
        else:
            m = re.search(r"\$?\s*(\d[\d.,]*)\s*$", parts[0])
            if m:
                price = _num(m.group(1))
                name = parts[0][: m.start()].strip(" -–—:")
        if not cur:
            cur = {"name": "Carta", "items": []}
            cats.append(cur)
        cur["items"].append({"name": name, "description": " · ".join(others), "price": price, "tags": []})
    return normalize_draft({"categories": [c for c in cats if c["items"]]})


def parse_csv(text: str) -> dict:
    """CSV con encabezados en cualquier orden: categoria, nombre/plato, precio, descripcion."""
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return {"categories": []}
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(head):
                if n in h:
                    return i
        return None
    ci, ni, pi, di = col("categor"), col("nombre", "plato", "producto", "name", "item"), col("precio", "price", "valor"), col("descrip")
    if ni is None or pi is None:  # sin encabezados reconocibles: tratar como texto libre
        return parse_text(text)
    cats: dict[str, list] = {}
    for r in rows[1:]:
        if len(r) <= max(ni, pi) or not r[ni].strip():
            continue
        cat = (r[ci].strip() if ci is not None and len(r) > ci else "") or "Carta"
        cats.setdefault(cat, []).append({"name": r[ni], "price": r[pi], "description": r[di] if di is not None and len(r) > di else "", "tags": []})
    return normalize_draft({"categories": [{"name": k, "items": v} for k, v in cats.items()]})


# ---------------------------------------------------------------- IA (visión)
def _post(url: str, **kw):
    """Único punto de salida HTTP (permite probar con respuestas simuladas)."""
    return httpx.post(url, timeout=kw.pop("timeout", 150), **kw)


def _json_from_text(txt: str):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
    try:
        return json.loads(txt)
    except ValueError:
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            raise AIError("La IA no devolvió una carta legible. Prueba con una foto más nítida o recta.")
        try:
            return json.loads(m.group(0))
        except ValueError:
            raise AIError("La IA devolvió una respuesta incompleta. Prueba con una foto más nítida o con menos páginas.")


def _gemini_call(model: str, body: dict):
    return _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                 headers={"x-goog-api-key": config.GEMINI_API_KEY, "content-type": "application/json"}, json=body, timeout=100)


def _error_info(r) -> dict:
    """Extrae de un error de Google: si es límite DIARIO del nivel gratuito y cuánto pide esperar."""
    info = {"daily": False, "retry_after": None, "message": ""}
    try:
        e = r.json().get("error", {})
    except Exception:
        return info
    info["message"] = str(e.get("message", ""))
    for d in e.get("details", []) if isinstance(e.get("details"), list) else []:
        for v in d.get("violations", []) if isinstance(d, dict) else []:
            if "perday" in str(v.get("quotaId", "")).lower().replace("_", "").replace("-", ""):
                info["daily"] = True
        delay = d.get("retryDelay") if isinstance(d, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                info["retry_after"] = float(delay[:-1])
            except ValueError:
                pass
    return info


def parse_with_gemini(data: bytes, media_type: str) -> dict:
    gen = {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 32768}
    if config.GEMINI_THINKING:  # "low" lee la carta en ~15 s en vez de 45-85 s con el mismo resultado
        gen["thinkingConfig"] = {"thinkingLevel": config.GEMINI_THINKING}
    body = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": media_type, "data": base64.b64encode(data).decode()}},
        {"text": PROMPT}]}], "generationConfig": gen}

    # Cada modelo tiene su propio cupo: si uno se agotó, se salta al siguiente sin esperar.
    models = [config.GEMINI_MODEL] + [m for m in config.GEMINI_FALLBACK_MODELS if m != config.GEMINI_MODEL]
    deadline = time.time() + config.AI_DEADLINE_SECONDS
    seen = {"daily": 0, "busy": 0, "limit": 0, "gone": 0, "net": 0}
    r = None
    for model in models:
        for attempt in range(3):
            if time.time() > deadline:
                break
            try:
                r = _gemini_call(model, body)
            except httpx.HTTPError:
                seen["net"] += 1
                r = None
                time.sleep(2)
                continue
            code = r.status_code
            if code == 200:
                break
            if code in (401, 403):
                raise AIError("La clave de IA no es válida o no tiene permiso. Revisa GEMINI_API_KEY.")
            info = _error_info(r)
            if code == 400 and "thinkingConfig" in gen and "think" in info["message"].lower():
                gen.pop("thinkingConfig")  # este modelo no admite ese ajuste: reintentar sin él
                continue
            if code == 429:
                if info["daily"]:
                    seen["daily"] += 1
                    break  # cupo diario agotado en este modelo: probar el siguiente ya
                seen["limit"] += 1
                time.sleep(min(info["retry_after"] or 10, 25))
                continue
            if code in (500, 502, 503, 504):
                seen["busy"] += 1
                time.sleep(3 * (attempt + 1))
                continue
            seen["gone"] += 1  # 400/404...: este modelo no sirve, probar el siguiente
            break
        if r is not None and r.status_code == 200:
            break
    if r is None or r.status_code != 200:
        if seen["daily"] and seen["daily"] >= len([m for m in models]) - seen["gone"]:
            raise AIError("Se agotó el cupo diario gratuito de la IA de Google. Inténtalo mañana, pega el texto de tu carta, "
                          "o activa la facturación en Google AI Studio para quitar el límite.")
        if seen["limit"] and not seen["busy"]:
            raise AIError("Se alcanzó el límite de uso por minuto de la IA. Espera un minuto e inténtalo de nuevo.")
        if seen["gone"] and not (seen["busy"] or seen["daily"] or seen["limit"]):
            raise AIError("El modelo de IA configurado ya no está disponible. Cambia MESAYA_GEMINI_MODEL por uno vigente.")
        raise AIError("La IA de Google está muy ocupada en este momento. Inténtalo de nuevo en unos minutos.")
    j = r.json()
    if j.get("promptFeedback", {}).get("blockReason"):
        raise AIError("La IA rechazó el archivo. Prueba con otra imagen de tu carta.")
    cands = j.get("candidates") or []
    if not cands:
        raise AIError("La IA no devolvió resultados. Intenta de nuevo.")
    if cands[0].get("finishReason") == "MAX_TOKENS":
        raise AIError("La carta es demasiado larga para leerla de una vez. Súbela por partes (por ejemplo, una página a la vez).")
    parts = cands[0].get("content", {}).get("parts", [])
    return _json_from_text("".join(p.get("text", "") for p in parts if not p.get("thought")))


def parse_with_claude(data: bytes, media_type: str) -> dict:
    block_type = "document" if media_type == "application/pdf" else "image"
    content = [
        {"type": block_type, "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}},
        {"type": "text", "text": PROMPT},
    ]
    r = _post("https://api.anthropic.com/v1/messages",
              headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
              json={"model": config.ANTHROPIC_MODEL, "max_tokens": 8000, "messages": [{"role": "user", "content": content}]})
    if r.status_code in (401, 403):
        raise AIError("La clave de IA no es válida o no tiene permiso. Revisa ANTHROPIC_API_KEY.")
    if r.status_code != 200:
        raise AIError("La IA no pudo procesar el archivo (error %d)." % r.status_code)
    return _json_from_text("".join(b.get("text", "") for b in r.json()["content"]))


def parse_file(data: bytes, media_type: str) -> dict:
    """Punto de entrada único: devuelve siempre un borrador normalizado {"categories": [...]}."""
    if media_type in TEXT_TYPES:
        text = data.decode("utf-8", errors="replace") if data[:3] != b"\xef\xbb\xbf" else data[3:].decode("utf-8", errors="replace")
        return parse_csv(text) if media_type == "text/csv" else parse_text(text)
    prov = provider()
    if prov is None:
        raise AIError("La lectura con IA no está configurada (falta GEMINI_API_KEY). Mientras tanto puedes pegar el texto de tu carta.")
    if media_type in ("image/jpeg", "image/png", "image/webp"):
        data, media_type = shrink_image(data, media_type)
    if len(data) > config.AI_MAX_BYTES:
        mb = len(data) / (1024 * 1024)
        raise AIError(f"El archivo ({mb:.0f} MB) es demasiado grande para la IA (máx. {config.AI_MAX_BYTES // (1024 * 1024)} MB). "
                      "Expórtalo en calidad media o con menos fotos, o súbelo en Word/Excel.")
    raw = parse_with_gemini(data, media_type) if prov == "gemini" else parse_with_claude(data, media_type)
    return normalize_draft(raw)


def shrink_image(data: bytes, media_type: str) -> tuple[bytes, str]:
    """Una foto de celular pesa 5-12 MB y la IA no necesita tanta resolución: se reduce a ~2400 px (más rápido y más liviano)."""
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if len(data) <= 3 * 1024 * 1024 and max(im.size) <= 3000:
            return data, media_type
        im.thumbnail((2400, 2400))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=88)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, media_type
