"use client";
// Fidelización Clientes: el dueño registra, consulta y elimina a sus clientes fidelizados.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { Any, useAdmin } from "./ctx";
import Icon from "@/components/Icon";

export default function CustomersTab() {
  const { toast } = useAdmin();
  const [list, setList] = useState<Any[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const load = useCallback(async () => {
    try { setList((await api("/api/customers")).customers); } catch (e: Any) { toast(e.message, true); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d: Any = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      await api("/api/customers", { method: "POST", body: { ...d, consent: !!d.consent } });
      setOpen(false);
      toast("Cliente agregado");
      load();
    } catch (err: Any) {
      toast(err.message, true);
    }
    setBusy(false);
  }

  async function remove(c: Any) {
    if (!confirm(`¿Eliminar a ${c.name} de la fidelización? Se borran sus datos.`)) return;
    try { await api("/api/customers/" + c.id, { method: "DELETE" }); toast("Cliente eliminado"); } catch (e: Any) { toast(e.message, true); }
    load();
  }

  if (!list) return <p className="muted">Cargando…</p>;
  const f = q.trim().toLowerCase();
  const shown = f ? list.filter((c) => (c.name + c.document + c.email + c.phone).toLowerCase().includes(f)) : list;
  return (
    <>
      <div className="row spread wrap">
        <h1>Fidelización Clientes</h1>
        <div className="row">
          {list.length > 0 && <a className="btn sm ghost" href="/api/customers.xlsx" download><Icon n="download" /> Exportar a Excel</a>}
          <button className="btn sm" onClick={() => setOpen(true)}>+ Agregar cliente</button>
        </div>
      </div>
      <p className="muted">{list.length} {list.length === 1 ? "cliente fidelizado" : "clientes fidelizados"}.</p>
      {list.length > 5 && <input placeholder="Buscar por nombre, cédula, correo o celular…" value={q} onChange={(e) => setQ(e.target.value)} />}
      <div className="card" style={{ marginTop: ".8rem" }}>
        {shown.map((c) => (
          <div className="mi" key={c.id}>
            <div className="grow">
              <b>{c.name}</b>
              <div className="muted small">CC {c.document} · {c.phone} · {c.email}</div>
            </div>
            <button className="btn sm ghost" title="Eliminar" onClick={() => remove(c)} aria-label="Eliminar"><Icon n="close" /></button>
          </div>
        ))}
        {!shown.length && <p className="muted">{list.length ? "Sin resultados." : "Aún no tienes clientes fidelizados. Agrega el primero con «+ Agregar cliente»."}</p>}
      </div>

      <Modal open={open} onClose={() => setOpen(false)}>
        <h2>Agregar cliente</h2>
        <form onSubmit={save}>
          <label>Número de cédula</label>
          <input name="document" inputMode="numeric" autoComplete="off" required />
          <label>Nombre completo</label>
          <input name="name" autoComplete="off" required />
          <label>Correo electrónico</label>
          <input name="email" type="email" autoComplete="off" required />
          <label>Número de celular</label>
          <input name="phone" type="tel" inputMode="tel" autoComplete="off" required />
          <label style={{ display: "flex", gap: ".5rem", alignItems: "flex-start", fontWeight: 500, color: "var(--ink)", marginTop: "1rem" }}>
            <input name="consent" type="checkbox" style={{ width: "auto", marginTop: ".2rem" }} required />
            El cliente autorizó el tratamiento de sus datos personales para su programa de fidelización.
          </label>
          <div className="row" style={{ marginTop: "1rem" }}>
            <button type="button" className="btn ghost grow" onClick={() => setOpen(false)}>Cancelar</button>
            <button className="btn grow" disabled={busy}>Guardar</button>
          </div>
        </form>
      </Modal>
    </>
  );
}
