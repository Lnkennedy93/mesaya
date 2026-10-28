"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { Any, useAdmin } from "./ctx";
import ItemDialog from "./ItemDialog";
import ImportDialog from "./ImportDialog";

type Dlg = null | { t: "item"; item: Any | null; catId?: number } | { t: "import" };

export default function MenuTab() {
  const { money, toast } = useAdmin();
  const [menu, setMenu] = useState<Any[] | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);

  const load = useCallback(async () => {
    try { setMenu((await api("/api/menu")).categories); } catch (e: Any) { toast(e.message, true); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<unknown>) {
    try { await fn(); } catch (e: Any) { toast(e.message, true); }
    load();
  }

  if (!menu) return <p className="muted">Cargando…</p>;
  const empty = !menu.length;

  return (
    <>
      <div className="row spread wrap">
        <h1>Carta</h1>
        <div className="row wrap">
          <button className="btn ghost sm" onClick={() => setDlg({ t: "import" })}>⚡ Importar carta</button>
          <button className="btn sm" onClick={() => { const n = prompt("Nombre de la categoría (ej. Entradas)"); if (n) run(() => api("/api/categories", { method: "POST", body: { name: n } })); }}>+ Categoría</button>
        </div>
      </div>
      {empty && (
        <div className="card">
          <h2>Crea tu carta en 5 minutos</h2>
          <p className="muted">Importa tu menú pegando el texto o subiendo una foto/PDF, o crea las categorías a mano. Luego agrega la foto de cada plato.</p>
          <button className="btn" onClick={() => setDlg({ t: "import" })}>⚡ Importar mi carta</button>
        </div>
      )}
      {menu.map((c, ci) => (
        <div key={c.id}>
          <div className="cathead">
            <h2 style={{ margin: 0 }} className="grow">{c.name}</h2>
            <button className="btn sm ghost" disabled={ci === 0} onClick={() => run(() => api(`/api/categories/${c.id}/move`, { method: "POST", body: { dir: "up" } }))}>↑</button>
            <button className="btn sm ghost" disabled={ci === menu.length - 1} onClick={() => run(() => api(`/api/categories/${c.id}/move`, { method: "POST", body: { dir: "down" } }))}>↓</button>
            <button className="btn sm ghost" onClick={() => { const n = prompt("Nuevo nombre", c.name); if (n) run(() => api("/api/categories/" + c.id, { method: "PUT", body: { name: n } })); }}>Renombrar</button>
            <button className="btn sm ghost" onClick={() => { if (confirm("¿Eliminar la categoría y todos sus platos?")) run(() => api("/api/categories/" + c.id, { method: "DELETE" })); }}>Eliminar</button>
            <button className="btn sm" onClick={() => setDlg({ t: "item", item: null, catId: c.id })}>+ Plato</button>
          </div>
          <div className="card" style={{ padding: ".2rem" }}>
            {c.items.map((i: Any) => (
              <div className="mi" key={i.id}>
                <div className="thumb">{i.image ? <img src={i.image} alt="" /> : i.name[0] || "?"}</div>
                <div className="grow"><b>{i.name}</b> {i.featured && <span className="pill warn">★</span>}<div className="muted small">{String(i.description).slice(0, 80)}</div></div>
                <b>{money(i.price)}</b>
                <label className="switch" title="Disponible">
                  <input type="checkbox" checked={i.available} onChange={(e) => run(async () => { await api(`/api/items/${i.id}/availability`, { method: "POST", body: { available: e.target.checked } }); toast(e.target.checked ? "Disponible" : "Marcado como agotado"); })} />
                  <span></span>
                </label>
                <button className="btn sm ghost" onClick={() => setDlg({ t: "item", item: i })}>Editar</button>
              </div>
            ))}
            {!c.items.length && <p className="muted small" style={{ padding: ".8rem" }}>Sin platos todavía</p>}
          </div>
        </div>
      ))}

      <Modal open={!!dlg} onClose={() => setDlg(null)}>
        {dlg?.t === "item" && <ItemDialog item={dlg.item} catId={dlg.catId} menu={menu} onClose={() => setDlg(null)} onChanged={load} />}
        {dlg?.t === "import" && <ImportDialog onClose={() => setDlg(null)} onDone={() => { setDlg(null); load(); }} />}
      </Modal>
    </>
  );
}
