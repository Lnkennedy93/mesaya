import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    """Carga ROOT/.env si existe (desarrollo local). No pisa variables que ya estén definidas en el entorno."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v


_load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("MESAYA_DB", ROOT / "data" / "mesaya.db"))
# Con MESAYA_DATABASE_URL (postgresql://usuario:clave@host:5432/base) MesaYa usa PostgreSQL en vez de SQLite.
DATABASE_URL = os.getenv("MESAYA_DATABASE_URL", "").strip()
PG_POOL_MAX = int(os.getenv("MESAYA_PG_POOL_MAX", "20"))
# Esquema de PostgreSQL (por defecto "public"). "auto" crea uno temporal: lo usan las pruebas.
PG_SCHEMA = os.getenv("MESAYA_PG_SCHEMA", "").strip()
UPLOAD_DIR = Path(os.getenv("MESAYA_UPLOADS", ROOT / "uploads"))
WEB_DIR = ROOT / "web"

ENV = os.getenv("MESAYA_ENV", "development")  # "production" activa las validaciones de arranque
BASE_URL = os.getenv("MESAYA_BASE_URL", "http://localhost:8000").rstrip("/")
TRIAL_DAYS = int(os.getenv("MESAYA_TRIAL_DAYS", "14"))
ADMIN_KEY = os.getenv("MESAYA_ADMIN_KEY", "")  # activa suscripciones desde tu backoffice
# --- IA para leer la carta desde foto/PDF (auto: usa Gemini si hay GEMINI_API_KEY; si no, Anthropic)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Google retiró los 2.5 para cuentas nuevas y los modelos más nuevos suelen estar saturados: principal estable + respaldos
GEMINI_MODEL = os.getenv("MESAYA_GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("MESAYA_GEMINI_FALLBACK", "gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",") if m.strip()]
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("MESAYA_AI_MODEL", "claude-sonnet-5-5")
GEMINI_THINKING = os.getenv("MESAYA_GEMINI_THINKING", "low")  # minimal | low | medium | high ("" = ajuste del modelo)
AI_DEADLINE_SECONDS = int(os.getenv("MESAYA_AI_DEADLINE", "170"))  # tiempo máximo total (reintentos y respaldos incluidos)
# Cómo se lee la carta que sube el restaurante: auto = local primero (PDF con texto, Word, Excel) y IA de respaldo;
# local = nunca usar IA; ai = siempre IA para PDF/fotos.
MENU_READER = os.getenv("MESAYA_MENU_READER", "auto")
AI_PROVIDER = os.getenv("MESAYA_AI_PROVIDER", "auto")  # auto | gemini | anthropic
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
DEMO_MODE = os.getenv("MESAYA_DEMO", "0") == "1"  # habilita el pago simulado: NUNCA en producción
# Funciones apagadas por ahora (el producto base es: pedir -> cocina -> terminar mesa).
# Para reactivarlas: MESAYA_ONLINE_PAYMENTS=1 (Nequi / Bre-B / tarjeta) y MESAYA_INVOICING=1 (factura electronica).
ONLINE_PAYMENTS = os.getenv("MESAYA_ONLINE_PAYMENTS", "0") == "1"
INVOICING = os.getenv("MESAYA_INVOICING", "0") == "1"
SECURE_COOKIES = BASE_URL.startswith("https")

# Fotos de platos y logo: se redimensionan a WebP, así que se acepta el peso típico de una foto de celular
MAX_UPLOAD_BYTES = int(os.getenv("MESAYA_MAX_PHOTO_MB", "20")) * 1024 * 1024
# Archivo de carta (PDF con fotos, Word, Excel...). Un PDF de menú con fotos a todo color pasa fácil de 15 MB.
MAX_IMPORT_MB = int(os.getenv("MESAYA_MAX_IMPORT_MB", "30"))
# Gemini admite ~20 MB por petición (el archivo viaja en base64, +33 %): por encima de esto no se envía a la IA
AI_MAX_BYTES = 14 * 1024 * 1024

# --- datos de TU empresa: aparecen en Términos y Política de datos
COMPANY = {
    "name": os.getenv("MESAYA_COMPANY_NAME", "[RAZÓN SOCIAL DEL PROVEEDOR]"),
    "nit": os.getenv("MESAYA_COMPANY_NIT", "[NIT]"),
    "address": os.getenv("MESAYA_COMPANY_ADDRESS", "[DIRECCIÓN]"),
    "city": os.getenv("MESAYA_COMPANY_CITY", "[CIUDAD], Colombia"),
    "email": os.getenv("MESAYA_COMPANY_EMAIL", "[CORREO PARA PETICIONES, QUEJAS Y RECLAMOS]"),
    "phone": os.getenv("MESAYA_COMPANY_PHONE", "[TELÉFONO / WHATSAPP]"),
}
TERMS_VERSION = "2026-10-27"  # súbela cuando cambies Términos o Política: se vuelve a pedir aceptación

# --- correo saliente (recuperar contraseña). Sin SMTP el dueño recibe el enlace por soporte (ver README)
SMTP_HOST = os.getenv("MESAYA_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("MESAYA_SMTP_PORT", "587"))
SMTP_USER = os.getenv("MESAYA_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("MESAYA_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("MESAYA_SMTP_FROM", SMTP_USER)
RESET_TTL_MINUTES = 60

# --- copias de seguridad
BACKUP_DIR = Path(os.getenv("MESAYA_BACKUP_DIR", ROOT / "data" / "backups"))
BACKUP_EVERY_HOURS = float(os.getenv("MESAYA_BACKUP_EVERY_HOURS", "24"))  # 0 = desactivadas
BACKUP_KEEP = int(os.getenv("MESAYA_BACKUP_KEEP", "14"))
BACKUP_HOOK = os.getenv("MESAYA_BACKUP_HOOK", "")  # comando opcional tras cada copia, ej. rclone para subirla a la nube

PLANS = {
    "basic": {"name": "Esencial", "tables": 15, "ai_imports": 3},
    "pro": {"name": "Pro", "tables": 60, "ai_imports": 50},
    "chain": {"name": "Cadena", "tables": 500, "ai_imports": 500},
}


def production_problems() -> list[str]:
    """Errores de configuración que NO deben llegar a producción."""
    p = []
    if not BASE_URL.startswith("https://"):
        p.append("MESAYA_BASE_URL debe empezar por https:// (los QR y las cookies seguras dependen de ello)")
    if "localhost" in BASE_URL or "127.0.0.1" in BASE_URL:
        p.append("MESAYA_BASE_URL apunta a localhost")
    if len(ADMIN_KEY) < 20:
        p.append("MESAYA_ADMIN_KEY debe tener al menos 20 caracteres")
    if not os.getenv("MESAYA_SECRET_KEY"):
        p.append("Define MESAYA_SECRET_KEY (clave Fernet) para no depender de un archivo en disco")
    if DEMO_MODE:
        p.append("MESAYA_DEMO=1 habilita pagos simulados: desactívalo")
    if any(v.startswith("[") for v in COMPANY.values()):
        p.append("Completa los datos de tu empresa (MESAYA_COMPANY_*): salen en Términos y Política de datos")
    if not SMTP_HOST:
        p.append("Sin SMTP la recuperación de contraseña solo funciona por soporte (aviso, no bloquea)")
    return p


def blocking_problems() -> list[str]:
    return [x for x in production_problems() if not x.startswith("Sin SMTP")]
