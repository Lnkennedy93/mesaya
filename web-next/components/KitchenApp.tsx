"use client";
// Cocina y sala (portada de web/kitchen.html). Mismos endpoints /api/... y el mismo canal en vivo /api/stream.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, beep, poll, makeMoney, secsSince, setBrand } from "@/lib/api";
import Powered from "@/components/Powered";
import { useToast } from "@/components/useToast";

type Any = any;
type Tab = "kitchen" | "floor" | "stock";

const NEXT: Record<string, [string, string]> = { new: ["preparing", "Preparar"], preparing: ["ready", "Listo"], ready: ["served", "Entregado"] };

export default function KitchenApp({ slugHint }: { slugHint: string }) {
  const [phase, setPhase] = useState<"boot" | "login" | "ready">("boot");
  const [ME, setME] = useState<Any>(null);
  const [orders, setOrders] = useState<Any[]>([]);
  const [calls, setCalls] = useState<Any[]>([]);
  const [floor, setFloor] = useState<Any[]>([]);
  const [menu, setMenu] = useState<Any[]>([]);
  const [reviews, setReviews] = useState<Any[]>([]);
  const [tab, setTab] = useState<Tab>("kitchen");
  const [sound, setSound] = useState(true);
  const [tableOpen, setTableOpen] = useState<string | null>(null);
  const [, setTick] = useState(0);
  const [toastNode, toast] = useToast();

  // lo que necesita el refresco aunque llegue desde el canal en vivo (valores "actuales", no los del primer render)
  const live = useRef({ first: true, known: new Set<number>(), calls: [] as Any[], reviews: [] as Any[], sound: true });
  live.current.sound = sound;

  const refresh = useCallback(async () => {
    const [o, c, f, m, rv] = await Promise.all([api("/api/orders"), api("/api/calls"), api("/api/floor"), api("/api/menu"), api("/api/payments/review")]);
    const L = live.current;
    if (!L.first && rv.payments.some((x: Any) => !L.reviews.some((y) => y.id === x.id)) && L.sound) beep();
    L.reviews = rv.payments;
    const fresh = o.orders.filter((x: Any) => x.status === "new" && !L.known.has(x.id));
    if (!L.first && fresh.length && L.sound) beep();
    const newCalls = c.calls.filter((x: Any) => !L.calls.some((y) => y.id === x.id));
    if (!L.first && newCalls.length && L.sound) beep();
    L.known = new Set(o.orders.map((x: Any) => x.id));
    L.calls = c.calls;
    L.first = false;
    setReviews(rv.payments);
    setOrders(o.orders);
    setCalls(c.calls);
    setFloor(f.tables);
    setMenu(m.categories);
  }, []);
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  const safeRefresh = () => refreshRef.current().catch(() => {});

  useEffect(() => {
    let stop: (() => void) | undefined;
    let timer: ReturnType<typeof setInterval> | undefined;
    let dead = false;
    (async () => {
      let me: Any;
      try {
        me = await api("/api/me");
      } catch {
        if (!dead) setPhase("login");
        return;
      }
      if (dead) return;
      setME(me);
      setBrand(me.restaurant.brand_color);
      await refreshRef.current();
      if (dead) return;
      setPhase("ready");
      const go = () => { refreshRef.current().catch(() => {}); };
      stop = poll(go, 5000);
      timer = setInterval(() => setTick((t) => t + 1), 15000); // actualiza los minutos de cada ticket
    })();
    return () => { dead = true; stop?.(); if (timer) clearInterval(timer); };
  }, []);

  if (phase === "boot") return <div className="kitchen-root" />;
  if (phase === "login") return <StaffLogin slugHint={slugHint} toast={toast} toastNode={toastNode} />;

  const money = makeMoney(ME.restaurant.decimals, ME.restaurant.currency);
  const nNew = orders.filter((o) => o.status === "new").length;

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); } catch (e: Any) { toast(e.message, true); }
    safeRefresh();
  }

  return (
    <div className="kitchen-root">
      <header>
        <h1>{ME.restaurant.name}</h1>
        <div className="tabs">
          <button className={tab === "kitchen" ? "on" : ""} onClick={() => setTab("kitchen")}>Cocina{nNew ? ` · ${nNew}` : ""}</button>
          <button className={tab === "floor" ? "on" : ""} onClick={() => setTab("floor")}>Sala{calls.length ? ` · ${calls.length}` : ""}</button>
          <button className={tab === "stock" ? "on" : ""} onClick={() => setTab("stock")}>Agotados</button>
        </div>
        <span className="grow"></span>
        <button className="btn sm ghost" onClick={() => { const n = !sound; setSound(n); if (n) beep(); }}>{sound ? "🔔 Sonido" : "🔕 Silencio"}</button>
        {ME.role === "owner" && <a className="btn sm ghost" href="/admin">Panel</a>}
        <button className="btn sm ghost" onClick={async () => { await api("/api/logout", { method: "POST" }); location.reload(); }}>Salir</button>
      </header>

      <div className="calls">
        {reviews.map((p) => (
          <div className="call" style={{ background: "#1d3f5a", animation: "none" }} key={"p" + p.id}>
            <b>💸 Confirmar Bre-B · Mesa {p.table_label} · {money(p.total)}</b>
            <span className="muted small">ref {p.reference.slice(-6).toUpperCase()}</span>
            <button className="btn sm ok" onClick={() => act(async () => { await api(`/api/payments/${p.id}/confirm`, { method: "POST" }); toast("Pago confirmado ✓"); })}>Ya llegó</button>
            <button className="btn sm ghost" onClick={() => { if (confirm("¿El dinero NO llegó a tu cuenta? Se liberará la cuenta del cliente.")) act(() => api(`/api/payments/${p.id}/reject`, { method: "POST" })); }}>No llegó</button>
          </div>
        ))}
        {calls.map((c) => (
          <div className="call" key={"c" + c.id}>
            <b>{c.type === "bill" ? "🧾 Cuenta" : "🙋 Mesero"} · Mesa {c.table_label}</b>
            <button className="btn sm" onClick={() => act(() => api(`/api/calls/${c.id}/resolve`, { method: "POST" }))}>Atendido</button>
          </div>
        ))}
      </div>

      {tab === "kitchen" && (
        <div className="cols">
          {([["new", "Nuevos"], ["preparing", "En preparación"], ["ready", "Listos para servir"]] as const).map(([st, title]) => {
            const list = orders.filter((o) => o.status === st);
            return (
              <div className="col" key={st}>
                <h2>{title} ({list.length})</h2>
                {list.map((o) => {
                  const mins = secsSince(o.created_at) / 60;
                  const cls = st === "ready" ? "" : mins > 15 ? "late" : mins > 8 ? "warn" : "";
                  return (
                    <div className={"ticket " + cls} key={o.id}>
                      <div className="row spread"><span className="t">Mesa {o.table_label}</span><span className="muted">#{o.seq} · {Math.floor(mins)} min</span></div>
                      <ul>
                        {o.items.map((i: Any, n: number) => (
                          <li key={n}>
                            <span className="q">{i.qty}</span><b>{i.name}</b>
                            {i.options_text && <div className="muted small">{i.options_text}</div>}
                            {i.note && <div className="note">“{i.note}”</div>}
                          </li>
                        ))}
                      </ul>
                      {o.note && <div className="note">📝 {o.note}</div>}
                      {o.diner_name && <div className="muted small">{o.diner_name}</div>}
                      <div className="row" style={{ marginTop: ".6rem" }}>
                        <button className={"btn grow " + (st === "ready" ? "ok" : "")} onClick={() => act(() => api(`/api/orders/${o.id}/status`, { method: "POST", body: { status: NEXT[st][0] } }))}>{NEXT[st][1]}</button>
                        <button className="btn ghost sm" onClick={() => { if (confirm("¿Cancelar este pedido?")) act(() => api(`/api/orders/${o.id}/status`, { method: "POST", body: { status: "cancelled" } })); }}>✕</button>
                      </div>
                    </div>
                  );
                })}
                {!list.length && <p className="muted small">—</p>}
              </div>
            );
          })}
        </div>
      )}

      {tab === "floor" && (
        <div className="floor">
          {floor.map((t) => (
            <div className={"tb " + (t.calls.length ? "call" : t.unpaid ? "occ" : t.has_paid ? "done" : "")} key={t.label} onClick={() => setTableOpen(t.label)}>
              <span className="muted small">Mesa</span><b>{t.label}</b>
              {t.unpaid ? <div>{money(t.unpaid)}</div> : <div className="muted small">libre</div>}
              <div className="small">{t.active ? `🍳 ${t.active} en cocina` : ""}{t.calls.length ? " 🔔" : ""}</div>
            </div>
          ))}
        </div>
      )}

      {tab === "stock" && (
        <div className="pad" style={{ maxWidth: 640, margin: "auto" }}>
          <p className="muted">Apaga un plato cuando se agote: desaparece al instante de los celulares de los clientes.</p>
          {menu.map((c) => (
            <div key={c.id}>
              <h3 style={{ marginTop: "1.2rem" }}>{c.name}</h3>
              {c.items.map((i: Any) => (
                <div className="line" key={i.id}>
                  <div className="grow">{i.name}</div>
                  <span className="small muted">{i.available ? "Disponible" : <b style={{ color: "#ff8a8a" }}>AGOTADO</b>}</span>
                  <label className="switch" style={{ margin: 0 }}>
                    <input type="checkbox" checked={i.available} onChange={(e) => act(async () => { await api(`/api/items/${i.id}/availability`, { method: "POST", body: { available: e.target.checked } }); toast(e.target.checked ? "Disponible de nuevo" : "Plato apagado"); })} />
                    <span></span>
                  </label>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <TableDialog label={tableOpen} ME={ME} money={money} onClose={() => setTableOpen(null)}
        onSettled={() => { setTableOpen(null); toast("Mesa cerrada ✓"); safeRefresh(); }} onError={(m) => toast(m, true)} />
      {toastNode}
      <Powered />
    </div>
  );
}

function StaffLogin({ slugHint, toast, toastNode }: { slugHint: string; toast: (t: string, e?: boolean) => void; toastNode: React.ReactNode }) {
  const [slug, setSlug] = useState(slugHint);
  const [pin, setPin] = useState("");
  async function enter() {
    try {
      await api("/api/staff-login", { method: "POST", body: { slug, pin } });
      location.reload();
    } catch (e: Any) { toast(e.message, true); }
  }
  return (
    <div className="kitchen-root">
      <div className="card login">
        <h2>Cocina y sala</h2>
        <p className="muted small">Ingresa el código de tu restaurante y el PIN del equipo (lo encuentras en Ajustes del panel).</p>
        <label>Restaurante (código)</label>
        <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="dragon-dorado" autoCapitalize="off" />
        <label>PIN</label>
        <input type="password" inputMode="numeric" maxLength={8} value={pin} onChange={(e) => setPin(e.target.value)} onKeyDown={(e) => e.key === "Enter" && enter()} />
        <button className="btn block" style={{ marginTop: "1rem" }} onClick={enter}>Entrar</button>
        <p className="small muted" style={{ marginTop: "1rem" }}>¿Eres el dueño? <a href="/login">Entra al panel</a></p>
      </div>
      {toastNode}
      <Powered />
    </div>
  );
}

function TableDialog({ label, ME, money, onClose, onSettled, onError }: { label: string | null; ME: Any; money: (v: number) => string; onClose: () => void; onSettled: () => void; onError: (m: string) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [lines, setLines] = useState<Any[] | null>(null);
  const [inv, setInv] = useState({ doc_type: "CC", doc_number: "", name: "", email: "" });

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (label === null) { if (d.open) d.close(); return; }
    let dead = false;
    setLines(null);
    setInv({ doc_type: "CC", doc_number: "", name: "", email: "" });
    api(`/api/floor/${encodeURIComponent(label)}`).then((r) => { if (!dead) { setLines(r.lines); if (!d.open) d.showModal(); } }).catch((e) => { onError(e.message); onClose(); });
    return () => { dead = true; };
  }, [label]); // eslint-disable-line react-hooks/exhaustive-deps

  const L = lines || [];
  const total = L.filter((l) => l.state === "unpaid").reduce((s, l) => s + l.line_total, 0);

  async function settle(method: string) {
    try {
      const invoice = inv.doc_number && inv.name ? inv : null;
      await api(`/api/floor/${encodeURIComponent(label!)}/settle`, { method: "POST", body: { method, invoice } });
      onSettled();
    } catch (e: Any) { onError(e.message); }
  }

  return (
    <dialog ref={ref} onClose={onClose}>
      <div className="dlg">
        {label !== null && lines && (
          <>
            <div className="row spread"><h2 style={{ margin: 0 }}>Mesa {label}</h2><button style={{ color: "#fff", background: "none", border: 0, fontSize: "1.6rem" }} onClick={onClose}>×</button></div>
            {L.map((l) => (
              <div className="line" key={l.id}>
                <div className="grow">{l.qty}× {l.name} <span className="muted small">{l.diner_name || ""}</span></div>
                <span>{l.state === "paid" ? <span className="pill ok">PAGADO</span> : money(l.line_total)}</span>
              </div>
            ))}
            {!L.length && <p className="muted">Sin consumo reciente</p>}
            <div className="row spread" style={{ margin: ".8rem 0" }}><b>Por cobrar</b><b className="big" style={{ fontSize: "1.4rem" }}>{money(total)}</b></div>
            {ME.features.invoicing && ME.restaurant.inv_provider !== "none" && total > 0 && (
              <>
                <details style={{ margin: ".4rem 0" }}>
                  <summary style={{ cursor: "pointer" }}>🧾 Factura a nombre del cliente (opcional)</summary>
                  <div className="row" style={{ marginTop: ".4rem" }}>
                    <select style={{ width: "35%" }} value={inv.doc_type} onChange={(e) => setInv({ ...inv, doc_type: e.target.value })}>
                      <option>CC</option><option>NIT</option><option>CE</option><option value="PP">Pasaporte</option>
                    </select>
                    <input placeholder="Documento" inputMode="numeric" value={inv.doc_number} onChange={(e) => setInv({ ...inv, doc_number: e.target.value })} />
                  </div>
                  <input placeholder="Nombre o razón social" style={{ marginTop: ".4rem" }} value={inv.name} onChange={(e) => setInv({ ...inv, name: e.target.value })} />
                  <input type="email" placeholder="Correo" style={{ marginTop: ".4rem" }} value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} />
                </details>
                <p className="muted small" style={{ margin: ".2rem 0 .6rem" }}>Sin datos se factura a Consumidor Final.</p>
              </>
            )}
            {ME.features.payments ? (
              <div className="row">
                <button className="btn grow ok" disabled={!total} onClick={() => settle("cash")}>Cobrado en efectivo</button>
                <button className="btn grow" disabled={!total} onClick={() => settle("card")}>Cobrado con datáfono</button>
              </div>
            ) : (
              <>
                <button className="btn block ok" disabled={!total} onClick={() => settle("cash")}>✅ Cerrar mesa (cuenta cobrada)</button>
                <p className="muted small" style={{ margin: ".4rem 0 0" }}>Cobra en caja como siempre y cierra la mesa para dejarla libre.</p>
              </>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}
