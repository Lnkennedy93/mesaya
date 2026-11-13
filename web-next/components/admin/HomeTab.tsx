"use client";
import { useEffect, useState } from "react";
import { api, localDay } from "@/lib/api";
import { Any, useAdmin } from "./ctx";
import Icon from "@/components/Icon";

export default function HomeTab() {
  const { ME, money, toast } = useAdmin();
  const [days, setDays] = useState(7);
  const [a, setA] = useState<Any>(null);
  // pedidos por mesa: filtro de mesa y fechas (en la hora del negocio); por defecto, los últimos 7 días
  const tz = ME.restaurant.tz_offset || 0;
  const today = localDay(new Date().toISOString().slice(0, 19).replace("T", " "), tz);
  const [table, setTable] = useState("");
  const [from, setFrom] = useState(() => new Date(+new Date(today + "T00:00:00Z") - 6 * 86400000).toISOString().slice(0, 10));
  const [to, setTo] = useState(today);
  const [h, setH] = useState<Any>(null);
  const qs = `from=${from}&to=${to}&table=${encodeURIComponent(table)}`;

  useEffect(() => {
    if (!from || !to) return;
    let dead = false;
    api("/api/orders/history?" + qs).then((r) => { if (!dead) setH(r); }).catch((e) => { if (!dead) toast(e.message, true); });
    return () => { dead = true; };
  }, [qs, from, to, toast]);

  useEffect(() => {
    let dead = false;
    api("/api/analytics?days=" + days).then((r) => { if (!dead) setA(r); }).catch((e) => toast(e.message, true));
    return () => { dead = true; };
  }, [days, toast]);

  if (!a) return <p className="muted">Cargando…</p>;
  const maxS = Math.max(1, ...a.daily.map((d: Any) => d.sales));
  const maxH = Math.max(1, ...a.hourly);
  const kpis: [string, Any, number[]?][] = [
    ["Ventas", money(a.sales), a.daily.map((d: Any) => d.sales)], ["Pedidos", a.orders, a.daily.map((d: Any) => d.orders)], ["Ticket promedio", money(a.avg_ticket)],
    ...(ME.features.payments ? ([["Propinas", money(a.tips)]] as [string, Any][]) : []),
    ["Tiempo a cocina", a.avg_prep_min === null ? "—" : a.avg_prep_min + " min"],
    ["Opiniones", a.rating_avg ? <>{a.rating_avg} <Icon n="star" /> ({a.rating_count})</> : "—"],
  ];
  // mini-barras de los últimos días (la última, en verde): la tendencia se ve de un vistazo, sin abrir la gráfica
  const spark = (s?: number[]) => {
    if (!s || s.length < 2) return null;
    const last = s.slice(-14), top = Math.max(1, ...last);
    return <div className="spark" aria-hidden="true">{last.map((v, i) => <i key={i} className={i === last.length - 1 ? "" : "m"} style={{ height: Math.max(8, (v / top) * 100) + "%" }}></i>)}</div>;
  };

  return (
    <>
      <div className="row spread wrap">
        <h1>Resumen</h1>
        <select style={{ width: "auto" }} value={days} onChange={(e) => setDays(+e.target.value)}>
          {[1, 7, 30, 90].map((d) => <option key={d} value={d}>{d === 1 ? "Hoy / 24 h" : "Últimos " + d + " días"}</option>)}
        </select>
      </div>
      <div className="card row wrap spread">
        <div><b>Link de tu carta</b><div className="muted small">{ME.public_url}</div></div>
        <div className="row">
          <button className="btn sm ghost" onClick={() => { navigator.clipboard.writeText(ME.public_url); toast("Link copiado"); }}>Copiar</button>
          <a className="btn sm" href="/print/qr" target="_blank">Imprimir QR de mesas</a>
        </div>
      </div>
      <div className="kpis">
        {kpis.map(([k, v, s]) => <div className="card kpi" key={k}><div className="muted small">{k}</div><div className="v">{v}</div>{spark(s)}</div>)}
      </div>
      <div className="card">
        <b>Ventas por día</b>
        <div className="bars">
          {a.daily.length ? a.daily.map((d: Any) => <div key={d.date} style={{ height: (d.sales / maxS) * 100 + "%" }} data-t={`${d.date}: ${money(d.sales)}`}></div>) : <span className="muted small">Aún sin ventas</span>}
        </div>
        <div className="axis">{a.daily.map((d: Any) => <span key={d.date}>{d.date.slice(8)}</span>)}</div>
      </div>
      <div className="grid2" style={{ marginTop: ".8rem" }}>
        <div className="card">
          <b>Horas pico</b>
          <div className="bars" style={{ height: 100 }}>
            {a.hourly.map((v: number, h: number) => <div key={h} style={{ height: (v / maxH) * 100 + "%" }} data-t={`${h}:00 · ${v} pedidos`}></div>)}
          </div>
          <div className="axis">{a.hourly.map((_: number, h: number) => <span key={h}>{h % 3 === 0 ? h : ""}</span>)}</div>
        </div>
        <div className="card">
          <b>Platos más vendidos</b>
          <table>
            <tbody>
              {a.top.length ? a.top.map((t: Any) => <tr key={t.name}><td>{t.name}</td><td>{t.qty}×</td><td>{money(t.revenue)}</td></tr>) : <tr><td className="muted">Sin datos</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card" style={{ marginTop: ".8rem" }}>
        <b>Pedidos por mesa</b>
        <p className="muted small" style={{ margin: ".2rem 0 .6rem" }}>Filtra por mesa y fechas para ver cuántos pedidos tuvo cada una y qué pidió el cliente, con el valor de cada pedido.</p>
        <div className="row wrap">
          <div><label htmlFor="h-mesa">Mesa</label>
            <select id="h-mesa" value={table} onChange={(e) => setTable(e.target.value)}>
              <option value="">Todas las mesas</option>
              {(h?.tables || []).map((t: Any) => <option key={t.table} value={t.table}>{t.label} ({t.orders})</option>)}
              {table && !(h?.tables || []).some((t: Any) => t.table === table) && <option value={table}>{table === "PL" ? "Para llevar" : "Mesa " + table}</option>}
            </select>
          </div>
          <div><label htmlFor="h-desde">Desde</label><input id="h-desde" type="date" max={to} value={from} onChange={(e) => setFrom(e.target.value)} /></div>
          <div><label htmlFor="h-hasta">Hasta</label><input id="h-hasta" type="date" min={from} max={today} value={to} onChange={(e) => setTo(e.target.value)} /></div>
        </div>
        {h && (
          <>
            <div className="row wrap" style={{ margin: ".6rem 0" }}>
              {h.tables.map((t: Any) => (
                <button key={t.table} className={"chip" + (table === t.table ? " on" : "")} aria-pressed={table === t.table} onClick={() => setTable(table === t.table ? "" : t.table)}>
                  {t.label}: {t.orders} {t.orders === 1 ? "pedido" : "pedidos"} · {money(t.total)}
                </button>
              ))}
              {!h.tables.length && <span className="muted small">Sin pedidos en estas fechas.</span>}
            </div>
            {h.orders.length > 0 && <p className="muted small" style={{ margin: ".2rem 0 .4rem" }}>{h.count} {h.count === 1 ? "pedido" : "pedidos"} · {money(h.total)}{table ? " en " + (table === "PL" ? "Para llevar" : "la mesa " + table) : " en total"}{h.truncated ? " (se muestran los 300 más recientes)" : ""}</p>}
            {h.orders.map((o: Any) => (
              <details key={o.id} className="ordrow">
                <summary>
                  <span><b>#{o.seq}</b> · {o.takeaway ? "Para llevar" : "Mesa " + o.table_label} · {o.local_time}{o.diner_name ? " · " + o.diner_name : ""}{o.status === "cancelled" && <> <span className="pill bad">cancelado</span></>}</span>
                  <b>{money(o.total)}</b>
                </summary>
                <table>
                  <tbody>
                    {o.items.map((i: Any, k: number) => (
                      <tr key={k}><td>{i.qty}× {i.name}{i.options ? <div className="muted small">{i.options}</div> : null}{i.note ? <div className="muted small">Nota: {i.note}</div> : null}</td><td>{money(i.unit_price)}</td><td><b>{money(i.line_total)}</b></td></tr>
                    ))}
                  </tbody>
                </table>
                {o.note ? <p className="muted small" style={{ margin: ".3rem 0 0" }}>Nota del pedido: {o.note}</p> : null}
              </details>
            ))}
          </>
        )}
      </div>
      <p><a className="btn ghost sm" href={"/api/export/orders.csv?" + qs}><Icon n="download" /> Exportar lo filtrado (CSV)</a> <a className="btn ghost sm" href="/api/export/orders.csv"><Icon n="download" /> Exportar todo (CSV)</a></p>
    </>
  );
}
