"""Recorrido completo de la importación de cartas: lector local primero, IA de respaldo.
Sin red (la IA se simula).  Requiere fpdf2:  pip install -r requirements-dev.txt   →   python -m tests.test_import_flow"""
import io
import os
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["GEMINI_API_KEY"] = "clave-falsa-de-prueba-123"
os.environ["MESAYA_AI_PROVIDER"] = "auto"
os.environ["MESAYA_MENU_READER"] = "auto"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ai_import, config, db, drafts, menu_reader  # noqa: E402
from app.main import app  # noqa: E402
from tests.menu_fixtures import (MENU, docx, layout_right_aligned, layout_sizes, layout_two_columns, layout_with_heavy_photo, layout_item_photos, xlsx)  # noqa: E402

ai_import.time.sleep = lambda s: None


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


AI_CALLS = []


class R:
    status_code = 200

    def json(self):
        import json
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(
            {"categories": [{"name": "De la IA", "items": [{"name": "Plato IA", "price": 11000}]}]})}]}}]}


ai_import._post = lambda url, **kw: (AI_CALLS.append(url), R())[1]


def upload(cl, name, data):
    db.run("DELETE FROM rate_hits")
    return cl.post("/api/import/ai", files={"file": (name, data)})


used = lambda: db.row("SELECT ai_imports_used n FROM restaurants WHERE email='r@x.co'")["n"]  # noqa: E731

scanned = io.BytesIO()
Image.new("RGB", (800, 600), "white").save(scanned, "PDF")
photo = io.BytesIO()
Image.new("RGB", (800, 600), "white").save(photo, "PNG")

with TestClient(app) as cl:
    cl.post("/api/signup", json={"accept_terms": True, "name": "Resto", "email": "r@x.co", "password": "secreto123", "tables": 1})

    # 1) PDF con texto: local, instantáneo, sin IA ni cuota (aunque la IA esté disponible)
    r = upload(cl, "carta.pdf", layout_two_columns())
    j = r.json()
    check(r.status_code == 200 and j["source"] == "local" and len(AI_CALLS) == 0 and used() == 0,
          "PDF con texto: 200 al instante, leído localmente, sin llamar a la IA ni gastar cuota")
    check(sum(len(c["items"]) for c in j["categories"]) == 7 and j["warnings"] == [], "PDF con texto: los 7 platos, sin avisos")
    check(cl.post("/api/import/commit", json=j).json()["added"] == 7, "el borrador local se puede confirmar igual que uno de IA")

    # 2) Word y Excel: siempre locales
    paras = []
    for cat, items in MENU:
        paras.append((cat, True, 16))
        for n, pr, d in items:
            paras.append((f"{n}\t$ {pr:,.0f}".replace(",", "."), True, 11))
    r = upload(cl, "carta.docx", docx(paras))
    check(r.status_code == 200 and r.json()["source"] == "local" and len(r.json()["categories"]) == 3, "Word (.docx): lectura local")
    xl = [("Categoría", "Plato", "Precio")] + [(c, n, pr) for c, items in MENU for n, pr, d in items]
    r = upload(cl, "carta.xlsx", xlsx(xl))
    check(r.status_code == 200 and r.json()["source"] == "local", "Excel (.xlsx): lectura local")
    r = upload(cl, "vacio.docx", docx([("Hola, esto no es una carta", False, 11)]))
    check(r.status_code == 422, "Word sin platos con precio: 422 con explicación (la IA no lee Word)")

    # 3) lectura local de baja confianza (PDF con tamaños SIN etiquetas claras) -> pasa a la IA
    # (layout_sizes sí se entiende: cada tamaño es un plato) ; usamos un PDF dañado como caso de "no se pudo leer"
    r = upload(cl, "roto.pdf", b"%PDF-1.4 esto no es un pdf valido")
    check(r.status_code == 200 and r.json()["source"] == "ai" and used() == 1,
          "PDF ilegible localmente + IA disponible: la IA de respaldo lo lee y descuenta 1 lectura")

    # 4) PDF escaneado: sin texto -> IA
    r = upload(cl, "escaneado.pdf", scanned.getvalue())
    check(r.status_code == 200 and r.json()["source"] == "ai", "PDF escaneado: no trae texto y pasa a la IA")

    # 5) foto: con IA se prefiere la IA (no se intenta OCR)
    r = upload(cl, "foto.png", photo.getvalue())
    check(r.status_code == 200 and r.json()["source"] == "ai", "foto + IA disponible: va directo a la IA")

    # 6) cuota agotada: el PDF con texto sigue funcionando (es local); el escaneado ya no
    db.run("UPDATE restaurants SET ai_imports_used=3 WHERE email='r@x.co'")
    r = upload(cl, "carta2.pdf", layout_right_aligned())
    check(r.status_code == 200 and r.json()["source"] == "local", "con la cuota de IA agotada, un PDF con texto se lee igual (local)")
    r = upload(cl, "escaneado.pdf", scanned.getvalue())
    check(r.status_code == 402, "con la cuota agotada, un PDF escaneado da 402 claro")
    db.run("UPDATE restaurants SET ai_imports_used=0 WHERE email='r@x.co'")

    # 7) sin IA configurada
    key = config.GEMINI_API_KEY
    config.GEMINI_API_KEY = ""
    AI_CALLS.clear()
    r = upload(cl, "carta.pdf", layout_two_columns())
    check(r.status_code == 200 and r.json()["source"] == "local", "SIN IA configurada: el PDF con texto se lee igual")
    r = upload(cl, "escaneado.pdf", scanned.getvalue())
    check(r.status_code == 422 and "escaneada" in r.json()["error"] and "Word" in r.json()["error"], "sin IA: el PDF escaneado explica qué hacer (Word, Excel, PDF con texto o pegar texto)")
    r = upload(cl, "foto.png", photo.getvalue())
    check(r.status_code == 422 and not AI_CALLS, "sin IA ni OCR: una foto da 422 claro (no se queda colgada)")
    me = cl.get("/api/me").json()
    check(me["ai_available"] is False and "ocr_available" in me and me["menu_reader"] == "auto", "el panel sabe qué lectores hay")

    # 8) PDF de tamaños: se entiende localmente
    r = upload(cl, "pizzas.pdf", layout_sizes())
    check(r.status_code == 200 and len(r.json()["categories"][0]["items"]) == 12 and any("tamaños" in w for w in r.json()["warnings"]), "PDF con tamaños: un plato por tamaño, con aviso")

    # 9) modos
    config.GEMINI_API_KEY = key
    AI_CALLS.clear()
    config.MENU_READER = "ai"
    r = upload(cl, "carta.pdf", layout_two_columns())
    check(r.status_code == 200 and r.json()["source"] == "ai", "MESAYA_MENU_READER=ai: el PDF va siempre a la IA")
    config.MENU_READER = "local"
    AI_CALLS.clear()
    r = upload(cl, "escaneado.pdf", scanned.getvalue())
    check(r.status_code == 422 and not AI_CALLS, "MESAYA_MENU_READER=local: nunca se llama a la IA")
    config.MENU_READER = "auto"

    # 10) archivos pesados (PDF con fotos): antes se rechazaba todo lo que pasara de 10 MB
    big = layout_with_heavy_photo(14.0)
    check(len(big) > 12 * 1024 * 1024, f"(PDF de prueba con fotos: {len(big) / 1048576:.1f} MB)")
    r = upload(cl, "carta-con-fotos.pdf", big)
    check(r.status_code == 200 and r.json()["source"] == "local" and sum(len(c["items"]) for c in r.json()["categories"]) == 7,
          "PDF de más de 10 MB con fotos: se lee igual (local) con los 7 platos")
    old_limit = config.MAX_IMPORT_MB
    config.MAX_IMPORT_MB = 1
    r = upload(cl, "gigante.pdf", big)
    check(r.status_code == 413 and "1 MB" in r.json()["error"] and "calidad media" in r.json()["error"], "sobre el límite configurado: 413 con el límite y qué hacer")
    config.MAX_IMPORT_MB = old_limit
    check(cl.get("/api/me").json()["max_import_mb"] == old_limit, "el panel conoce el límite (para avisar antes de subir)")

    # 11) la IA no recibe archivos que no caben en su petición
    old_ai = config.AI_MAX_BYTES
    config.AI_MAX_BYTES = 500
    r = upload(cl, "escaneado.pdf", scanned.getvalue())
    check(r.status_code == 502 and "demasiado grande para la IA" in r.json()["error"], "archivo demasiado grande para la IA: mensaje claro, sin gastar cuota")
    config.AI_MAX_BYTES = old_ai

    # 13) fotos de los platos dentro del PDF
    me_id = db.row("SELECT id FROM restaurants WHERE email='r@x.co'")["id"]
    r = upload(cl, "carta-con-fotos-de-platos.pdf", layout_item_photos("left", two_columns=True))
    j = r.json()
    items = [i for c in j["categories"] for i in c["items"]]
    check(r.status_code == 200 and j["source"] == "local" and j.get("draft_id") and "images" not in j and "good" not in j,
          "PDF con fotos de platos: 200, borrador con draft_id y SIN bytes de imagen en el JSON")
    check(len(items) == 7 and all(i.get("image") and i.get("image_ref") and "image_idx" not in i for i in items),
          "cada plato trae su miniatura (URL) y su referencia")
    url = items[0]["image"]
    pv = cl.get(url)
    check(pv.status_code == 200 and pv.headers["content-type"] == "image/webp" and pv.content[:4] == b"RIFF", "la vista previa de la foto se sirve como WebP")
    stranger = TestClient(app)
    stranger.post("/api/signup", json={"accept_terms": True, "name": "Otro", "email": "otro@x.co", "password": "secreto123", "tables": 1})
    check(stranger.get(url).status_code == 404, "otro restaurante no puede ver las fotos de mi borrador")
    check(TestClient(app).get(url).status_code == 401, "sin sesión no se ven las fotos del borrador")
    check(drafts.read(me_id, "../../etc", 0) is None and drafts.read(me_id, j["draft_id"], "../../x") is None and drafts.read(me_id, j["draft_id"], -1) is None,
          "ids con rutas maliciosas (../) se rechazan")

    first_name = items[2]["name"]
    del items[2]["image"], items[2]["image_ref"]  # el dueño quita una foto equivocada
    r = cl.post("/api/import/commit", json=j)
    check(r.json() == {"added": 7, "photos": 6}, "al confirmar: 7 platos, 6 con foto (la quitada no se guarda)")
    menu = {i["name"]: i for c in cl.get("/api/menu").json()["categories"] for i in c["items"]}
    with_img = [i for i in menu.values() if i["image"]]
    imgs_of = lambda: {r["name"] for r in db.rows("SELECT name FROM images")}  # noqa: E731
    check(len(with_img) == 6 and menu[first_name]["image"] == "" and all(i["image"].rsplit("/", 1)[-1] in imgs_of() for i in with_img),
          "las fotos quedan guardadas en la base y ligadas a su plato")
    check(cl.get(url).status_code == 404, "el borrador (y sus fotos temporales) se elimina al confirmar")
    pub = TestClient(app).get(with_img[0]["image"])
    check(pub.status_code == 200 and pub.content[:4] == b"RIFF" and "immutable" in pub.headers["cache-control"], "/uploads sirve la foto desde la base, pública y cacheable")

    # cambiar o borrar un plato limpia su foto de la base
    solo = with_img[0]
    png = io.BytesIO()
    Image.new("RGB", (60, 60), "red").save(png, "PNG")
    r = cl.post(f"/api/items/{solo['id']}/image", files={"file": ("f.png", png.getvalue())})
    new_name = r.json()["image"].rsplit("/", 1)[-1]
    check(r.status_code == 200 and solo["image"].rsplit("/", 1)[-1] not in imgs_of() and new_name in imgs_of(), "cambiar la foto de un plato borra la anterior de la base")
    cl.delete(f"/api/items/{solo['id']}")
    check(new_name not in imgs_of(), "borrar el plato borra su foto")

    # una foto repetida en varios platos se guarda una sola vez
    j2 = cl.post("/api/import/ai", files={"file": ("c.pdf", layout_item_photos("left"))}).json()
    a_item = [i for c in j2["categories"] for i in c["items"]]
    for it in a_item[1:4]:
        it["image_ref"] = a_item[0]["image_ref"]
    before = len(imgs_of())
    cl.post("/api/import/commit", json=j2)
    check(len(imgs_of()) - before == 4, "la misma foto usada en 4 platos se guarda 1 vez (más 3 fotos propias)")
    shared = db.row("SELECT image, MIN(id) AS id FROM items WHERE image != '' GROUP BY image HAVING COUNT(*) = 4")
    cl.delete(f"/api/items/{shared['id']}")
    check(shared["image"].rsplit("/", 1)[-1] in imgs_of(), "borrar un plato que comparte su foto con otros no la borra")

    # referencias falsas o ajenas no copian nada
    j3 = {"categories": [{"name": "Prueba", "items": [{"name": "X", "price": 1000, "image_ref": ["abcdefghijkl", 0]},
                                                      {"name": "Y", "price": 1000, "image_ref": [j["draft_id"], 999]}, {"name": "Z", "price": 1000, "image_ref": "basura"}]}]}
    before = len(imgs_of())
    check(cl.post("/api/import/commit", json=j3).json()["photos"] == 0 and len(imgs_of()) == before, "referencias de fotos inválidas se ignoran sin copiar nada")

    # carta grande subida por partes (una petición a Vercel admite 4,5 MB)
    raw = layout_two_columns()
    cut = len(raw) // 3
    uid = "subida-de-prueba-123"
    for n, part in enumerate((raw[:cut], raw[cut:2 * cut], raw[2 * cut:])):
        check(cl.post("/api/import/chunk", data={"upload_id": uid, "n": n}, files={"file": ("p", part)}).status_code == 200, f"parte {n + 1}/3 recibida")
    check(stranger.post("/api/import/ai", data={"upload_id": uid, "filename": "c.pdf"}).status_code == 400, "otro restaurante no puede reunir mis partes")
    r = cl.post("/api/import/ai", data={"upload_id": uid, "filename": "c.pdf"})
    check(r.status_code == 200 and r.json()["source"] == "local" and sum(len(c["items"]) for c in r.json()["categories"]) == 7,
          "carta por partes: se reúne y se lee igual que una subida directa")
    check(db.row("SELECT COUNT(*) n FROM import_chunks")["n"] == 0, "las partes se borran al reunirlas")
    check(cl.post("/api/import/chunk", data={"upload_id": "x", "n": 0}, files={"file": ("p", b"1")}).status_code == 400, "id de subida inválido → 400")
    check(cl.post("/api/import/chunk", data={"upload_id": uid, "n": 0}, files={"file": ("p", b"0" * (4 * 1024 * 1024 + 1))}).status_code == 413, "una parte de más de 4 MB → 413")

    # caducidad y limpieza
    j4 = cl.post("/api/import/ai", files={"file": ("c.pdf", layout_item_photos("left"))}).json()
    n_of = lambda d: db.row("SELECT COUNT(*) n FROM draft_images WHERE draft_id=?", (d,))["n"]  # noqa: E731
    db.run("UPDATE draft_images SET created_at=? WHERE draft_id=?", (time.time() - 4 * 3600, j4["draft_id"]))
    drafts.purge()
    check(n_of(j4["draft_id"]) == 0, "un borrador abandonado se elimina a las 3 horas")
    j5 = cl.post("/api/import/ai", files={"file": ("c.pdf", layout_item_photos("left"))}).json()
    check(n_of(j5["draft_id"]) > 0, "(un borrador nuevo sí existe)")
    cl.post("/api/account/delete", json={"password": "secreto123", "confirm": "resto"})
    check(n_of(j5["draft_id"]) == 0 and db.row("SELECT COUNT(*) n FROM images WHERE restaurant_id=?", (me_id,))["n"] == 0,
          "al borrar la cuenta se eliminan también sus borradores y todas sus fotos")

# 12) reducción de fotos pesadas antes de enviarlas a la IA
import os as _os  # noqa: E402

noisy = Image.frombytes("RGB", (3200, 2400), _os.urandom(3200 * 2400 * 3))
jb = io.BytesIO()
noisy.save(jb, "JPEG", quality=95)
out, mt = ai_import.shrink_image(jb.getvalue(), "image/jpeg")
im = Image.open(io.BytesIO(out))
check(len(jb.getvalue()) > 3 * 1024 * 1024 and max(im.size) <= 2400 and len(out) < len(jb.getvalue()),
      f"foto pesada ({len(jb.getvalue()) / 1048576:.1f} MB): se reduce a {im.size} ({len(out) / 1048576:.1f} MB) antes de ir a la IA")
small, _ = ai_import.shrink_image(photo.getvalue(), "image/png")
check(small == photo.getvalue(), "una foto liviana no se toca")

print("\nImportación de cartas ✔")
