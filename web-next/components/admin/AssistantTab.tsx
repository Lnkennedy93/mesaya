"use client";
// Asistente del dueño: pregunta en lenguaje natural por ventas, platos, tiempos de cocina y platos apagados.
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Any, useAdmin } from "./ctx";
import Icon from "@/components/Icon";

type Msg = { role: "user" | "assistant"; text: string; actions?: Any[] };

const IDEAS = [
  "¿Cuántos platos vendí esta semana?",
  "¿Cuánta plata se movió hoy?",
  "¿Cuánto se demora la cocina en sacar un pedido?",
  "¿Qué platos están apagados?",
];

export default function AssistantTab() {
  const { ME, toast } = useAdmin();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState<number | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, busy]);

  if (!ME.plan.ai_asks) {
    return (
      <>
        <h1>Asistente</h1>
        <div className="card">
          <b>Pregúntale a tu negocio</b>
          <p className="muted">Cuántos platos se vendieron, cuánto dinero se movió, cuánto demora la cocina y qué platos se apagaron, en una sola pregunta.</p>
          <p>Incluido en <b>Pro</b> y <b>Cadena</b>. En el plan Esencial se activa como complemento: <b>120 preguntas al mes por $12.000</b>.</p>
          <a className="btn sm" href={`mailto:ventas@mesaya.app?subject=Activar%20asistente%20IA%20${encodeURIComponent(ME.restaurant.slug)}`}>Activar el asistente</a>
        </div>
      </>
    );
  }

  async function ask(text: string) {
    text = text.trim();
    if (!text || busy) return;
    const history = msgs.map((m) => ({ role: m.role, text: m.text }));
    setMsgs((m) => [...m, { role: "user", text }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api<Any>("/api/assistant", { method: "POST", body: { question: text, history } });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, actions: r.actions }]);
      setLeft(r.asks_left);
    } catch (e: Any) {
      toast(e.message, true);
      setMsgs((m) => m.slice(0, -1));
      setQ(text);
    } finally {
      setBusy(false);
    }
  }

  async function apply(a: Any) {
    try {
      await api(`/api/items/${a.item_id}/availability`, { method: "POST", body: { available: a.available } });
      setDone((d) => ({ ...d, [a.item_id + ":" + a.available]: true }));
      toast(a.available ? `«${a.name}» disponible` : `«${a.name}» apagado`);
    } catch (e: Any) {
      toast(e.message, true);
    }
  }

  return (
    <>
      <div className="row spread wrap">
        <h1>Asistente</h1>
        {left !== null && <span className="muted small">{left} preguntas restantes este mes</span>}
      </div>
      <div className="card" style={{ minHeight: 260 }}>
        {!msgs.length && (
          <>
            <p className="muted">Pregunta por tu negocio con tus palabras. Responde con los datos reales de tus pedidos.</p>
            <div className="row wrap">
              {IDEAS.map((t) => <button key={t} className="btn sm ghost" onClick={() => ask(t)}>{t}</button>)}
            </div>
          </>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ margin: ".7rem 0", textAlign: m.role === "user" ? "right" : "left" }}>
            <div style={{ display: "inline-block", maxWidth: "min(46rem,92%)", padding: ".6rem .9rem", borderRadius: 12, whiteSpace: "pre-wrap", textAlign: "left",
              background: m.role === "user" ? "var(--brand)" : "color-mix(in srgb,var(--ink) 7%,transparent)", color: m.role === "user" ? "var(--brand-ink)" : "inherit" }}>
              {m.text}
            </div>
            {m.actions?.map((a) => {
              const k = a.item_id + ":" + a.available;
              return (
                <div key={k} style={{ marginTop: ".4rem" }}>
                  <button className="btn sm" disabled={done[k]} onClick={() => apply(a)}>
                    {done[k] ? <><Icon n="check" /> Hecho</> : a.available ? `Encender «${a.name}»` : `Apagar «${a.name}»`}
                  </button>
                </div>
              );
            })}
          </div>
        ))}
        {busy && <p className="muted">Consultando tus datos…</p>}
        <div ref={end} />
      </div>
      <form className="row" style={{ marginTop: ".8rem" }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input value={q} maxLength={500} onChange={(e) => setQ(e.target.value)} placeholder="Escribe tu pregunta…" aria-label="Pregunta" style={{ flex: 1 }} />
        <button className="btn" disabled={busy || q.trim().length < 2}>Preguntar</button>
      </form>
    </>
  );
}
