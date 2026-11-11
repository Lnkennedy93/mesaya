-- Datos SIMULADOS de un mes de uso (PostgreSQL) para enseñar la herramienta a prospectos.
-- Reemplazar __RID__ por el id del restaurante demo. Todo queda marcado: orders.client_ref 'sim-%', payments.external_ref 'sim'
-- (las calificaciones: id mayor al máximo que había antes de correrlo). Para quitarlo: sim_month_clean.sql.
-- Mesas y platos son los reales del restaurante; los pedidos, cobros y calificaciones son inventados (setseed fijo: repetible).
DO $sim$
DECLARE
  rid int := __RID__;
  tz int; today date; d date; k int; i int; j int; n int; nses int; norders int; dow int; fact numeric;
  mains int[]; drinks int[]; starts int[]; sweets int[]; tabs text[]; ids int[];
  lunch numeric; dinner numeric; hr numeric; r numeric; p numeric;
  t timestamp; ts timestamp; tlast timestamp; lbl text; sid text; oid int; itid int; line int; lid int;
  sub int; tip int; pid int; prov text; party int; take boolean; seqn int := 0; rating int;
  nm text[] := ARRAY['Ana','Carlos','Laura','Andrés','Camila','Juan','Valentina','Santiago','Daniela','Felipe','Mariana','Sebastián','Paula','David','Natalia','Mateo','Isabela','Julián','Sara','Nicolás','Luisa','Diego','Manuela','Camilo','Lucía','Esteban'];
  cm text[] := ARRAY['Muy rico todo, volveremos','Buen servicio y la comida llegó rápido','La pasta deliciosa','Excelente atención','Un poco de espera pero valió la pena','Porciones generosas','Ambiente agradable para ir en familia','Los postres están buenísimos','Podrían tener más opciones de bebidas','Todo perfecto'];
  f text := 'YYYY-MM-DD HH24:MI:SS';
BEGIN
  PERFORM setseed(0.42);
  SELECT tz_offset INTO tz FROM restaurants WHERE id = rid;
  IF tz IS NULL THEN RAISE EXCEPTION 'restaurante % no existe', rid; END IF;
  today := ((now() AT TIME ZONE 'UTC') + make_interval(mins => tz))::date;
  SELECT array_agg(tables_.label ORDER BY id) INTO tabs FROM tables_ WHERE restaurant_id = rid;
  -- Los platos van ordenados por un hash estable: los primeros de cada lista son los «más pedidos».
  SELECT array_agg(i.id ORDER BY md5(i.id::text)) INTO drinks FROM items i JOIN categories c ON c.id=i.category_id WHERE i.restaurant_id=rid AND i.available=1 AND c.name ILIKE 'Bebida%';
  SELECT array_agg(i.id ORDER BY md5(i.id::text)) INTO sweets FROM items i JOIN categories c ON c.id=i.category_id WHERE i.restaurant_id=rid AND i.available=1 AND c.name ILIKE 'Postre%';
  SELECT array_agg(i.id ORDER BY md5(i.id::text)) INTO starts FROM items i JOIN categories c ON c.id=i.category_id WHERE i.restaurant_id=rid AND i.available=1 AND c.name ILIKE 'Entrada%';
  SELECT array_agg(i.id ORDER BY md5(i.id::text)) INTO mains FROM items i JOIN categories c ON c.id=i.category_id WHERE i.restaurant_id=rid AND i.available=1
    AND c.name NOT ILIKE 'Bebida%' AND c.name NOT ILIKE 'Postre%' AND c.name NOT ILIKE 'Entrada%' AND c.name NOT ILIKE 'Desayuno%';
  IF mains IS NULL OR tabs IS NULL THEN RAISE EXCEPTION 'faltan platos o mesas'; END IF;

  FOR k IN 1..30 LOOP   -- 30 días completos que terminan ayer (hora local)
    d := today - (31 - k);
    dow := extract(dow FROM d)::int;   -- 0 domingo … 6 sábado
    -- fin de semana fuerte, tendencia de crecimiento suave y ruido diario
    fact := (0.9 + 0.2 * k / 30.0) * (0.88 + 0.24 * random());
    nses := round(fact * CASE dow WHEN 5 THEN 22 WHEN 6 THEN 33 WHEN 0 THEN 29 ELSE 10 + (dow % 3) * 2 END)::int;
    lunch  := CASE dow WHEN 5 THEN .40 WHEN 6 THEN .42 WHEN 0 THEN .62 ELSE .60 END;
    dinner := CASE dow WHEN 5 THEN .56 WHEN 6 THEN .53 WHEN 0 THEN .33 ELSE .35 END;
    FOR i IN 1..(nses + round(nses * 0.3)::int) LOOP   -- las últimas 30 % son pedidos para llevar
      take := i > nses;
      -- hora de llegada: campana alrededor del almuerzo (13:15) o de la cena (20:00); el resto, la tarde
      r := random();
      hr := CASE WHEN r < lunch THEN 13.25 + (random()+random()+random()-1.5) * 1.6
                 WHEN r < lunch + dinner THEN 20.0 + (random()+random()+random()-1.5) * 1.7
                 ELSE 16.5 + (random()-0.5) * 2.5 END;
      hr := greatest(11.5, least(21.5, hr));
      t := d + make_interval(secs => (hr * 3600)::int) - make_interval(mins => tz);   -- a UTC
      IF NOT take THEN
        lbl := tabs[1 + floor(random() * array_length(tabs,1))::int];
        norders := CASE WHEN random() < .6 THEN 1 WHEN random() < .75 THEN 2 ELSE 3 END;
        party := 1 + floor(random() * random() * 5)::int + (CASE WHEN dow IN (0,6) THEN 1 ELSE 0 END);
      ELSE
        lbl := 'PL-' || substr(md5(random()::text), 1, 6);
        norders := 1;
        party := 1 + floor(random() * 2)::int;
      END IF;
      sid := to_char(d,'YYMMDD') || '-' || i;
      ids := ARRAY[]::int[]; sub := 0; tlast := t;
      FOR j IN 1..norders LOOP
        ts := t + make_interval(mins => (j-1) * (20 + floor(random()*25))::int);
        tlast := ts + make_interval(mins => 24);
        seqn := seqn + 1;
        INSERT INTO orders(restaurant_id, table_label, seq, status, diner_id, diner_name, note, created_at, preparing_at, ready_at, served_at, client_ref)
        VALUES (rid, lbl, 0, 'served', 'sim-' || sid, nm[1 + floor(random()*array_length(nm,1))::int], '',
                to_char(ts, f),
                to_char(ts + make_interval(mins => 1 + floor(random()*3)::int), f),
                to_char(ts + make_interval(mins => 8 + floor(random()*10)::int + CASE WHEN dow IN (5,6,0) AND (hr BETWEEN 13 AND 14.5 OR hr BETWEEN 19.5 AND 21) THEN 6 ELSE 0 END), f),
                to_char(ts + make_interval(mins => 22 + floor(random()*10)::int), f),
                'sim-' || seqn)
        RETURNING id INTO oid;
        -- un principal por comensal en el primer pedido; después bebidas, entradas o postres. Los primeros de cada lista salen más.
        FOR n IN 1..(CASE WHEN j = 1 THEN party ELSE 1 END) + (CASE WHEN random() < .6 THEN 1 ELSE 0 END) LOOP
          p := random();
          itid := CASE WHEN j = 1 AND n <= party THEN mains[1 + floor(power(random(), 2.0) * array_length(mains,1))::int]
                       WHEN p < .45 AND drinks IS NOT NULL THEN drinks[1 + floor(power(random(), 1.8) * array_length(drinks,1))::int]
                       WHEN p < .65 AND starts IS NOT NULL THEN starts[1 + floor(random() * array_length(starts,1))::int]
                       WHEN p < .85 AND sweets IS NOT NULL THEN sweets[1 + floor(random() * array_length(sweets,1))::int]
                       ELSE mains[1 + floor(power(random(), 2.0) * array_length(mains,1))::int] END;
          INSERT INTO order_items(order_id, item_id, name, options_text, note, qty, unit_price)
          SELECT oid, x.id, x.name, '', '', CASE WHEN random() < .15 THEN 2 ELSE 1 END, x.price FROM items x WHERE x.id = itid
          RETURNING id, qty * unit_price INTO lid, line;
          ids := ids || lid; sub := sub + line;
        END LOOP;
      END LOOP;
      -- cobro de la cuenta (INC incluido en el precio, como el restaurante real): total = subtotal + propina
      r := random();
      prov := CASE WHEN take THEN (CASE WHEN r < .55 THEN 'nequi' WHEN r < .85 THEN 'breb' ELSE 'wompi' END)
                   WHEN r < .30 THEN 'cash' WHEN r < .55 THEN 'card' WHEN r < .85 THEN 'nequi' WHEN r < .95 THEN 'breb' ELSE 'wompi' END;
      r := random();
      tip := CASE WHEN take THEN 0 WHEN r < .70 THEN round(sub * .10)::int WHEN r < .85 THEN round(sub * .05)::int ELSE 0 END;
      IF take THEN tlast := t + make_interval(mins => 1); ELSE tlast := tlast + make_interval(mins => 20 + floor(random()*40)::int); END IF;
      INSERT INTO payments(restaurant_id, table_label, provider, status, subtotal, tip, total, payer, item_ids, external_ref, created_at, paid_at)
      VALUES (rid, lbl, prov, 'paid', sub, tip, sub + tip, nm[1 + floor(random()*array_length(nm,1))::int], to_json(ids)::text, 'sim', to_char(tlast, f), to_char(tlast, f))
      RETURNING id INTO pid;
      UPDATE order_items SET paid_payment_id = pid WHERE id = ANY(ids);
      -- opinión: la deja ~1 de cada 4 mesas
      IF NOT take AND random() < .25 THEN
        r := random();
        rating := CASE WHEN r < .55 THEN 5 WHEN r < .85 THEN 4 WHEN r < .95 THEN 3 WHEN r < .98 THEN 2 ELSE 1 END;
        INSERT INTO feedback(restaurant_id, table_label, rating, comment, created_at)
        VALUES (rid, lbl, rating, CASE WHEN random() < .5 THEN cm[1 + floor(random()*array_length(cm,1))::int] ELSE '' END, to_char(tlast + make_interval(mins => 8), f));
      END IF;
    END LOOP;
  END LOOP;
  -- número de pedido: arranca en 1 cada día (hora local), en el orden en que llegaron
  UPDATE orders o SET seq = s.rn FROM (
    SELECT id, row_number() OVER (PARTITION BY (created_at::timestamp + make_interval(mins => tz))::date ORDER BY created_at, id) rn
    FROM orders WHERE restaurant_id = rid AND client_ref LIKE 'sim-%') s
  WHERE o.id = s.id;
END
$sim$;
