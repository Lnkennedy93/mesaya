"""Lectura de cartas (sin red: las respuestas de Gemini se simulan).   python -m tests.test_ai"""
import json
import os
import tempfile
import threading
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["GEMINI_API_KEY"] = "clave-falsa-de-prueba-123"  # evita usar la real del .env
os.environ["MESAYA_AI_PROVIDER"] = "auto"

from fastapi.testclient import TestClient  # noqa: E402

from app import ai_import, config  # noqa: E402
from app.main import app  # noqa: E402

SLEPT = []
ai_import.time.sleep = lambda s: SLEPT.append(s)  # sin esperas reales; registramos cuánto se pidió esperar


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


class R:
    def __init__(self, status, data=None):
        self.status_code, self._d = status, data or {}

    def json(self):
        return self._d


def gemini_ok(draft):
    return R(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"thought": True, "text": "pensando..."},
                                                                                 {"text": json.dumps(draft)}]}}]})


def daily_429():
    return R(429, {"error": {"message": "quota", "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
        {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}})


def minute_429(delay="7s"):
    return R(429, {"error": {"message": "slow down", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}})


def model_of(url):
    return url.split("/models/")[1].split(":")[0]


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50
PDF = b"%PDF-1.4 " + b"0" * 50
DRAFT = {"categories": [{"name": "Entradas", "items": [
    {"name": "Empanadas", "description": "De carne", "price": "8.000", "tags": ["Vegan", "radioactivo"]},
    {"name": "Patacones", "price": 12000.0, "tags": ["vegetariano"]}, {"name": "", "price": 5}, "basura"]}, {"name": "Vacía", "items": []}, 7]}

# --- utilidades
check(ai_import.sniff_media_type(PNG) == "image/png" and ai_import.sniff_media_type(PDF) == "application/pdf", "el tipo se detecta por el contenido")
check(ai_import.sniff_media_type(b"MZ\x90\x00 programa.exe", "carta.png") is None, "un ejecutable disfrazado de imagen se rechaza")
check(ai_import.sniff_media_type(b"Arepa;5000", "carta.csv") == "text/csv", "reconoce .csv")
n = ai_import.normalize_draft(DRAFT)
it = n["categories"][0]["items"]
check(len(n["categories"]) == 1 and len(it) == 2, "limpia basura: categorías vacías, platos sin nombre y tipos raros")
check(it[0]["price"] == 8000 and it[0]["tags"] == ["vegano"], "«8.000» → 8000 y solo etiquetas permitidas (vegan → vegano)")
check(ai_import.normalize_draft("no es dict") == {"categories": []}, "una respuesta inesperada no rompe")
csv_txt = "Categoría;Plato;Precio;Descripción\nEntradas;Empanadas;8.000;De carne\nBebidas;Limonada;$ 6.500;\n"
c = ai_import.parse_csv(csv_txt)
check([x["name"] for x in c["categories"]] == ["Entradas", "Bebidas"] and c["categories"][1]["items"][0]["price"] == 6500, "CSV con encabezados en cualquier orden")

# --- Gemini simulado: petición
CALLS = []


def post_ok(url, **kw):
    CALLS.append((url, kw))
    return gemini_ok(DRAFT)


ai_import._post = post_ok
res = ai_import.parse_file(PNG, "image/png")
url, kw = CALLS[0]
check("gemini-3.5-flash:generateContent" in url and kw["headers"]["x-goog-api-key"] == config.GEMINI_API_KEY, "usa el modelo principal y envía la clave por cabecera")
check(config.GEMINI_API_KEY not in url, "la clave no va en la URL")
gc = kw["json"]["generationConfig"]
check(gc["responseMimeType"] == "application/json" and gc["thinkingConfig"] == {"thinkingLevel": "low"}, "pide JSON y razonamiento bajo (lectura 3-5 veces más rápida)")
check(len(res["categories"][0]["items"]) == 2, "ignora las partes de «pensamiento» y normaliza la respuesta")

# --- resiliencia
seq = []


def run_seq(handler):
    seq.clear()
    SLEPT.clear()
    ai_import._post = lambda url, **kw: (seq.append(model_of(url)) or handler(model_of(url), kw))
    return ai_import.parse_file(PNG, "image/png")


run_seq(lambda m, kw: daily_429() if m == "gemini-3.5-flash" else gemini_ok(DRAFT))
check(seq == ["gemini-3.5-flash", "gemini-3.5-flash-lite"] and not SLEPT, "cupo DIARIO agotado: pasa al siguiente modelo al instante, sin esperar ni reintentar")

try:
    run_seq(lambda m, kw: daily_429())
except ai_import.AIError as e:
    check("cupo diario" in str(e) and "facturación" in str(e) and len(seq) == 3, "cupo diario agotado en todos: mensaje claro con la salida (mañana / activar facturación)")

state = {"n": 0}


def minute_then_ok(m, kw):
    state["n"] += 1
    return minute_429("7s") if state["n"] == 1 else gemini_ok(DRAFT)


run_seq(minute_then_ok)
check(seq == ["gemini-3.5-flash", "gemini-3.5-flash"] and SLEPT == [7.0], "límite por MINUTO: espera lo que pide Google (7 s) y reintenta el mismo modelo")

state["n"] = 0


def busy_twice(m, kw):
    state["n"] += 1
    return R(503, {"error": {"status": "UNAVAILABLE"}}) if state["n"] <= 2 else gemini_ok(DRAFT)


run_seq(busy_twice)
check(seq == ["gemini-3.5-flash"] * 3 and SLEPT == [3, 6], "alta demanda (503): reintenta con espera creciente")

try:
    run_seq(lambda m, kw: R(503, {}))
except ai_import.AIError as e:
    check("muy ocupada" in str(e) and len(seq) == 9, "si todo está saturado: 3 intentos por modelo y mensaje amable")

state["n"] = 0
bodies = []


def no_thinking(m, kw):
    bodies.append("thinkingConfig" in kw["json"]["generationConfig"])
    return R(400, {"error": {"message": "Thinking level is not supported for this model"}}) if "thinkingConfig" in kw["json"]["generationConfig"] else gemini_ok(DRAFT)


run_seq(no_thinking)
check(bodies == [True, False], "si un modelo no admite el ajuste de razonamiento, reintenta sin él")

for code, fragment in ((403, "GEMINI_API_KEY"),):
    try:
        run_seq(lambda m, kw: R(code, {"error": {"message": "API key not valid: " + config.GEMINI_API_KEY}}))
    except ai_import.AIError as e:
        check(fragment in str(e) and config.GEMINI_API_KEY not in str(e), "clave inválida: mensaje claro sin filtrar la clave")
try:
    run_seq(lambda m, kw: R(404, {"error": {"message": "no longer available"}}))
except ai_import.AIError as e:
    check("MESAYA_GEMINI_MODEL" in str(e), "modelos retirados: el mensaje dice qué variable cambiar")
try:
    run_seq(lambda m, kw: R(200, {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}]}))
except ai_import.AIError as e:
    check("por partes" in str(e), "carta demasiado larga: sugiere subirla por partes")
run_seq(lambda m, kw: R(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "```json\n" + json.dumps(DRAFT) + "\n```"}]}}]}))
check(True, "tolera JSON envuelto en bloque de código")

# --- endpoint: la lectura con IA corre dentro de la petición (Vercel no tiene hilos de fondo)
ai_import._post = post_ok


def ai_post(cl, name, data, ctype=None):
    """Sube un archivo. Devuelve (estado, cuerpo)."""
    r = cl.post("/api/import/ai", files={"file": (name, data, ctype) if ctype else (name, data)})
    return r.status_code, r.json()


with TestClient(app) as cl:
    cl.post("/api/signup", json={"accept_terms": True, "name": "Cafe IA", "email": "ia@x.co", "password": "secreto123", "tables": 1})
    me = cl.get("/api/me").json()
    check(me["ai_available"] and me["ai_provider"] == "gemini", "el panel sabe que hay IA (Gemini)")
    check(cl.post("/api/import/ai", files={"file": ("a.exe", b"MZ\x90\x00 virus")}).status_code == 400, "archivo no permitido → 400")
    r = cl.post("/api/import/ai", files={"file": ("carta.png", PNG, "text/plain")})
    check(r.status_code == 200 and r.json()["source"] == "ai" and len(r.json()["categories"][0]["items"]) == 2,
          "foto/PDF: se lee con IA y responde con el borrador (aunque el navegador declare otro tipo)")

    before = len(CALLS)
    st, body = ai_post(cl, "carta.csv", csv_txt.encode())
    check(st == 200 and len(CALLS) == before, "el .csv se lee al instante, sin IA ni cuota")
    st, body = ai_post(cl, "vacio.csv", b"nada;util\n1;2\n")
    check(st in (200, 422), "un archivo sin platos no rompe")
    used = lambda: __import__("app.db", fromlist=["x"]).row("SELECT ai_imports_used n FROM restaurants WHERE email='ia@x.co'")["n"]  # noqa: E731
    check(used() == 1, "solo la foto descontó una lectura del plan")

    ai_import._post = lambda url, **kw: R(503, {})
    st, body = ai_post(cl, "c.pdf", PDF)
    check(st == 502 and "ocupada" in body["error"] and used() == 1, "si la IA falla, el dueño ve el motivo y no se descuenta la cuota")

    ai_import._post = post_ok
    check(ai_post(cl, "c1.pdf", PDF)[0] == 200 and used() == 2, "una segunda lectura con IA descuenta otra del plan")
    from app import db as _db
    _db.run("DELETE FROM rate_hits")  # reinicia el límite de ritmo (8 subidas / 10 min) para medir solo la cuota del plan
    ai_post(cl, "c.pdf", PDF)
    check(used() == 3 and ai_post(cl, "c.pdf", PDF)[0] == 402, "el plan Esencial permite 3 lecturas con IA")
    check(any(cl.post("/api/import/ai", files={"file": ("x.csv", b"a;1")}).status_code == 429 for _ in range(10)), "límite de ritmo: no se puede inundar el endpoint")
    cl.post("/api/logout")
    check(cl.post("/api/import/ai", files={"file": ("c.png", PNG)}).status_code == 401, "sin sesión no se puede usar")
    config.GEMINI_API_KEY = ""
    _db.run("DELETE FROM rate_hits")
    cl.post("/api/login", json={"email": "ia@x.co", "password": "secreto123"})
    check(cl.post("/api/import/ai", files={"file": ("c.png", PNG)}).status_code == 422 and not cl.get("/api/me").json()["ai_available"], "sin clave ni OCR: una foto da 422 con explicación y el panel lo sabe")

print("\nLectura de cartas ✔")
