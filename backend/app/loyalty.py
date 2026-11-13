"""Tarjeta de sellos de la fidelización: cada visita suma un sello al cliente y, al completar la tarjeta, gana el premio que eligió el dueño.
Cada cliente tiene un enlace personal (card_key) que abre su tarjeta; ese mismo enlace va en un QR o en una tarjeta NFC."""
import secrets

from fastapi import HTTPException

from . import auth, db
from .auth import now

COOLDOWN_HOURS = 3  # una visita = un sello: el equipo no puede sumar otro al mismo cliente antes de este tiempo (salvo el dueño)


def new_card_key() -> str:
    return secrets.token_urlsafe(9)


def find(r: dict, card: str = "", document: str = "") -> dict | None:
    """Cliente de este restaurante por el enlace de su tarjeta o por su cédula."""
    card = (card or "").strip()
    if card:
        row = db.row("SELECT * FROM customers WHERE restaurant_id=? AND card_key=? AND card_key<>''", (r["id"], card))
        if row and auth.safe_eq(row["card_key"], card):
            return row
    doc = "".join(ch for ch in (document or "") if ch.isdigit())
    if doc:
        return db.row("SELECT * FROM customers WHERE restaurant_id=? AND document=?", (r["id"], doc))
    return None


def ensure_key(c: dict) -> str:
    if not c["card_key"]:
        c["card_key"] = new_card_key()
        db.run("UPDATE customers SET card_key=? WHERE id=?", (c["card_key"], c["id"]))
    return c["card_key"]


def _on(r: dict):
    if not (r["stamps_on"] and auth.module_on(r, "customers")):
        raise HTTPException(400, "La tarjeta de sellos no está activa en este restaurante")


def state(r: dict, c: dict) -> dict:
    goal = max(2, int(r["stamps_goal"] or 8))
    n = int(c["stamps"])
    return {"name": c["name"], "stamps": n, "goal": goal, "filled": min(n, goal), "rewards": n // goal, "ready": n >= goal, "reward": r["stamps_reward"]}


def add_stamp(r: dict, c: dict, note: str = "", force: bool = False) -> dict:
    _on(r)
    if not force:
        last = db.row("SELECT created_at FROM stamp_log WHERE restaurant_id=? AND customer_id=? AND kind='stamp' ORDER BY id DESC LIMIT 1", (r["id"], c["id"]))
        if last:
            from datetime import datetime, timedelta
            fmt = "%Y-%m-%d %H:%M:%S"
            if datetime.strptime(last["created_at"], fmt) > datetime.strptime(now(), fmt) - timedelta(hours=COOLDOWN_HOURS):
                raise HTTPException(409, f"A {c['name'].split()[0]} ya se le sumó un sello hace menos de {COOLDOWN_HOURS} horas")
    db.run("UPDATE customers SET stamps=stamps+1 WHERE id=?", (c["id"],))
    db.run("INSERT INTO stamp_log(restaurant_id,customer_id,kind,delta,note,created_at) VALUES (?,?,?,?,?,?)", (r["id"], c["id"], "stamp", 1, note[:80], now()))
    return state(r, db.row("SELECT * FROM customers WHERE id=?", (c["id"],)))


def redeem(r: dict, c: dict, note: str = "") -> dict:
    _on(r)
    goal = max(2, int(r["stamps_goal"] or 8))
    if c["stamps"] < goal:
        raise HTTPException(409, f"Aún no completa la tarjeta: le faltan {goal - c['stamps']} sellos")
    db.run("UPDATE customers SET stamps=stamps-? WHERE id=? AND stamps>=?", (goal, c["id"], goal))
    db.run("INSERT INTO stamp_log(restaurant_id,customer_id,kind,delta,note,created_at) VALUES (?,?,?,?,?,?)", (r["id"], c["id"], "redeem", -goal, note[:80], now()))
    return state(r, db.row("SELECT * FROM customers WHERE id=?", (c["id"],)))
