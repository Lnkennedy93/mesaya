"""Asistente del dueño (sin red: Gemini se simula).   python -m tests.test_assistant"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["MESAYA_DB"] = str(tmp / "t.db")
from tests import isolate  # noqa: E402,F401  (PostgreSQL: esquema temporal)
os.environ["MESAYA_UPLOADS"] = str(tmp / "up")
os.environ["MESAYA_ADMIN_KEY"] = "k"
os.environ["GEMINI_API_KEY"] = "clave-falsa-de-prueba-123"

from fastapi.testclient import TestClient  # noqa: E402

from app import ai_import, assistant, db  # noqa: E402
from app.main import app  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


class R:
    def __init__(self, status, data=None):
        self.status_code, self._d = status, data or {}

    def json(self):
        return self._d


def model_turn(*parts):
    return R(200, {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": list(parts)}}]})


def call(name, **args):
    return {"functionCall": {"name": name, "args": args}}


sent = []      # cuerpos enviados a Google
script = []    # respuestas que devolverá el "modelo", en orden


def fake_post(url, **kw):
    sent.append(kw["json"])
    return script.pop(0)


ai_import._post = fake_post


def signup(c, name, email):
    r = c.post("/api/signup", json={"accept_terms": True, "name": name, "email": email, "password": "secreto123", "tables": 2})
    return r.json()["restaurant"]["slug"]


def order(c, slug, item_id, qty, diner, name="Ana", table=0):
    t = c.get("/api/tables").json()["tables"][table]
    r = c.post(f"/api/public/{slug}/orders", json={"table": t["label"], "key": t["secret"], "diner_id": diner, "diner_name": name,
                                                      "items": [{"item_id": item_id, "qty": qty}]})
    check(r.status_code == 200, f"pedido de {qty} creado")


with TestClient(app) as c, TestClient(app) as other:
    slug = signup(c, "Café Uno", "uno@b.co")
    c.post("/api/import/commit", json=c.post("/api/import/text", json={"text": "# Platos\nEmpanadas - 8.000\nLimonada - 6.500\nSopa - 12.000\n"}).json())
    items = {i["name"]: i["id"] for cat in c.get("/api/menu").json()["categories"] for i in cat["items"]}

    # otro restaurante con ventas propias: no debe aparecer en las cifras del primero
    slug2 = signup(other, "Café Dos", "dos@b.co")
    other.post("/api/import/commit", json=other.post("/api/import/text", json={"text": "# Platos\nEmpanadas - 99.000\n"}).json())
    order(other, slug2, other.get("/api/menu").json()["categories"][0]["items"][0]["id"], 5, "zz")

    # plan de prueba (Esencial): sin asistente
    r = c.post("/api/assistant", json={"question": "¿Cuánto vendí hoy?"})
    check(r.status_code == 402 and "Pro" in r.json()["error"], "Esencial/prueba: asistente bloqueado con aviso de plan")
    check(not sent, "sin plan no se llama a Google")

    check(c.post("/api/superadmin/activate", headers={"x-admin-key": "k"}, json={"plan": "pro", "email": "uno@b.co"}).status_code == 200, "plan Pro activado")
    order(c, slug, items["Empanadas"], 2, "d1")
    order(c, slug, items["Sopa"], 1, "d2")

    # tiempos de cocina conocidos: espera 2 min, preparación 10 min
    for o in c.get("/api/orders").json()["orders"]:
        t0 = db.row("SELECT created_at FROM orders WHERE id=?", (o["id"],))["created_at"]
        a = datetime.strptime(t0, FMT)
        db.run("UPDATE orders SET preparing_at=?, ready_at=? WHERE id=?", ((a + timedelta(minutes=2)).strftime(FMT), (a + timedelta(minutes=12)).strftime(FMT), o["id"]))

    # --- una pregunta completa: el modelo pide 3 herramientas y luego responde
    script[:] = [
        model_turn(call("ventas"), call("platos", nombre="empan"), call("proponer_disponibilidad", nombre="Limonada", disponible=False)),
        model_turn({"thought": True, "text": "pensando"}, {"text": "Vendiste 2 empanadas."}),
    ]
    r = c.post("/api/assistant", json={"question": "¿Cuántas empanadas vendí y apaga la limonada?"})
    check(r.status_code == 200 and r.json()["answer"] == "Vendiste 2 empanadas.", "respuesta final del modelo (sin su razonamiento)")
    check(r.json()["actions"] == [{"item_id": items["Limonada"], "name": "Limonada", "available": False}], "apagar plato llega como propuesta")
    check(db.row("SELECT available FROM items WHERE id=?", (items["Limonada"],))["available"] == 1, "la propuesta NO cambia la carta")
    check(r.json()["asks_left"] == 299, "descuenta una pregunta del cupo mensual")

    res = {p["functionResponse"]["name"]: p["functionResponse"]["response"]["result"] for p in sent[1]["contents"][-1]["parts"]}
    check(res["ventas"]["pedidos"] == 2 and res["ventas"]["dinero_pedido"] == 28000, "ventas: 2 pedidos, $28.000 (no mezcla el otro restaurante)")
    check(res["platos"]["total_unidades"] == 2 and res["platos"]["platos"][0]["plato"] == "Empanadas", "platos: filtra por nombre")
    check(sent[0]["contents"][0]["parts"][0]["text"].startswith("¿Cuántas") and "Café Uno" in sent[0]["systemInstruction"]["parts"][0]["text"], "contexto del restaurante en el mensaje del sistema")
    check("restaurant_id" not in str(sent[0]["tools"]), "el modelo no puede elegir el restaurante")
    check("thoughtSignature" not in str(sent[0]) and sent[1]["contents"][-2]["role"] == "model", "se devuelve el turno del modelo antes de las respuestas de herramientas")

    # --- herramientas sueltas
    s = type("S", (), {})()
    s.id, s.r = db.row("SELECT id FROM restaurants WHERE email='uno@b.co'")["id"], db.row("SELECT * FROM restaurants WHERE email='uno@b.co'")
    k = assistant.t_cocina(s, {}, [])
    check(k["min_espera_hasta_empezar"] == 2.0 and k["min_preparacion"] == 10.0 and k["min_total_hasta_listo"] == 12.0 and k["pedidos_de_mas_de_20_min"] == 0, "cocina: 2 min de espera, 10 de preparación, 12 en total")
    cm = assistant.t_comensales(s, {}, [])
    check(cm["comensales"] == 2 and cm["pedidos"] == 2 and cm["por_mesa"] == [{"mesa": "1", "comensales": 2, "pedidos": 2, "platos": 3}], "comensales: 2 personas en la mesa 1, con sus pedidos y platos")
    order(c, slug, items["Sopa"], 2, "d1", name="Ana")              # la misma persona vuelve a pedir: no suma
    order(c, slug, items["Sopa"], 1, "d1", name="Luis")             # mismo celular, otro nombre: otra persona
    order(c, slug, items["Sopa"], 1, "d9", name="luis", table=1)    # otra mesa: otra persona
    cm = assistant.t_comensales(s, {}, [])
    mesas = {m["mesa"]: m["comensales"] for m in cm["por_mesa"]}
    check(cm["comensales"] == 4 and mesas == {"1": 3, "2": 1} and cm["por_dia"][0]["comensales"] == 4, "comensales: se distingue por nombre, celular y mesa")
    check("ana" not in str(cm).lower() and "luis" not in str(cm).lower(), "los nombres de los clientes no salen hacia el modelo")
    menos = assistant.t_platos(s, {"orden": "menos"}, [])
    check(menos["sin_ventas_en_el_rango"] == ["Limonada"], "menos vendidos incluye platos sin ventas")
    check("Las fechas" in assistant.run_tool(s, "ventas", {"desde": "ayer"}, [])["error"], "fecha mal escrita: error legible para el modelo")
    check("Rango inválido" in assistant.run_tool(s, "ventas", {"desde": "2024-01-01", "hasta": "2026-01-01"}, [])["error"], "rango de más de un año rechazado")
    check(assistant.run_tool(s, "borrar_todo", {}, []) == {"error": "Herramienta desconocida"}, "herramienta inventada rechazada")
    acts = []
    check("coincidencias" not in assistant.t_proponer(s, {"nombre": "zzz", "disponible": False}, acts) and not acts, "plato inexistente: sin propuesta")

    # --- confirmar con el botón (endpoint existente) deja historial
    check(c.post(f"/api/items/{items['Limonada']}/availability", json={"available": False}).status_code == 200, "dueño confirma: se apaga")
    c.post(f"/api/items/{items['Limonada']}/availability", json={"available": False})  # repetido: no es un cambio
    d = assistant.t_desactivados(s, {}, [])
    check(d["apagados_ahora"][0]["plato"] == "Limonada" and len(d["historial"]) == 1 and d["veces_apagado_en_el_rango"] == {"Limonada": 1}, "desactivados: historial de un solo cambio")
    check(assistant.t_proponer(s, {"nombre": "limonada", "disponible": False}, acts)["nota"].endswith("no se propone nada."), "ya apagado: no se propone nada")

    # --- seguimiento (historial) y límite mensual
    script[:] = [model_turn({"text": "Sí."})]
    c.post("/api/assistant", json={"question": "¿y ayer?", "history": [{"role": "assistant", "text": "huérfano"}, {"role": "user", "text": "hola"}, {"role": "assistant", "text": "hola!"}]})
    roles = [m["role"] for m in sent[-1]["contents"]]
    check(roles == ["user", "model", "user"], "historial: empieza por el usuario y alterna")
    db.run("UPDATE restaurants SET ai_asks_used=300, ai_asks_month=? WHERE id=?", (datetime.now(timezone.utc).strftime("%Y-%m"), s.id))
    n = len(sent)
    check(c.post("/api/assistant", json={"question": "otra"}).status_code == 402 and len(sent) == n, "cupo mensual agotado: 402 sin llamar a Google")
    db.run("UPDATE restaurants SET ai_asks_month='2020-01' WHERE id=?", (s.id,))
    script[:] = [model_turn({"text": "ok"})]
    check(c.post("/api/assistant", json={"question": "nuevo mes"}).json()["asks_left"] == 299, "el cupo se reinicia con el mes")

    # --- fallos del proveedor
    script[:] = [R(503), R(503), R(503)]
    r = c.post("/api/assistant", json={"question": "¿hoy?"})
    check(r.status_code == 502 and "no está disponible" in r.json()["error"], "Google caído: mensaje presentable")
    check(db.row("SELECT ai_asks_used FROM restaurants WHERE id=?", (s.id,))["ai_asks_used"] == 1, "una pregunta fallida no descuenta del cupo")
    script[:] = [R(200, {"candidates": [{"content": {"parts": [call("ventas")]}}]})] * 6
    check(c.post("/api/assistant", json={"question": "bucle"}).status_code == 502, "modelo que nunca termina: corta tras 5 rondas")

    # --- permisos
    c.post("/api/logout")
    check(c.post("/api/assistant", json={"question": "hola"}).status_code == 401, "sin sesión: 401")
    me = other.post("/api/login", json={"email": "dos@b.co", "password": "secreto123"}).json()
    c.post("/api/staff-login", json={"slug": slug2, "pin": me["restaurant"]["staff_pin"]})
    check(c.post("/api/assistant", json={"question": "hola"}).status_code == 403, "la cocina no puede usar el asistente")

print("\nTodo OK")
