import sqlite3
import json
from contextlib import closing, contextmanager
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  staff_pin TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'COP',
  decimals INTEGER NOT NULL DEFAULT 0,
  brand_color TEXT NOT NULL DEFAULT '#e4572e',
  tagline TEXT DEFAULT '',
  logo TEXT DEFAULT '',
  tip_pct INTEGER NOT NULL DEFAULT 10,
  tax_pct REAL NOT NULL DEFAULT 0,
  tax_included INTEGER NOT NULL DEFAULT 1,
  tz_offset INTEGER NOT NULL DEFAULT -300,
  google_review_url TEXT DEFAULT '',
  whatsapp TEXT DEFAULT '',
  accepting_orders INTEGER NOT NULL DEFAULT 1,
  online_payments INTEGER NOT NULL DEFAULT 1,
  plan TEXT NOT NULL DEFAULT 'basic',
  subscription_status TEXT NOT NULL DEFAULT 'trial',
  trial_ends_at TEXT NOT NULL,
  ai_imports_used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  price INTEGER NOT NULL,
  image TEXT DEFAULT '',
  available INTEGER NOT NULL DEFAULT 1,
  featured INTEGER NOT NULL DEFAULT 0,
  tags TEXT NOT NULL DEFAULT '[]',
  allergens TEXT NOT NULL DEFAULT '[]',
  options TEXT NOT NULL DEFAULT '[]',
  sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tables_ (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  secret TEXT NOT NULL,
  UNIQUE(restaurant_id, label)
);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  table_label TEXT NOT NULL,
  seq INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  diner_id TEXT DEFAULT '',
  diner_name TEXT DEFAULT '',
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  preparing_at TEXT,
  ready_at TEXT,
  served_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_r ON orders(restaurant_id, status, created_at);
CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  item_id INTEGER,
  name TEXT NOT NULL,
  options_text TEXT DEFAULT '',
  note TEXT DEFAULT '',
  qty INTEGER NOT NULL,
  unit_price INTEGER NOT NULL,
  paid_payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  table_label TEXT NOT NULL,
  type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  table_label TEXT NOT NULL,
  provider TEXT NOT NULL,
  status TEXT NOT NULL,
  subtotal INTEGER NOT NULL,
  tip INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL,
  payer TEXT DEFAULT '',
  item_ids TEXT NOT NULL DEFAULT '[]',
  external_ref TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
  token_hash TEXT PRIMARY KEY,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  payment_id INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  number TEXT DEFAULT '',
  cufe TEXT DEFAULT '',
  qr_url TEXT DEFAULT '',
  public_url TEXT DEFAULT '',
  customer TEXT NOT NULL DEFAULT '{}',
  total INTEGER NOT NULL DEFAULT 0,
  error TEXT DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  issued_at TEXT,
  UNIQUE(payment_id)
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  table_label TEXT DEFAULT '',
  rating INTEGER NOT NULL,
  comment TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# Columnas añadidas después de la v1 (se aplican también a bases existentes).
MIGRATIONS = {
    "restaurants": {
        "legal_name": "TEXT NOT NULL DEFAULT ''",
        "nit": "TEXT NOT NULL DEFAULT ''",
        "nit_dv": "TEXT NOT NULL DEFAULT ''",
        "tax_type": "TEXT NOT NULL DEFAULT 'NONE'",
        "fiscal_address": "TEXT NOT NULL DEFAULT ''",
        "fiscal_phone": "TEXT NOT NULL DEFAULT ''",
        "fiscal_municipality_id": "INTEGER NOT NULL DEFAULT 0",
        "inv_provider": "TEXT NOT NULL DEFAULT 'none'",
        "inv_env": "TEXT NOT NULL DEFAULT 'sandbox'",
        "inv_range_id": "INTEGER NOT NULL DEFAULT 0",
        "inv_secrets": "TEXT NOT NULL DEFAULT ''",
        "wompi_env": "TEXT NOT NULL DEFAULT 'sandbox'",
        "pay_secrets": "TEXT NOT NULL DEFAULT ''",
        "nequi_enabled": "INTEGER NOT NULL DEFAULT 0",
        "breb_enabled": "INTEGER NOT NULL DEFAULT 0",
        "breb_key": "TEXT NOT NULL DEFAULT ''",
        "breb_key_type": "TEXT NOT NULL DEFAULT 'celular'",
        "breb_holder": "TEXT NOT NULL DEFAULT ''",
        "terms_accepted_at": "TEXT",
        "terms_version": "TEXT NOT NULL DEFAULT ''",
    },
    "payments": {
        "customer": "TEXT NOT NULL DEFAULT ''",
        "reference": "TEXT NOT NULL DEFAULT ''",
        "paid_at": "TEXT",
    },
}


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as c:
        c.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            for col, ddl in cols.items():
                if col not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


@contextmanager
def tx():
    """Transacción con conexión propia (cada request es un hilo distinto)."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def rows(sql, args=()):
    with closing(connect()) as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def row(sql, args=()):
    with closing(connect()) as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def run(sql, args=()):
    with closing(connect()) as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def jl(s, default=None):
    try:
        return json.loads(s)
    except Exception:
        return default if default is not None else []
