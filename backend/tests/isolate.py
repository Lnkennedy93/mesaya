"""Importar ANTES de `app`: con PostgreSQL (MESAYA_DATABASE_URL en .env) las pruebas usan un esquema temporal
y lo borran al terminar, así nunca tocan los datos reales. Con SQLite no hace nada (cada prueba ya usa su archivo temporal)."""
import atexit
import os

os.environ["MESAYA_PG_SCHEMA"] = "auto"


def _drop():
    from app import config, db  # import tardío: config se lee al importarse y las pruebas fijan su entorno antes
    if db.IS_PG and db.PG_SCHEMA.startswith("t_"):
        db.close_pool()
        import psycopg
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{db.PG_SCHEMA}" CASCADE')


atexit.register(_drop)
