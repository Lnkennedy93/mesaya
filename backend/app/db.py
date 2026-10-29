import atexit
import json
import re
import sqlite3
import threading
import uuid
from contextlib import closing, contextmanager

from . import config
from .config import DB_PATH

# Dos motores con la misma API: SQLite (por defecto, un solo archivo) y PostgreSQL (MESAYA_DATABASE_URL).
IS_PG = bool(config.DATABASE_URL)
PG_SCHEMA = ("t_" + uuid.uuid4().hex[:10]) if config.PG_SCHEMA == "auto" else config.PG_SCHEMA

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
CREATE TABLE IF NOT EXISTS rate_hits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  k TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_k ON rate_hits(k, ts);
CREATE TABLE IF NOT EXISTS images (
  name TEXT PRIMARY KEY,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS draft_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  draft_id TEXT NOT NULL,
  n INTEGER NOT NULL,
  data BLOB NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_draft_images ON draft_images(restaurant_id, draft_id, n);
CREATE TABLE IF NOT EXISTS import_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  upload_id TEXT NOT NULL,
  n INTEGER NOT NULL,
  data BLOB NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_import_chunks ON import_chunks(restaurant_id, upload_id, n);
"""


# ---------------------------------------------------------------- SQLite
def _connect_sqlite():
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ---------------------------------------------------------------- PostgreSQL
class Row(dict):
    """Fila que se lee por nombre o por posición (como sqlite3.Row)."""
    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return super().__getitem__(k)


def _row_factory(cursor):
    names = [c.name for c in (cursor.description or [])]
    return lambda values: Row(zip(names, values))


_NO_ID = ("sessions", "password_resets", "images")  # tablas sin columna id: no se pide RETURNING id
_pool = None
_pool_lock = threading.Lock()


def _pg_sql(sql: str, has_args: bool) -> str:
    """Traduce el SQL escrito para SQLite: ? -> %s, CAST(x AS INTEGER) tolerante y RETURNING id."""
    parts = re.split(r"('(?:[^']|'')*')", sql)
    for i, p in enumerate(parts):
        if has_args:
            p = p.replace("%", "%%")
        if i % 2 == 0:
            if has_args:
                p = p.replace("?", "%s")
            p = re.sub(r"CAST\(([\w.]+) AS INTEGER\)",
                       lambda m: f"(CASE WHEN {m[1]} ~ '^[0-9]+$' THEN {m[1]}::bigint ELSE 0 END)", p)
        parts[i] = p
    out = "".join(parts)
    m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", out, re.I)
    if m and m[1].lower() not in _NO_ID and "RETURNING" not in out.upper():
        out = out.rstrip().rstrip(";") + " RETURNING id"
    return out


class _PgCursor:
    def __init__(self, cur, lastrowid=None):
        self._cur, self.lastrowid = cur, lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)


class _PgConn:
    def __init__(self, conn, pool):
        self._conn, self._pool = conn, pool

    def execute(self, sql, args=()):
        args = tuple(int(a) if isinstance(a, bool) else a for a in (args or ()))
        q = _pg_sql(sql, bool(args))
        cur = self._conn.execute(q, args or None)
        last = None
        if q.endswith(" RETURNING id"):
            r = cur.fetchone()
            last = r["id"] if r else None
        return _PgCursor(cur, last)

    def executescript(self, sql):
        self._conn.execute(sql)

    def close(self):
        if self._conn is not None:
            self._pool.putconn(self._conn)
            self._conn = None


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                kw = {"autocommit": True, "row_factory": _row_factory, "prepare_threshold": None}
                if PG_SCHEMA:  # solo las pruebas; sin esto la conexión sirve también tras el pooler de Supabase (puerto 6543)
                    kw["options"] = f"-c search_path={PG_SCHEMA},public"
                p = ConnectionPool(
                    config.DATABASE_URL, min_size=1, max_size=config.PG_POOL_MAX, open=False, timeout=15,
                    check=ConnectionPool.check_connection, kwargs=kw)
                p.open()
                atexit.register(close_pool)
                _pool = p
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def _connect_pg():
    pool = _get_pool()
    return _PgConn(pool.getconn(), pool)


def connect():
    return _connect_pg() if IS_PG else _connect_sqlite()


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
    if IS_PG:
        if PG_SCHEMA:
            import psycopg
            with psycopg.connect(config.DATABASE_URL, autocommit=True) as boot:
                boot.execute(f'CREATE SCHEMA IF NOT EXISTS "{PG_SCHEMA}"')
        ddl = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        ddl = re.sub(r"\bREAL\b", "DOUBLE PRECISION", ddl)
        ddl = re.sub(r"\bBLOB\b", "BYTEA", ddl)
        with closing(connect()) as c:
            c.execute("SELECT pg_advisory_lock(727002)")  # varios procesos arrancando a la vez
            try:
                c.executescript(ddl)
                for table, cols in MIGRATIONS.items():
                    for col, col_ddl in cols.items():
                        c.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_ddl}")
                # Supabase publica por su API REST las tablas de "public": con RLS activo y sin políticas esa API no
                # ve nada. El backend, que es el dueño de las tablas, no se ve afectado.
                for table in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", ddl):
                    c.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            finally:
                c.execute("SELECT pg_advisory_unlock(727002)")
        return
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
    """Transacción con conexión propia (cada request es un hilo distinto).
    Las escrituras se serializan (SQLite: BEGIN IMMEDIATE; PostgreSQL: un candado de transacción),
    así las lecturas-y-luego-escrituras (número de pedido, pagos) no se pisan."""
    conn = connect()
    try:
        if IS_PG:
            conn.execute("BEGIN")
            conn.execute("SELECT pg_advisory_xact_lock(727001)")
        else:
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


if __name__ == "__main__":
    init_db()
    print("Esquema listo en", "PostgreSQL" if IS_PG else DB_PATH)
