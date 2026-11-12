"use client";
import { useState } from "react";
import { api, setBrand, shrinkImage } from "@/lib/api";
import { Any, CURRENCIES, useAdmin } from "./ctx";
import Icon from "@/components/Icon";

export default function SettingsTab() {
  const { ME, setME, toast } = useAdmin();
  const r = ME.restaurant;
  const [f, setF] = useState({
    name: r.name as string, tagline: (r.tagline || "") as string, color: r.brand_color as string, color2: (r.brand_color2 || "") as string, color3: (r.brand_color3 || "") as string, tip: String(r.tip_pct),
    cur: r.currency as string, tz: String(r.tz_offset), google: (r.google_review_url || "") as string, accepting: !!r.accepting_orders, pin: (r.staff_pin || "") as string,
  });
  const [pwCur, setPwCur] = useState("");
  const [pwNew, setPwNew] = useState("");
  const DEF2 = "#dbe7f3", DEF3 = "#3ddc61"; // los del producto: se muestran mientras el restaurante no elija otros
  // vista previa: el color se ve en el panel apenas se escoge (se guarda con «Guardar cambios»)
  const pick = (k: "color" | "color2" | "color3", v: string) => {
    const n = { ...f, [k]: v };
    setF(n);
    setBrand(n.color, n.color2, n.color3);
  };
  const resetColors = () => { const n = { ...f, color2: "", color3: "" }; setF(n); setBrand(n.color, "", ""); };
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  async function save() {
    try {
      const me = await api("/api/settings", { method: "PUT", body: { name: f.name, tagline: f.tagline, brand_color: f.color, brand_color2: f.color2, brand_color3: f.color3, tip_pct: +f.tip, currency: f.cur, tz_offset: +f.tz, google_review_url: f.google, accepting_orders: f.accepting ? 1 : 0, staff_pin: f.pin } });
      setME(me);
      toast("Guardado");
    } catch (e: Any) { toast(e.message, true); }
  }

  async function changePassword() {
    try {
      await api("/api/password", { method: "POST", body: { current: pwCur, password: pwNew } });
      setPwCur(""); setPwNew("");
      toast("Contraseña actualizada. Las demás sesiones se cerraron.");
    } catch (e: Any) { toast(e.message, true); }
  }

  async function cancelSub() {
    if (!confirm(r.paid_until ? `Tu plan seguirá activo hasta el ${String(r.paid_until).slice(0, 10)} y luego pasarás al plan Gratis. No se borra nada. ¿Cancelar la suscripción?`
      : "Pasarás al plan Gratis ahora mismo (3 mesas con pedidos). No se borra nada. ¿Cancelar la suscripción?")) return;
    try { setME(await api("/api/subscription/cancel", { method: "POST" })); toast("Suscripción cancelada"); } catch (e: Any) { toast(e.message, true); }
  }

  async function deleteAccount() {
    const pw = prompt("Vas a BORRAR tu restaurante y todos sus datos (carta, pedidos, opiniones, fotos). No se puede deshacer.\n\nEscribe tu contraseña para continuar:");
    if (!pw) return;
    const conf = prompt(`Para confirmar escribe el código de tu restaurante: ${ME.restaurant.slug}`);
    if (!conf) return;
    try { await api("/api/account/delete", { method: "POST", body: { password: pw, confirm: conf } }); location.href = "/"; } catch (e: Any) { toast(e.message, true); }
  }

  async function uploadLogo(file: File | undefined) {
    if (!file) return;
    const fd = new FormData();
    try { fd.append("file", await shrinkImage(file)); const res = await api("/api/logo", { method: "POST", body: fd }); setME({ ...ME, restaurant: { ...ME.restaurant, logo: res.logo } }); toast("Logo actualizado"); } catch (e: Any) { toast(e.message, true); }
  }

  async function uploadPayQr(file: File | undefined) {
    if (!file) return;
    const fd = new FormData();
    try { fd.append("file", await shrinkImage(file, 1200)); const res = await api("/api/pay-qr", { method: "POST", body: fd }); setME({ ...ME, restaurant: { ...ME.restaurant, pay_qr: res.pay_qr } }); toast("QR de pago guardado"); } catch (e: Any) { toast(e.message, true); }
  }

  async function removePayQr() {
    try { await api("/api/pay-qr", { method: "DELETE" }); setME({ ...ME, restaurant: { ...ME.restaurant, pay_qr: "" } }); toast("QR de pago quitado"); } catch (e: Any) { toast(e.message, true); }
  }

  return (
    <>
      <h1>Ajustes</h1>
      <div className="card">
        <h3>Tu restaurante</h3>
        <div className="grid2">
          <div><label>Nombre</label><input value={f.name} onChange={set("name")} /></div>
          <div><label>Eslogan</label><input value={f.tagline} onChange={set("tagline")} /></div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label>Colores de tu marca</label>
            <div className="colors">
              <div><b>Principal</b><span className="muted small">Botones, pestaña activa y la cabecera de tu carta.</span><input type="color" aria-label="Color principal" value={f.color} onChange={(e) => pick("color", e.target.value)} /></div>
              <div><b>Secundario</b><span className="muted small">Fondos suaves: barra lateral, cabeceras y tarjetas.</span><input type="color" aria-label="Color secundario" value={f.color2 || DEF2} onChange={(e) => pick("color2", e.target.value)} /></div>
              <div><b>Acento</b><span className="muted small">Detalles: barras, puntos de estado y resaltes.</span><input type="color" aria-label="Color de acento" value={f.color3 || DEF3} onChange={(e) => pick("color3", e.target.value)} /></div>
            </div>
            <p className="muted small" style={{ margin: ".5rem 0 0" }}>Verás el cambio al instante; guárdalo con «Guardar cambios». <button type="button" className="linkbtn" onClick={resetColors}>Volver a los colores de MesaYa (secundario y acento)</button></p>
          </div>
          <div><label>Logo</label><input type="file" accept="image/*" onChange={(e) => uploadLogo(e.target.files?.[0])} /><p className="muted small" style={{ margin: ".3rem 0 0" }}>Aparece arriba a la izquierda del panel y en tu carta.</p></div>
          <div><label>Propina sugerida (%)</label><input type="number" min={0} max={10} value={f.tip} onChange={set("tip")} /></div>
          <div><label>Moneda</label><select value={f.cur} onChange={set("cur")}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></div>
          <div><label>Zona horaria (minutos vs UTC)</label><input type="number" value={f.tz} onChange={set("tz")} /></div>
          <div><label>Link reseñas de Google</label><input value={f.google} onChange={set("google")} placeholder="https://g.page/r/..." /></div>
        </div>
      </div>
      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>Operación</h3>
        <label className="chk"><input type="checkbox" checked={f.accepting} onChange={(e) => setF({ ...f, accepting: e.target.checked })} /> Recibir pedidos desde el QR (si lo apagas, el QR solo muestra la carta)</label>
        <label>PIN del equipo, de 6 a 8 dígitos (cocina y meseros) — entran en <b>/kitchen</b> con el código <b>{r.slug}</b>. Si lo cambias, el equipo debe volver a entrar.</label>
        <input value={f.pin} onChange={set("pin")} inputMode="numeric" maxLength={8} style={{ maxWidth: 160 }} />
      </div>
      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>Pago por QR (Bre-B o Nequi)</h3>
        <p className="muted small" style={{ margin: "0 0 .6rem" }}>Sube la imagen del QR de cobro de tu negocio (la que genera tu app Bre-B o Nequi). Cuando el cliente pida la cuenta y elija «QR», se la mostramos para que pague desde su celular. Tu equipo ve el aviso en cocina/sala, revisa el comprobante y cierra la mesa con «Cobrado por QR».</p>
        <div className="row wrap" style={{ alignItems: "center" }}>
          {r.pay_qr && <img src={r.pay_qr} alt="QR de pago" style={{ width: 120, height: 120, objectFit: "contain", background: "#fff", borderRadius: 12, padding: 6 }} />}
          <div className="grow">
            <input type="file" accept="image/*" aria-label="Imagen del QR de pago" onChange={(e) => { uploadPayQr(e.target.files?.[0]); e.target.value = ""; }} />
            {r.pay_qr && <p style={{ margin: ".4rem 0 0" }}><button type="button" className="btn ghost sm" onClick={removePayQr}>Quitar QR</button></p>}
          </div>
        </div>
      </div>
      <p><button className="btn" onClick={save}>Guardar cambios</button></p>
      <div className="card" style={{ marginBottom: ".8rem" }}>
        <h3>Seguridad de la cuenta</h3>
        <div className="grid2">
          <div><label>Contraseña actual</label><input type="password" autoComplete="current-password" value={pwCur} onChange={(e) => setPwCur(e.target.value)} /></div>
          <div><label>Nueva contraseña (mín. 8)</label><input type="password" autoComplete="new-password" value={pwNew} onChange={(e) => setPwNew(e.target.value)} /></div>
        </div>
        <p><button className="btn ghost sm" onClick={changePassword}>Cambiar contraseña</button></p>
      </div>
      <div className="card" style={{ marginBottom: ".8rem" }}>
        <h3>Plan</h3>
        <p>
          Plan <b>{ME.plan.name}</b> ·{" "}
          {r.subscription_status === "active" ? <span className="pill ok">Activo</span> : ME.active ? <span className="pill warn">Prueba · {ME.trial_days_left} días</span> : <span className="pill warn">Gratis · {ME.plan.tables} mesas</span>}
        </p>
      </div>
      {r.subscription_status === "active" && (
        <div className="card" style={{ marginTop: ".8rem" }}>
          <h3>Suscripción</h3>
          <p className="muted small" style={{ marginTop: 0 }}>
            {r.paid_until ? `Pagada hasta el ${String(r.paid_until).slice(0, 10)}. ` : "Sin fecha de vencimiento. "}
            {r.cancel_requested_at ? "Pediste cancelar: sigue activa hasta esa fecha y luego pasas al plan Gratis. No se borra nada."
              : "Si cancelas, tu plan sigue activo hasta que termine lo ya pagado y luego pasas al plan Gratis. No se borra nada."}
          </p>
          {!r.cancel_requested_at && <button className="btn ghost sm" onClick={cancelSub}>Cancelar mi suscripción</button>}
        </div>
      )}
      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>Tus datos</h3>
        <p className="muted small" style={{ marginTop: 0 }}>
          Consulta los <a href="/terminos" target="_blank">Términos</a> y la <a href="/privacidad" target="_blank">Política de datos</a>. Puedes llevarte tus pedidos o borrar todo (derecho de supresión).
        </p>
        <p><a className="btn ghost sm" href="/api/export/orders.csv"><Icon n="download" /> Exportar pedidos (CSV)</a> <button className="btn bad sm" onClick={deleteAccount}>Borrar mi cuenta y mis datos</button></p>
      </div>
    </>
  );
}
