"""Cuenta del dueño: recuperar y cambiar contraseña, aceptación de términos y borrado de la cuenta."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import auth, config, db, mailer, storage
from .auth import Staff, now, owner_dep, rate_limit
from .panel import _admin, _audit, _me, _set_cookie

router = APIRouter(prefix="/api")
log = logging.getLogger("mesaya.account")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


_ip = auth.client_ip


def _new_reset(restaurant_id: int) -> str:
    """Crea un enlace de un solo uso. Solo se guarda el hash del token."""
    token = secrets.token_urlsafe(32)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=config.RESET_TTL_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    db.run("DELETE FROM password_resets WHERE restaurant_id=?", (restaurant_id,))  # un solo enlace vigente
    db.run("INSERT INTO password_resets(token_hash, restaurant_id, expires_at) VALUES (?,?,?)", (_hash(token), restaurant_id, exp))
    return f"{config.BASE_URL}/reset?token={token}"


class ForgotIn(BaseModel):
    email: str = Field(max_length=120)


@router.post("/forgot")
def forgot(body: ForgotIn, request: Request):
    """Responde siempre igual: no revela si el correo tiene cuenta."""
    rate_limit(f"forgot:ip:{_ip(request)}", 5, 3600)
    email = body.email.strip().lower()
    rate_limit(f"forgot:mail:{email}", 3, 3600)
    r = db.row("SELECT id, name FROM restaurants WHERE email=?", (email,))
    if r:
        link = _new_reset(r["id"])
        sent = mailer.send(
            email, "Recupera tu contraseña de MesaYa",
            f"Hola,\n\nRecibimos una solicitud para cambiar la contraseña de {r['name']}.\n\n"
            f"Abre este enlace (vale {config.RESET_TTL_MINUTES} minutos y solo se puede usar una vez):\n{link}\n\n"
            "Si no fuiste tú, ignora este mensaje: tu contraseña no cambiará.\n")
        if not sent:
            log.warning("Recuperación solicitada para %s pero no hay SMTP configurado; usa /api/superadmin/reset-link", email)
    return {"ok": True, "message": "Si el correo tiene una cuenta, te enviamos un enlace para cambiar la contraseña."}


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=100)


@router.post("/reset")
def reset(body: ResetIn, request: Request, response: Response):
    rate_limit(f"reset:{_ip(request)}", 10, 3600)
    row = db.row("SELECT * FROM password_resets WHERE token_hash=? AND used_at IS NULL AND expires_at > ?",
                 (_hash(body.token), now()))
    if not row:
        raise HTTPException(400, "El enlace no es válido o ya venció. Solicita uno nuevo.")
    pw_hash = auth.hash_password(body.password)  # (scrypt tarda ~100 ms: fuera de la transacción)
    with db.tx(row["restaurant_id"]) as c:
        c.execute("UPDATE password_resets SET used_at=? WHERE token_hash=?", (now(), row["token_hash"]))
        c.execute("UPDATE restaurants SET password_hash=? WHERE id=?", (pw_hash, row["restaurant_id"]))
        c.execute("DELETE FROM sessions WHERE restaurant_id=?", (row["restaurant_id"],))  # cierra todas las sesiones abiertas
    _set_cookie(response, auth.create_session(row["restaurant_id"], "owner"))
    return _me(db.row("SELECT * FROM restaurants WHERE id=?", (row["restaurant_id"],)), "owner")


class ChangePwIn(BaseModel):
    current: str
    password: str = Field(min_length=8, max_length=100)


@router.post("/password")
def change_password(body: ChangePwIn, request: Request, response: Response, s: Staff = Depends(owner_dep)):
    rate_limit(f"chpw:{s.id}", 10, 3600)
    if not auth.verify_password(body.current, s.r["password_hash"]):
        raise HTTPException(400, "La contraseña actual no es correcta")
    keep = request.cookies.get(auth.COOKIE)
    pw_hash = auth.hash_password(body.password)
    with db.tx(s.id) as c:
        c.execute("UPDATE restaurants SET password_hash=? WHERE id=?", (pw_hash, s.id))
        c.execute("DELETE FROM sessions WHERE restaurant_id=? AND token != ?", (s.id, keep or ""))
    return {"ok": True}


@router.post("/accept-terms")
def accept_terms(s: Staff = Depends(owner_dep)):
    db.run("UPDATE restaurants SET terms_accepted_at=?, terms_version=? WHERE id=?", (now(), config.TERMS_VERSION, s.id))
    return {"ok": True}


class DeleteIn(BaseModel):
    password: str
    confirm: str


@router.post("/account/delete")
def delete_account(body: DeleteIn, request: Request, response: Response, s: Staff = Depends(owner_dep)):
    """Derecho de supresión (Ley 1581 de 2012): borra el restaurante y todos sus datos (carta, pedidos, opiniones, fotos)."""
    rate_limit(f"delacc:{s.id}", 5, 3600)
    if not auth.verify_password(body.password, s.r["password_hash"]):
        raise HTTPException(400, "La contraseña no es correcta")
    if body.confirm.strip().lower() != s.r["slug"]:
        raise HTTPException(400, f"Escribe «{s.r['slug']}» para confirmar")
    if storage.enabled():  # los archivos de Blob no caen por cascada: si no se pueden borrar, la cuenta tampoco (derecho de supresión)
        try:
            storage.delete_prefix(f"r{s.id}/")
        except Exception:
            log.exception("Blob: no se pudieron borrar los archivos de %s", s.r["slug"])
            raise HTTPException(503, "No pudimos borrar tus archivos, intenta de nuevo en unos minutos")
    db.run("DELETE FROM restaurants WHERE id=?", (s.id,))  # ON DELETE CASCADE limpia el resto: carta, fotos, borradores y partes
    response.delete_cookie(auth.COOKIE, path="/")
    log.info("Cuenta %s eliminada por su dueño", s.r["slug"])
    return {"ok": True}


@router.post("/superadmin/set-password")
def sa_set_password(body: dict, request: Request):
    """El superusuario fija una contraseña nueva a un negocio y cierra sus sesiones abiertas."""
    _admin(request)
    pw = str(body.get("password", ""))
    if not 8 <= len(pw) <= 100:
        raise HTTPException(400, "La contraseña debe tener entre 8 y 100 caracteres")
    email = str(body.get("email", "")).strip().lower()
    r = db.row("SELECT id FROM restaurants WHERE email=?", (email,))
    if not r:
        raise HTTPException(404, "No existe una cuenta con ese correo")
    pw_hash = auth.hash_password(pw)
    with db.tx(r["id"]) as c:
        c.execute("UPDATE restaurants SET password_hash=? WHERE id=?", (pw_hash, r["id"]))
        c.execute("DELETE FROM sessions WHERE restaurant_id=?", (r["id"],))
    _audit(request, email, "set-password")
    mailer.send(email, "Cambiaron la contraseña de tu cuenta de MesaYa",
                "Hola,\n\nEl equipo de soporte de MesaYa cambió la contraseña de tu cuenta y cerró tus sesiones abiertas.\n"
                "Si no lo pediste, respóndenos de inmediato.\n")
    return {"ok": True}


@router.post("/superadmin/reset-link")
def sa_reset_link(body: dict, request: Request):
    """Soporte: genera un enlace de recuperación para pasarlo por WhatsApp cuando no hay SMTP o el cliente no recibe el correo."""
    _admin(request)
    email = str(body.get("email", "")).strip().lower()
    r = db.row("SELECT id FROM restaurants WHERE email=?", (email,))
    if not r:
        raise HTTPException(404, "No existe una cuenta con ese correo")
    link = _new_reset(r["id"])
    _audit(request, email, "reset-link")
    mailer.send(email, "Soporte generó un enlace para cambiar tu contraseña",
                "Hola,\n\nEl equipo de soporte de MesaYa generó un enlace para cambiar la contraseña de tu cuenta. "
                "Si no lo pediste, respóndenos de inmediato.\n")
    return {"link": link, "expires_minutes": config.RESET_TTL_MINUTES}


@router.post("/subscription/cancel")
def cancel_subscription(s: Staff = Depends(owner_dep)):
    """Pide cancelar: sigue activa hasta que termine lo ya pagado y luego pasa al plan Gratis. No se borra nada."""
    if s.r["subscription_status"] != "active":
        raise HTTPException(400, "No tienes una suscripción activa")
    if not s.r["cancel_requested_at"]:
        if s.r["paid_until"]:
            db.run("UPDATE restaurants SET cancel_requested_at=? WHERE id=?", (now(), s.id))
        else:  # sin fecha de vencimiento no hay periodo pagado que respetar: pasa al plan Gratis ya
            db.run("UPDATE restaurants SET cancel_requested_at=?, subscription_status='inactive', trial_ends_at=? WHERE id=?", (now(), now(), s.id))
    return _me(db.row("SELECT * FROM restaurants WHERE id=?", (s.id,)), s.role)
