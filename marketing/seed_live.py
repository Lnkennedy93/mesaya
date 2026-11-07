"""Deja la base LOCAL de demostración con un servicio "en vivo" para grabar el video: pedidos en cocina con distintas
demoras, una mesa con cuenta por cobrar y llamados al mesero. Se puede repetir sin problema.

    cd backend && MESAYA_DATABASE_URL= MESAYA_DB=data/asistente_local.db python ../marketing/seed_live.py
(la guarda de abajo impide correrlo contra PostgreSQL / producción)"""
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from app import db  # noqa: E402

if db.IS_PG:
    raise SystemExit("Este script solo es para la base SQLite local, nunca para PostgreSQL.")

FMT = "%Y-%m-%d %H:%M:%S"
now = datetime.now(timezone.utc)
ago = lambda m: (now - timedelta(minutes=m)).strftime(FMT)
rid = db.row("SELECT id FROM restaurants WHERE email='demo@mesaya.app'")["id"]
price = {r["name"]: (r["id"], r["price"]) for r in db.rows("SELECT id,name,price FROM items WHERE restaurant_id=?", (rid,))}

# 1) borrar el servicio en vivo anterior (y el pedido que el video hace como «Camila»)
db.run("""UPDATE order_items SET paid_payment_id=NULL WHERE paid_payment_id IN
          (SELECT id FROM payments WHERE restaurant_id=? AND payer='caja' AND item_ids='[]')""", (rid,))
db.run("DELETE FROM payments WHERE restaurant_id=? AND payer='caja' AND item_ids='[]'", (rid,))
for o in db.rows("""SELECT id FROM orders WHERE restaurant_id=? AND (diner_id LIKE 'live-%' OR diner_name='Camila'
                    OR (table_label='6' AND created_at > ?))""", (rid, ago(240))):  # lo último = pedidos que hizo el guion de captura
    db.run("DELETE FROM order_items WHERE order_id=?", (o["id"],))
    db.run("DELETE FROM orders WHERE id=?", (o["id"],))
db.run("DELETE FROM calls WHERE restaurant_id=?", (rid,))

# 2) el historial viejo queda cobrado (si no, todas las mesas aparecerían con cuenta pendiente)
old = db.rows("""SELECT DISTINCT o.table_label t FROM orders o JOIN order_items oi ON oi.order_id=o.id
                 WHERE o.restaurant_id=? AND oi.paid_payment_id IS NULL AND o.created_at < ?""", (rid, ago(120)))
for t in old:
    amount = db.row("""SELECT COALESCE(SUM(oi.qty*oi.unit_price),0) s FROM order_items oi JOIN orders o ON o.id=oi.order_id
                       WHERE o.restaurant_id=? AND o.table_label=? AND oi.paid_payment_id IS NULL AND o.created_at < ?""", (rid, t["t"], ago(120)))["s"]
    pid = db.run("""INSERT INTO payments(restaurant_id,table_label,provider,status,subtotal,tip,total,payer,item_ids,customer,paid_at,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (rid, t["t"], "cashier", "paid", amount, 0, amount, "caja", "[]", "{}", ago(180), ago(180)))
    db.run("""UPDATE order_items SET paid_payment_id=? WHERE paid_payment_id IS NULL AND order_id IN
              (SELECT id FROM orders WHERE restaurant_id=? AND table_label=? AND created_at < ?)""", (pid, rid, t["t"], ago(120)))

# 3) servicio en vivo: (mesa, comensal, minutos desde el pedido, estado, platos)
LIVE = [
    ("7", "Camilo", 13, "preparing", [("Cerdo kung pao", 1), ("Arroz especial", 1)]),
    ("4", "Laura", 7, "preparing", [("Pollo agridulce", 2), ("Té helado de jazmín", 2)]),
    ("5", "Mateo", 3, "new", [("Lumpias", 1), ("Chop suey", 1), ("Limonada de coco", 2)]),
    ("2", "Valentina", 1, "new", [("Sopa wantán", 2)]),
    ("1", "Sofía", 16, "ready", [("Tofu mapo", 1), ("Arroz especial", 1)]),
    ("3", "Andrés", 35, "served", [("Chop suey", 2), ("Limonada de coco", 1), ("Helado frito", 1)]),
]
seq = db.row("SELECT COALESCE(MAX(seq),0) s FROM orders WHERE restaurant_id=?", (rid,))["s"]
for table, who, mins, status, dishes in LIVE:
    seq += 1
    t0 = now - timedelta(minutes=mins)
    prep = t0 + timedelta(minutes=2) if status != "new" else None
    ready = t0 + timedelta(minutes=11) if status in ("ready", "served") else None
    served = t0 + timedelta(minutes=13) if status == "served" else None
    f = lambda d: d.strftime(FMT) if d else None
    oid = db.run("""INSERT INTO orders(restaurant_id,table_label,seq,status,diner_id,diner_name,note,created_at,preparing_at,ready_at,served_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (rid, table, seq, status, f"live-{who.lower()}", who, "", f(t0), f(prep), f(ready), f(served)))
    for name, qty in dishes:
        iid, p = price[name]
        db.run("INSERT INTO order_items(order_id,item_id,name,options_text,note,qty,unit_price) VALUES (?,?,?,?,?,?,?)", (oid, iid, name, "", "", qty, p))
db.run("INSERT INTO calls(restaurant_id,table_label,type,created_at) VALUES (?,?,?,?)", (rid, "5", "waiter", ago(1)))
db.run("INSERT INTO calls(restaurant_id,table_label,type,created_at) VALUES (?,?,?,?)", (rid, "3", "bill", ago(2)))
db.run("UPDATE restaurants SET accepting_orders=1 WHERE id=?", (rid,))
print("Servicio en vivo listo:", len(LIVE), "pedidos,", len(old), "mesas con historial cobrado")
