"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Any, useAdmin } from "./ctx";

export default function HomeTab() {
  const { ME, money, toast } = useAdmin();
  const [days, setDays] = useState(7);
  const [a, setA] = useState<Any>(null);

  useEffect(() => {
    let dead = false;
    api("/api/analytics?days=" + days).then((r) => { if (!dead) setA(r); }).catch((e) => toast(e.message, true));
    return () => { dead = true; };
  }, [days, toast]);

  if (!a) return <p className="muted">Cargando…</p>;
  const maxS = Math.max(1, ...a.daily.map((d: Any) => d.sales));
  const maxH = Math.max(1, ...a.hourly);
  const kpis: [string, Any][] = [
    ["Ventas", money(a.sales)], ["Pedidos", a.orders], ["Ticket promedio", money(a.avg_ticket)],
    ...(ME.features.payments ? ([["Propinas", money(a.tips)]] as [string, Any][]) : []),
    ["Tiempo a cocina", a.avg_prep_min === null ? "—" : a.avg_prep_min + " min"],
    ["Opiniones", a.rating_avg ? a.rating_avg + " ★ (" + a.rating_count + ")" : "—"],
  ];

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
        {kpis.map(([k, v]) => <div className="card kpi" key={k}><div className="muted small">{k}</div><div className="v">{v}</div></div>)}
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
      <p><a className="btn ghost sm" href="/api/export/orders.csv">⬇ Exportar pedidos (CSV)</a></p>
    </>
  );
}
