"""Crea un restaurante de demostración:  python seed.py
Correo: demo@mesaya.app  ·  Contraseña: demo12345  ·  PIN cocina: 1234"""
import json
import sys
from datetime import datetime, timedelta, timezone

from app import auth, db, service

if db.IS_PG and "--pg" not in sys.argv:  # la demo trae una clave débil: nunca en la base real por accidente
    raise SystemExit("seed.py crea una cuenta demo con clave débil y MESAYA_DATABASE_URL apunta a PostgreSQL. "
                     "Si de verdad lo quieres: python seed.py --pg")
db.init_db()
if db.row("SELECT 1 FROM restaurants WHERE email='demo@mesaya.app'"):
    print("La demo ya existe.")
    raise SystemExit

end = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
rid = db.run(
    """INSERT INTO restaurants(slug,name,email,password_hash,staff_pin,currency,decimals,brand_color,tagline,
                               tip_pct,trial_ends_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("dragon-dorado", "Dragón Dorado", "demo@mesaya.app", auth.hash_password("demo12345"), "1234", "COP", 0,
     "#c8102e", "Cocina china de barrio · desde 1998", 10, end, auth.now()))

MENU = {
    "Entradas": [
        ("Arroz especial", "Arroz frito con cerdo, pollo, camarón y huevo", 24000, ["popular"], [], True),
        ("Lumpias", "6 rollitos crujientes de verduras con salsa agridulce", 16000, ["vegetariano"], ["gluten"], False),
        ("Sopa wantán", "Caldo claro con wantanes de cerdo y cebollín", 18000, [], ["gluten", "soya"], False),
    ],
    "Platos fuertes": [
        ("Chop suey", "Salteado de pollo y verduras al wok", 28000, [], ["soya"], True),
        ("Pollo agridulce", "Pollo apanado en salsa de piña y pimentón", 30000, ["popular"], ["gluten"], False),
        ("Cerdo kung pao", "Cerdo salteado con maní y chile seco", 32000, ["picante"], ["maní", "soya"], False),
        ("Tofu mapo", "Tofu sedoso en salsa picante de Sichuán", 26000, ["vegetariano", "picante"], ["soya"], False),
    ],
    "Bebidas": [
        ("Limonada de coco", "Cremosa, con hielo", 9000, ["vegano"], [], False),
        ("Té helado de jazmín", "Sin azúcar añadida", 7000, ["vegano"], [], False),
        ("Cerveza nacional", "Botella 330 ml", 8000, [], ["gluten"], False),
    ],
    "Postres": [
        ("Helado frito", "Bola de vainilla en tempura con miel", 14000, [], ["gluten", "lácteos"], False),
    ],
}
OPTIONS = {
    "Arroz especial": [{"name": "Tamaño", "required": True, "multi": False,
                        "options": [{"name": "Personal", "price": 0}, {"name": "Para compartir", "price": 12000}]}],
    "Cerdo kung pao": [{"name": "Nivel de picante", "required": True, "multi": False,
                        "options": [{"name": "Suave", "price": 0}, {"name": "Medio", "price": 0}, {"name": "Muy picante", "price": 0}]},
                       {"name": "Adicionales", "required": False, "multi": True,
                        "options": [{"name": "Arroz blanco", "price": 4000}, {"name": "Huevo frito", "price": 3000}]}],
}
for ci, (cat, items) in enumerate(MENU.items()):
    cid = db.run("INSERT INTO categories(restaurant_id,name,sort) VALUES (?,?,?)", (rid, cat, ci))
    for ii, (name, desc, price, tags, allergens, feat) in enumerate(items):
        db.run(
            """INSERT INTO items(restaurant_id,category_id,name,description,price,featured,tags,allergens,options,sort)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (rid, cid, name, desc, price, int(feat), json.dumps(tags), json.dumps(allergens),
             json.dumps(OPTIONS.get(name, [])), ii))
for n in range(1, 9):
    db.run("INSERT INTO tables_(restaurant_id,label,secret) VALUES (?,?,?)", (rid, str(n), f"demo{n}"))
from app import colombia  # noqa: E402
db.run("""UPDATE restaurants SET legal_name='Dragón Dorado SAS', nit='900123456', nit_dv=?, tax_type='INC', tax_pct=8, tax_included=1,
          inv_provider='mock', breb_enabled=1, breb_key='3001234567', breb_key_type='celular', breb_holder='Dragón Dorado SAS'
          WHERE id=?""", (colombia.nit_dv('900123456'), rid))
print("Demo creada: http://localhost:8000/login  (demo@mesaya.app / demo12345)")
