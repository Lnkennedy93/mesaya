"use client";
// Fidelización Clientes: el dueño registra, consulta y elimina a sus clientes fidelizados.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { Any, useAdmin } from "./ctx";
import Icon from "@/components/Icon";

export default function CustomersTab() {
  const { ME, setME, toast } = useAdmin();
  const r = ME.restaurant;
  const [sc, setSc] = useState({ on: !!r.stamps_on, goal: String(r.stamps_goal || 8), reward: r.stamps_reward || "" });
  const [cardOf, setCardOf] = useState<Any | null>(null); // cliente cuya tarjeta se está viendo
  const [cardUrl, setCardUrl] = useState("");
  const [list, setList] = useState<Any[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [qr, setQr] = useState<string | null>(null); // enlace del QR de registro ("" = aún no generado)
  const [qrCard, setQrCard] = useState(""); // enlace del QR de «ver mi tarjeta»
  const load = useCallback(async () => {
    try { setList((await api("/api/customers")).customers); } catch (e: Any) { toast(e.message, true); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api("/api/customers/qr").then((r) => { setQr(r.url); setQrCard(r.card_url || ""); }).catch(() => setQr("")); }, []);

  async function makeQr(rotate = false) {
    if (rotate && !confirm("El QR impreso actual dejará de funcionar. ¿Generar uno nuevo?")) return;
    try { const r = await api("/api/customers/qr", { method: "POST", body: { rotate } }); setQr(r.url); setQrCard(r.card_url || ""); } catch (e: Any) { toast(e.message, true); }
  }

  function printQr(kind: "registro" | "tarjeta" = "registro") {
    const w = window.open("", "_blank");
    if (!w) return;
    const t = kind === "tarjeta" ? ["Consulta tu tarjeta de sellos", "Escanea el código y mira cuántos sellos llevas", "/api/qr/customers-card.svg?v=" + encodeURIComponent(qrCard)]
      : ["¡Únete a nuestra fidelización!", "Escanea el código y llena tus datos", "/api/qr/customers.svg?v=" + encodeURIComponent(qr || "")];
    w.document.write(`<title>${t[0]}</title><body style="font-family:system-ui;text-align:center;padding:2rem"><h1>${t[0]}</h1><p>${t[1]}</p><img src="${t[2]}" style="width:70vmin" onload="print()">`);
    w.document.close();
  }

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

  async function saveStamps() {
    try {
      setME(await api("/api/settings", { method: "PUT", body: { stamps_on: sc.on ? 1 : 0, stamps_goal: +sc.goal || 8, stamps_reward: sc.reward } }));
      toast("Tarjeta de sellos guardada");
    } catch (e: Any) { toast(e.message, true); }
  }

  async function openCard(c: Any) {
    try { setCardUrl((await api(`/api/customers/${c.id}/card`)).url); setCardOf(c); } catch (e: Any) { toast(e.message, true); }
  }

  async function stampAct(kind: "stamp" | "redeem") {
    try {
      const res = await api("/api/loyalty/" + kind, { method: "POST", body: { document: cardOf!.document, force: true } });
      setCardOf({ ...cardOf, stamps: res.stamps });
      toast(kind === "stamp" ? `Sello sumado: ${res.filled}/${res.goal}` : "Premio canjeado");
      load();
    } catch (e: Any) { toast(e.message, true); }
  }

  async function writeNfc() { // Web NFC: solo Chrome en Android con NFC; la tarjeta queda con el enlace de este cliente
    try {
      const n = new (window as Any).NDEFReader();
      await n.write({ records: [{ recordType: "url", data: cardUrl }] });
      toast("Tarjeta NFC grabada: al acercarla a un celular se abre la tarjeta de sellos del cliente");
    } catch { toast("No se pudo grabar. Usa Chrome en un Android con NFC y acerca una tarjeta NFC en blanco.", true); }
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
      <div className="card" style={{ margin: ".8rem 0" }}>
        <h3><Icon n="qr" /> Registro por QR</h3>
        <p className="muted small" style={{ margin: "0 0 .6rem" }}>Imprime este QR en el mostrador o las mesas. Cuando un cliente lo escanee verá un formulario (cédula, nombre, correo, celular y su autorización de datos) y se guarda aquí, en la base de fidelización de tu restaurante.</p>
        {qr ? (
          <div className="row wrap" style={{ alignItems: "center" }}>
            <img src={`/api/qr/customers.svg?v=${encodeURIComponent(qr)}`} alt="QR de registro de clientes" style={{ width: 150, height: 150, background: "#fff", borderRadius: 12, padding: 6 }} />
            <div className="grow">
              <div className="muted small" style={{ wordBreak: "break-all" }}>{qr}</div>
              <div className="row wrap" style={{ marginTop: ".6rem" }}>
                <button className="btn sm" onClick={() => printQr()}><Icon n="print" /> Imprimir QR</button>
                <button className="btn sm ghost" onClick={() => makeQr(true)}>Renovar QR</button>
              </div>
            </div>
          </div>
        ) : qr === "" ? <button className="btn sm" onClick={() => makeQr()}>Generar QR de registro</button> : <p className="muted small">…</p>}
      </div>
      {qr && qrCard ? (
        <div className="card" style={{ margin: ".8rem 0" }}>
          <h3><Icon n="qr" /> QR para ver la tarjeta</h3>
          <p className="muted small" style={{ margin: "0 0 .6rem" }}>Imprímelo para el mostrador o las mesas. El cliente ya registrado lo escanea, escribe su cédula y su celular una sola vez y llega a su tarjeta de sellos (con su QR personal y el botón para crear el acceso directo). Ese celular la recuerda: las próximas veces entra directo. Si aún no está registrado, el mismo QR le ofrece registrarse.</p>
          <div className="row wrap" style={{ alignItems: "center" }}>
            <img src={`/api/qr/customers-card.svg?v=${encodeURIComponent(qrCard)}`} alt="QR para ver la tarjeta" style={{ width: 150, height: 150, background: "#fff", borderRadius: 12, padding: 6 }} />
            <div className="grow">
              <div className="muted small" style={{ wordBreak: "break-all" }}>{qrCard}</div>
              <div className="row wrap" style={{ marginTop: ".6rem" }}>
                <button className="btn sm" onClick={() => printQr("tarjeta")}><Icon n="print" /> Imprimir QR</button>
              </div>
              {!r.stamps_on && <p className="muted small" style={{ margin: ".5rem 0 0" }}>Activa la tarjeta de sellos aquí abajo para que funcione.</p>}
            </div>
          </div>
        </div>
      ) : null}
      <div className="card" style={{ margin: ".8rem 0" }}>
        <h3><Icon n="gift" /> Tarjeta de sellos</h3>
        <p className="muted small" style={{ margin: "0 0 .6rem" }}>Cada visita suma un sello; al completar la tarjeta el cliente gana el premio que tú elijas. El sello se suma al cobrar la mesa en Sala (con la cédula del cliente) o cuando tu equipo abre el QR o la tarjeta NFC personal del cliente.</p>
        <label className="chk"><input type="checkbox" checked={sc.on} onChange={(e) => setSc({ ...sc, on: e.target.checked })} /> Activar la tarjeta de sellos</label>
        <div className="grid2">
          <div><label>Sellos para ganar el premio</label><input type="number" min={2} max={30} value={sc.goal} onChange={(e) => setSc({ ...sc, goal: e.target.value })} /></div>
          <div><label>Premio</label><input maxLength={80} placeholder="Un postre gratis" value={sc.reward} onChange={(e) => setSc({ ...sc, reward: e.target.value })} /></div>
        </div>
        <p style={{ marginBottom: 0 }}><button className="btn sm" onClick={saveStamps}>Guardar tarjeta de sellos</button></p>
      </div>
      {list.length > 5 && <input placeholder="Buscar por nombre, cédula, correo o celular…" value={q} onChange={(e) => setQ(e.target.value)} />}
      <div className="card" style={{ marginTop: ".8rem" }}>
        {shown.map((c) => (
          <div className="mi" key={c.id}>
            <div className="grow">
              <b>{c.name}</b>
              <div className="muted small">CC {c.document} · {c.phone} · {c.email}</div>
            </div>
            {r.stamps_on ? <><span className="pill ok">{Math.min(c.stamps, r.stamps_goal)}/{r.stamps_goal} sellos</span><button className="btn sm ghost" onClick={() => openCard(c)}>Tarjeta</button></> : null}
            <button className="btn sm ghost" title="Eliminar" onClick={() => remove(c)} aria-label="Eliminar"><Icon n="close" /></button>
          </div>
        ))}
        {!shown.length && <p className="muted">{list.length ? "Sin resultados." : "Aún no tienes clientes fidelizados. Agrega el primero con «+ Agregar cliente»."}</p>}
      </div>

      <Modal open={!!cardOf} onClose={() => setCardOf(null)}>
        {cardOf && (
          <div style={{ textAlign: "center" }}>
            <h2>{cardOf.name}</h2>
            <p className="muted">{Math.min(cardOf.stamps, r.stamps_goal)} de {r.stamps_goal} sellos{cardOf.stamps >= r.stamps_goal ? " · ¡premio disponible!" : ""}</p>
            <img src={`/api/qr/card/${cardOf.id}.svg`} alt="QR de la tarjeta" style={{ width: 200, background: "#fff", borderRadius: 12, padding: 8 }} />
            <p className="muted small" style={{ wordBreak: "break-all" }}>{cardUrl}</p>
            <div className="row wrap" style={{ justifyContent: "center" }}>
              <button className="btn sm" onClick={() => stampAct("stamp")}>Sumar sello</button>
              <button className="btn sm ok" disabled={cardOf.stamps < r.stamps_goal} onClick={() => stampAct("redeem")}>Canjear premio</button>
              <button className="btn sm ghost" onClick={() => { navigator.clipboard?.writeText(cardUrl); toast("Enlace copiado"); }}>Copiar enlace</button>
              {typeof window !== "undefined" && "NDEFReader" in window && <button className="btn sm ghost" onClick={writeNfc}>Grabar en tarjeta NFC</button>}
            </div>
            <p className="muted small">El QR o la tarjeta NFC abren esta tarjeta en el celular. Cuando el equipo (con su sesión abierta) la abre, ve los botones para sumar sello o canjear el premio.</p>
          </div>
        )}
      </Modal>

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
