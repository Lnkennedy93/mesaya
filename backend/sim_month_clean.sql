-- Quita los datos simulados de sim_month.sql. Reemplazar __RID__ y __FB0__ (máximo id de feedback que había antes de simularlos).
DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE restaurant_id = __RID__ AND client_ref LIKE 'sim-%');
DELETE FROM payments WHERE restaurant_id = __RID__ AND external_ref = 'sim';
DELETE FROM orders WHERE restaurant_id = __RID__ AND client_ref LIKE 'sim-%';
DELETE FROM feedback WHERE restaurant_id = __RID__ AND id > __FB0__;
