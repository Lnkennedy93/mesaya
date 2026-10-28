"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Any, useAdmin } from "./ctx";

// Se vuelve a montar (y a leer ME) después de guardar, igual que la versión actual recarga la pestaña.
export default function FiscalTab() {
  const [ver, setVer] = useState(0);
  return <FiscalForm key={ver} reload={() => setVer((v) => v + 1)} />;
}

function nitDv(nit: string) {
  const d = nit.replace(/\D/g, "");
  if (!d) return "—";
  const W = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71];
  let t = 0;
  [...d].reverse().forEach((c, i) => { t += +c * W[i]; });
  const x = t % 11;
  return String(x < 2 ? x : 11 - x);
}

function FiscalForm({ reload }: { reload: () => void }) {
  const { ME, setME, money, toast } = useAdmin();
  const r = ME.restaurant, I = ME.integrations, tt: Record<string, Any> = ME.catalog.tax_types;
  const [invoices, setInvoices] = useState<Any[] | null>(null);
  const [ranges, setRanges] = useState<Any[] | null>(null);
  const [f, setF] = useState({
    legal: r.legal_name || "", nit: r.nit || "", tax: r.tax_type as string, pct: String(r.tax_pct ?? 0), addr: r.fiscal_address || "", phone: r.fiscal_phone || "",
    mun: r.fiscal_municipality_id ? String(r.fiscal_municipality_id) : "", incl: r.tax_included ? "1" : "0",
    prov: r.inv_provider as string, env: r.inv_env as string, cid: "", cs: "", user: "", pw: "", range: r.inv_range_id ? String(r.inv_range_id) : "",
    online: !!r.online_payments, penv: r.wompi_env as string, pub: "", prv: "", ev: "", int: "", nequi: !!r.nequi_enabled,
    btype: r.breb_key_type as string, bkey: r.breb_key || "", bholder: r.breb_holder || "", bon: !!r.breb_enabled,
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const chk = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.checked });
  const ph = (ok: boolean) => (ok ? "•••••• (guardado; deja vacío para conservar)" : undefined);

  useEffect(() => {
    api("/api/invoices").then((x) => setInvoices(x.invoices)).catch((e) => toast(e.message, true));
  }, [toast]);

  async function testConnection() {
    try {
      const { ranges } = await api("/api/invoicing/test", { method: "POST" });
      setRanges(ranges);
      toast("Conexión exitosa ✓");
    } catch (e: Any) { toast(e.message, true); }
  }

  async function retry(id: number) {
    try {
      const r2 = await api(`/api/invoices/${id}/retry`, { method: "POST" });
      toast(r2.invoice.status === "issued" ? "Factura emitida ✓" : "Sigue con error: " + r2.invoice.error, r2.invoice.status !== "issued");
      reload();
    } catch (e: Any) { toast(e.message, true); }
  }

  async function saveAll() {
    try {
      await api("/api/integrations/invoicing", { method: "PUT", body: { client_id: f.cid, client_secret: f.cs, username: f.user, password: f.pw } });
      await api("/api/integrations/payments", { method: "PUT", body: { wompi_public: f.pub, wompi_private: f.prv, wompi_events: f.ev, wompi_integrity: f.int } });
      const me = await api("/api/settings", {
        method: "PUT",
        body: {
          legal_name: f.legal, nit: f.nit, tax_type: f.tax, tax_pct: +f.pct, tax_included: +f.incl, fiscal_address: f.addr, fiscal_phone: f.phone, fiscal_municipality_id: +f.mun || 0,
          inv_provider: f.prov, inv_env: f.env, inv_range_id: +f.range || 0,
          online_payments: f.online ? 1 : 0, wompi_env: f.penv, nequi_enabled: f.nequi ? 1 : 0,
          breb_enabled: f.bon ? 1 : 0, breb_key_type: f.btype, breb_key: f.bkey, breb_holder: f.bholder,
        },
      });
      setME(me);
      toast("Guardado ✓");
      reload();
    } catch (e: Any) { toast(e.message, true); }
  }

  const stBadge = (i: Any) => (i.status === "issued" ? <span className="pill ok">Emitida</span> : i.status === "error" ? <span className="pill bad">Error</span> : <span className="pill warn">Pendiente</span>);

  return (
    <>
      <h1>Facturación y pagos · Colombia</h1>
      <p className="muted">Configura una sola vez: tus datos fiscales, tu proveedor de factura electrónica DIAN y cómo cobras (Nequi / Bre-B).</p>

      <div className="card">
        <h3>1 · Datos fiscales</h3>
        <div className="grid2">
          <div><label>Razón social</label><input value={f.legal} onChange={set("legal")} /></div>
          <div><label>NIT (sin dígito de verificación)</label><input value={f.nit} inputMode="numeric" onChange={set("nit")} /><div className="muted small">DV calculado: <b>{nitDv(f.nit)}</b></div></div>
          <div><label>Impuesto de tu negocio</label><select value={f.tax} onChange={set("tax")}>{Object.entries(tt).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></div>
          <div><label>Tarifa (%)</label><input type="number" step="0.1" min={0} max={30} value={f.pct} onChange={set("pct")} /></div>
          <div><label>Dirección del establecimiento</label><input value={f.addr} onChange={set("addr")} /></div>
          <div><label>Teléfono</label><input value={f.phone} onChange={set("phone")} /></div>
          <div><label>ID de municipio (en Factus)</label><input type="number" value={f.mun} placeholder="ej. el de tu ciudad en Factus" onChange={set("mun")} /></div>
          <div><label>Los precios de tu carta…</label><select value={f.incl} onChange={set("incl")}><option value="1">ya incluyen el impuesto</option><option value="0">NO lo incluyen (se suma)</option></select></div>
        </div>
        <p className="muted small">Los restaurantes normalmente cobran <b>INC 8 %</b>, no IVA. La propina voluntaria se muestra aparte y <b>no</b> entra en la factura. Confirma tu régimen con tu contador.</p>
      </div>

      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>2 · Facturación electrónica DIAN</h3>
        <p className="muted small" style={{ marginTop: 0 }}>
          MesaYa no transmite a la DIAN directamente (eso requiere habilitación, firma digital y XML UBL). Se conecta a tu <b>proveedor tecnológico</b>: crea cuenta en{" "}
          <a href="https://factus.com.co" target="_blank" rel="noopener">Factus</a>, habilita tu resolución de numeración y pega aquí las credenciales.
        </p>
        <div className="grid2">
          <div>
            <label>Proveedor</label>
            <select value={f.prov} onChange={set("prov")}>
              <option value="none">Desactivada</option><option value="factus">Factus</option>
              {ME.demo_mode && <option value="mock">Demo (facturas de mentira)</option>}
            </select>
          </div>
          <div><label>Ambiente</label><select value={f.env} onChange={set("env")}><option value="sandbox">Pruebas (sandbox)</option><option value="production">Producción</option></select></div>
          <div><label>Client ID</label><input autoComplete="off" value={f.cid} placeholder={ph(I.inv_configured)} onChange={set("cid")} /></div>
          <div><label>Client secret</label><input type="password" autoComplete="new-password" value={f.cs} placeholder={ph(I.inv_configured)} onChange={set("cs")} /></div>
          <div><label>Usuario (correo)</label><input autoComplete="off" value={f.user} placeholder={ph(I.inv_configured)} onChange={set("user")} /></div>
          <div><label>Contraseña</label><input type="password" autoComplete="new-password" value={f.pw} placeholder={ph(I.inv_configured)} onChange={set("pw")} /></div>
          <div><label>ID del rango de numeración</label><input type="number" value={f.range} placeholder="usa «Probar conexión» para verlos" onChange={set("range")} /></div>
        </div>
        <div className="row wrap" style={{ marginTop: ".8rem" }}><button className="btn ghost sm" onClick={testConnection}>Probar conexión</button><span className="muted small">Guarda primero los cambios.</span></div>
        {ranges && (
          <table style={{ marginTop: ".6rem" }}>
            <tbody>
              <tr><th>ID</th><th>Prefijo</th><th>Documento</th><th>Rango</th><th></th></tr>
              {ranges.map((x) => (
                <tr key={x.id}><td>{x.id}</td><td>{x.prefix}</td><td>{x.document}</td><td>{x.from}–{x.to} (actual {x.current})</td><td><button className="btn sm ghost" onClick={() => setF({ ...f, range: String(x.id) })}>Usar</button></td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>3 · Cobros desde el celular</h3>
        <label className="chk"><input type="checkbox" checked={f.online} onChange={chk("online")} /> Permitir pago desde el celular de la mesa</label>
        <h4 style={{ margin: "1rem 0 .2rem" }}>Nequi (por Wompi) — confirmación automática</h4>
        <p className="muted small" style={{ margin: "0 0 .4rem" }}>
          El cliente escribe su celular y recibe la notificación en Nequi. Necesitas una cuenta de comercio en <a href="https://wompi.com" target="_blank" rel="noopener">Wompi</a> con Nequi habilitado. En Wompi → Desarrolladores configura la <b>URL de eventos</b>:
        </p>
        <div className="row"><input readOnly value={I.wompi_webhook_url} /><button className="btn sm ghost" onClick={() => { navigator.clipboard.writeText(I.wompi_webhook_url); toast("URL copiada"); }}>Copiar</button></div>
        <div className="grid2">
          <div><label>Ambiente</label><select value={f.penv} onChange={set("penv")}><option value="sandbox">Pruebas</option><option value="production">Producción</option></select></div>
          <div><label>Llave pública</label><input autoComplete="off" value={f.pub} placeholder={ph(I.wompi_configured)} onChange={set("pub")} /></div>
          <div><label>Llave privada</label><input type="password" autoComplete="new-password" value={f.prv} placeholder={ph(I.wompi_configured)} onChange={set("prv")} /></div>
          <div><label>Secreto de eventos</label><input type="password" autoComplete="new-password" value={f.ev} placeholder={ph(I.wompi_events_set)} onChange={set("ev")} /></div>
          <div><label>Secreto de integridad</label><input type="password" autoComplete="new-password" value={f.int} placeholder={ph(I.wompi_configured)} onChange={set("int")} /></div>
        </div>
        <label className="chk"><input type="checkbox" checked={f.nequi} onChange={chk("nequi")} /> Ofrecer «Pagar con Nequi»</label>
        <h4 style={{ margin: "1rem 0 .2rem" }}>Bre-B — confirmación asistida</h4>
        <p className="muted small" style={{ margin: "0 0 .4rem" }}>
          El cliente paga a tu llave Bre-B desde su banco o Nequi y toca «Ya pagué»; tu equipo ve el aviso en la pantalla de cocina/sala, verifica que llegó el dinero y confirma. (Aún no hay API pública de cobro Bre-B para comercios.)
        </p>
        <div className="grid2">
          <div><label>Tipo de llave</label><select value={f.btype} onChange={set("btype")}>{["celular", "cedula", "nit", "correo", "alfanumerica"].map((t) => <option key={t}>{t}</option>)}</select></div>
          <div><label>Tu llave Bre-B</label><input value={f.bkey} onChange={set("bkey")} /></div>
          <div><label>Nombre del titular (el cliente lo verá)</label><input value={f.bholder} onChange={set("bholder")} /></div>
        </div>
        <label className="chk"><input type="checkbox" checked={f.bon} onChange={chk("bon")} /> Ofrecer «Pagar con Bre-B»</label>
      </div>
      <p><button className="btn" onClick={saveAll}>Guardar todo</button></p>

      <div className="card">
        <h3>Facturas electrónicas recientes</h3>
        <table>
          <tbody>
            {(invoices || []).map((i) => (
              <tr key={i.id}>
                <td>{stBadge(i)}</td>
                <td><b>{i.number || "—"}</b><div className="muted small">Mesa {i.table_label} · {i.created_at} UTC</div></td>
                <td>{i.customer.name || ""}<div className="muted small">{i.customer.doc_number || ""}</div></td>
                <td>{money(i.total)}</td>
                <td>
                  {i.public_url && <a className="btn sm ghost" href={i.public_url} target="_blank" rel="noopener">Ver</a>}
                  {i.status !== "issued" && <button className="btn sm" onClick={() => retry(i.id)}>Reintentar</button>}
                  {i.error && <div className="small" style={{ color: "var(--bad)", maxWidth: 260 }}>{i.error}</div>}
                </td>
              </tr>
            ))}
            {invoices && !invoices.length && <tr><td className="muted">Aún no hay facturas. Se emite una por cada pago confirmado.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
