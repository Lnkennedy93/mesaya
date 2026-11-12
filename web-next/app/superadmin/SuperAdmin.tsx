"use client";
// Superusuario: ve todos los negocios y gestiona plan, mesas, IA y contraseña. Se entra con MESAYA_ADMIN_KEY.
import { useCallback, useEffect, useState } from "react";
import { api, localDay } from "@/lib/api";
import { useToast } from "@/components/useToast";

type Biz = {
  id: number; slug: string; name: string; email: string; plan: string; subscription_status: string; trial_ends_at: string;
  created_at: string; extra_tables: number; ai_addon: number; tables_used: number; active: boolean; effective_plan: string;
  tables_limit: number; ai_asks: number; disabled_modules: string[]; paid_until: string; cancel_requested_at: string; license_start: string; tz_offset: number;
};

const MODS: [string, string][] = [["home", "Resumen"], ["menu", "Carta"], ["tables", "Mesas y QR"], ["reviews", "Opiniones"], ["customers", "Fidelización Clientes"],
  ["assistant", "Asistente"], ["settings", "Ajustes"], ["takeaway", "Para llevar"]];

const PLAN_LABEL: Record<string, string> = { basic: "Esencial", pro: "Pro", chain: "Cadena" };

function Row({ b, call }: { b: Biz; call: (path: string, body: object, ok: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState(b.plan);
  const [extra, setExtra] = useState(String(b.extra_tables));
  const [ai, setAi] = useState(!!b.ai_addon);
  const [pw, setPw] = useState("");
  const [off, setOff] = useState<string[]>(b.disabled_modules || []);
  const tz = b.tz_offset || 0;
  const nowUtc = new Date().toISOString().slice(0, 19).replace("T", " ");
  const today = localDay(nowUtc, tz);
  const plusDays = (d: string, n: number) => new Date(+new Date(d + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
  const [period, setPeriod] = useState("dates"); // «dates» = elegir inicio y fin en el calendario; lo demás suma días al activar o renovar
  const [from, setFrom] = useState(b.license_start ? localDay(b.license_start, tz) : today);
  const [to, setTo] = useState(b.subscription_status === "active" && b.paid_until ? localDay(b.paid_until, tz) : plusDays(today, 30));
  const scheduled = b.subscription_status === "active" && !!b.license_start && b.license_start > nowUtc;
  const span = Math.round((+new Date(to + "T00:00:00Z") - +new Date(from + "T00:00:00Z")) / 86400000) + 1;
  const status = scheduled ? <span className="pill warn">Programada</span>
    : b.subscription_status === "active" ? (b.active ? <span className="pill ok">Activa</span> : <span className="pill bad">Vencida (Gratis)</span>)
    : b.active ? <span className="pill warn">En prueba</span> : <span className="pill bad">Sin licencia (Gratis)</span>;
  const save = (st: "active" | "inactive") =>
    call("activate", { email: b.email, plan, status: st, extra_tables: +extra || 0, ai_addon: ai,
      ...(st !== "active" || period === "keep" ? {} : period === "dates" ? { starts_on: from, ends_on: to } : period === "none" ? { no_expiry: true } : { period_days: +period }) }, st === "active" ? "Licencia guardada" : "Licencia desactivada");

  return (
    <div className="card biz">
      <div className="biz-head" onClick={() => setOpen(!open)}>
        <div>
          <b>{b.name}</b> <span className="muted small">{b.email}</span>
        </div>
        <div className="stat">
          {status}
          <span className="pill brand">{b.effective_plan}</span>
          <span className="pill">{b.tables_used}/{b.tables_limit} mesas</span>
          {b.ai_asks > 0 && <span className="pill ok">IA {b.ai_asks}/mes</span>}
          {b.disabled_modules.length > 0 && <span className="pill warn">{b.disabled_modules.length} funciones apagadas</span>}
          {scheduled && <span className="pill">inicia {localDay(b.license_start, tz)}</span>}
          {b.subscription_status === "active" && b.paid_until && <span className={"pill" + (b.active || scheduled ? "" : " bad")}>{b.active || scheduled ? "vence " : "venció "}{localDay(b.paid_until, tz)}</span>}
          {b.cancel_requested_at && <span className="pill warn">cancelación pedida</span>}
        </div>
      </div>
      {open && (
        <>
          <div className="ctl">
            <div>
              <label>Licencia</label>
              <select value={plan} onChange={(e) => setPlan(e.target.value)}>
                {Object.entries(PLAN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label>Mesas adicionales (sobre las del plan)</label>
              <input type="number" min={0} max={500} value={extra} onChange={(e) => setExtra(e.target.value)} />
            </div>
            <div>
              <label>Herramienta de IA (solo plan Esencial)</label>
              <div className="sw">
                <label className="switch"><input type="checkbox" checked={ai} disabled={plan !== "basic"} onChange={(e) => setAi(e.target.checked)} /><span /></label>
                <span>{plan !== "basic" ? "Incluida en el plan" : ai ? "Activada (120 preguntas/mes)" : "Desactivada"}</span>
              </div>
            </div>
          </div>
          <div className="ctl">
            <div>
              <label>Vigencia al activar o renovar</label>
              <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                <option value="dates">Elegir inicio y fin en el calendario</option>
                <option value="30">+30 días (suma a lo que le quede)</option>
                <option value="90">+90 días</option>
                <option value="365">+1 año</option>
                <option value="none">Sin vencimiento (demo)</option>
                <option value="keep">Mantener la fecha actual</option>
              </select>
            </div>
            {period === "dates" && (
              <>
                <div>
                  <label>Inicia el</label>
                  <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); if (to < e.target.value) setTo(e.target.value); }} />
                </div>
                <div>
                  <label>Finaliza el</label>
                  <input type="date" min={from} value={to} onChange={(e) => setTo(e.target.value)} />
                </div>
              </>
            )}
          </div>
          {period === "dates" && (
            <p className="muted small" style={{ margin: "0 0 .6rem" }}>
              Vigencia: <b>{from}</b> → <b>{to}</b> ({span} {span === 1 ? "día" : "días"}; el día de fin se incluye completo, en la hora del negocio).
              {from > today && " Quedará programada: hasta esa fecha el negocio sigue como está (prueba o plan Gratis)."}
            </p>
          )}
          <div className="acts">
            <button className="btn ok sm" onClick={() => save("active")}>Guardar y activar licencia</button>
            <button className="btn bad sm" onClick={() => confirm(`¿Desactivar la licencia de ${b.name}? Pasará al plan Gratis.`) && save("inactive")}>Desactivar licencia</button>
          </div>
          <label style={{ marginTop: "1rem" }}>Funciones del panel (apaga las que este negocio no debe usar)</label>
          <div className="mods">
            {MODS.map(([k, l]) => (
              <label key={k}>
                <span className="switch"><input type="checkbox" checked={!off.includes(k)} onChange={(e) => setOff(e.target.checked ? off.filter((x) => x !== k) : [...off, k])} /><span /></span>
                {l}
              </label>
            ))}
          </div>
          <div className="acts"><button className="btn dark sm" onClick={() => call("modules", { email: b.email, disabled: off }, "Funciones guardadas")}>Guardar funciones</button></div>
          <div className="ctl">
            <div>
              <label>Nueva contraseña (mínimo 8)</label>
              <input type="text" autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} />
            </div>
            <div style={{ alignSelf: "end" }}>
              <button className="btn dark sm" disabled={pw.length < 8}
                onClick={() => call("set-password", { email: b.email, password: pw }, "Contraseña cambiada; sus sesiones se cerraron").then(() => setPw(""))}>
                Cambiar contraseña
              </button>
            </div>
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>
            /{b.slug} · creado {b.created_at.slice(0, 10)}{b.subscription_status !== "active" && ` · prueba hasta ${b.trial_ends_at.slice(0, 10)}`}
          </p>
        </>
      )}
    </div>
  );
}

export default function SuperAdmin() {
  const [key, setKey] = useState("");
  const [list, setList] = useState<Biz[] | null>(null);
  const [q, setQ] = useState("");
  const [audit, setAudit] = useState<{ id: number; email: string; action: string; detail: string; ip: string; created_at: string }[]>([]);
  const [toastNode, toast] = useToast();
  const hdr = (k: string) => ({ "x-admin-key": k });

  const load = useCallback(async (k: string) => {
    try {
      const r = await api<{ restaurants: Biz[] }>("/api/superadmin/restaurants", { headers: hdr(k) });
      setList(r.restaurants);
      try { setAudit((await api<{ events: typeof audit }>("/api/superadmin/audit", { headers: hdr(k) })).events); } catch { /* sin auditoría */ }
      sessionStorage.setItem("sa-key", k);
    } catch (e: any) {
      sessionStorage.removeItem("sa-key");
      setList(null);
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => {
    const k = sessionStorage.getItem("sa-key");
    if (k) { setKey(k); load(k); }
  }, [load]);

  async function call(path: string, body: object, ok: string) {
    try {
      await api("/api/superadmin/" + path, { method: "POST", body, headers: hdr(key) });
      toast(ok);
      await load(key);
    } catch (e: any) {
      toast(e.message, true);
    }
  }

  const shown = (list || []).filter((b) => (b.name + b.email + b.slug).toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <div className="sa">
      <div className="row spread wrap">
        <h1>Superusuario · MesaYa</h1>
        {list && <button className="btn ghost sm" onClick={() => { sessionStorage.removeItem("sa-key"); setList(null); setKey(""); }}>Salir</button>}
      </div>
      {!list ? (
        <form className="card" style={{ maxWidth: 420 }} onSubmit={(e) => { e.preventDefault(); load(key); }}>
          <label>Clave de administrador</label>
          <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
          <button className="btn block" style={{ marginTop: "1rem" }} disabled={!key}>Entrar</button>
        </form>
      ) : (
        <>
          <p className="muted">{list.length} negocios · {list.filter((b) => b.subscription_status === "active").length} con licencia activa</p>
          <input placeholder="Buscar por nombre, correo o enlace…" value={q} onChange={(e) => setQ(e.target.value)} />
          <details className="audit card">
            <summary>Últimos cambios con la clave de administrador ({audit.length})</summary>
            <table><tbody>
              {audit.map((e) => <tr key={e.id}><td>{e.created_at}</td><td>{e.email}</td><td><b>{e.action}</b> {e.detail}</td><td className="muted">{e.ip}</td></tr>)}
              {!audit.length && <tr><td className="muted">Aún no hay cambios registrados.</td></tr>}
            </tbody></table>
          </details>
          {shown.map((b) => <Row key={b.id} b={b} call={call} />)}
          {!shown.length && <p className="muted">Sin resultados.</p>}
        </>
      )}
      {toastNode}
    </div>
  );
}
