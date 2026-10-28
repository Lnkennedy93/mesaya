"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Any, useAdmin } from "./ctx";

export function TablesTab() {
  const { ME, toast } = useAdmin();
  const [tables, setTables] = useState<Any[] | null>(null);
  const load = useCallback(async () => {
    try { setTables((await api("/api/tables")).tables); } catch (e: Any) { toast(e.message, true); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<unknown>) {
    try { await fn(); } catch (e: Any) { toast(e.message, true); }
    load();
  }

  if (!tables) return <p className="muted">Cargando…</p>;
  return (
    <>
      <div className="row spread wrap">
        <h1>Mesas y QR</h1>
        <div className="row">
          <button className="btn ghost sm" onClick={() => { const n = prompt("¿Cuántas mesas quieres agregar?", "1"); if (n) run(() => api("/api/tables", { method: "POST", body: { count: +n } })); }}>+ Agregar mesas</button>
          <a className="btn sm" href="/print/qr" target="_blank">🖨 Imprimir todos</a>
        </div>
      </div>
      <p className="muted">Cada mesa tiene un QR con código secreto propio: así nadie puede mandar pedidos a tu cocina sin estar en la mesa. Plan {ME.plan.name}: hasta {ME.plan.tables} mesas.</p>
      <div className="qrg">
        {tables.map((t) => (
          <div className="card qrc" key={t.id}>
            <b>Mesa {t.label}</b>
            <img src={`/api/qr/${t.id}.svg`} alt="QR" />
            <div className="row" style={{ justifyContent: "center" }}>
              <button className="btn sm ghost" title="Genera un QR nuevo e invalida el anterior" onClick={() => { if (confirm("El QR impreso actual dejará de funcionar. ¿Renovar?")) run(() => api(`/api/tables/${t.id}/rotate`, { method: "POST" })); }}>Renovar</button>
              <button className="btn sm ghost" onClick={() => { if (confirm("¿Eliminar mesa?")) run(() => api("/api/tables/" + t.id, { method: "DELETE" })); }}>✕</button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

export function ReviewsTab() {
  const { toast } = useAdmin();
  const [list, setList] = useState<Any[] | null>(null);
  useEffect(() => {
    api("/api/feedback").then((r) => setList(r.feedback)).catch((e) => toast(e.message, true));
  }, [toast]);
  if (!list) return <p className="muted">Cargando…</p>;
  return (
    <>
      <h1>Opiniones de clientes</h1>
      <div className="card">
        {list.map((f) => (
          <div className="mi" key={f.id}>
            <b style={{ color: "#f5a623", minWidth: "5.2em" }}>{"★".repeat(f.rating)}{"☆".repeat(5 - f.rating)}</b>
            <div className="grow">
              {f.comment || <span className="muted">Sin comentario</span>}
              <div className="muted small">Mesa {f.table_label} · {f.created_at} UTC</div>
            </div>
          </div>
        ))}
        {!list.length && <p className="muted">Aún no hay opiniones. Se piden a los clientes cuando terminan su mesa; si dan 4–5 estrellas los invitamos a dejar reseña en Google.</p>}
      </div>
    </>
  );
}
