"""Tareas largas en segundo plano (leer una carta grande con IA puede tardar 1-2 minutos).
En memoria y de un solo proceso, igual que el tiempo real. El cliente consulta el avance con un id."""
import secrets
import threading
import time

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
TTL = 1800  # 30 min


def _cleanup():
    now = time.time()
    for k in [k for k, v in _jobs.items() if now - v["created"] > TTL]:
        _jobs.pop(k, None)


def running_for(restaurant_id: int) -> bool:
    with _lock:
        return any(j["restaurant_id"] == restaurant_id and j["status"] == "running" for j in _jobs.values())


def start(restaurant_id: int, fn, *args) -> str:
    """Ejecuta fn(*args) en un hilo. fn devuelve el resultado o lanza un error con mensaje presentable."""
    job_id = secrets.token_urlsafe(12)
    with _lock:
        _cleanup()
        _jobs[job_id] = {"restaurant_id": restaurant_id, "status": "running", "created": time.time(), "result": None, "error": None}

    def run():
        try:
            res = fn(*args)
            out = {"status": "done", "result": res}
        except Exception as e:  # el mensaje de AIError ya es presentable; el resto se oculta
            msg = str(e) if e.__class__.__name__ == "AIError" else "No se pudo leer la carta, intenta con otro archivo."
            out = {"status": "error", "error": msg}
        with _lock:
            _jobs[job_id].update(out)

    threading.Thread(target=run, daemon=True, name=f"job-{job_id[:6]}").start()
    return job_id


def get(job_id: str, restaurant_id: int) -> dict | None:
    with _lock:
        j = _jobs.get(job_id)
        if not j or j["restaurant_id"] != restaurant_id:  # un restaurante nunca ve los trabajos de otro
            return None
        return {"status": j["status"], "result": j["result"], "error": j["error"], "elapsed": round(time.time() - j["created"])}
