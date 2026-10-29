"use client";
import { useState } from "react";
import { api, shrinkImage } from "@/lib/api";
import { Any, CURRENCIES, useAdmin } from "./ctx";

export default function SettingsTab() {
  const { ME, setME, toast } = useAdmin();
  const r = ME.restaurant;
  const [f, setF] = useState({
    name: r.name as string, tagline: (r.tagline || "") as string, color: r.brand_color as string, tip: String(r.tip_pct),
    cur: r.currency as string, tz: String(r.tz_offset), google: (r.google_review_url || "") as string, accepting: !!r.accepting_orders, pin: (r.staff_pin || "") as string,
  });
  const [pwCur, setPwCur] = useState("");
  const [pwNew, setPwNew] = useState("");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  async function save() {
    try {
      const me = await api("/api/settings", { method: "PUT", body: { name: f.name, tagline: f.tagline, brand_color: f.color, tip_pct: +f.tip, currency: f.cur, tz_offset: +f.tz, google_review_url: f.google, accepting_orders: f.accepting ? 1 : 0, staff_pin: f.pin } });
      setME(me);
      toast("Guardado ✓");
    } catch (e: Any) { toast(e.message, true); }
  }

  async function changePassword() {
    try {
      await api("/api/password", { method: "POST", body: { current: pwCur, password: pwNew } });
      setPwCur(""); setPwNew("");
      toast("Contraseña actualizada. Las demás sesiones se cerraron.");
    } catch (e: Any) { toast(e.message, true); }
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
    try { fd.append("file", await shrinkImage(file)); await api("/api/logo", { method: "POST", body: fd }); toast("Logo actualizado"); } catch (e: Any) { toast(e.message, true); }
  }

  return (
    <>
      <h1>Ajustes</h1>
      <div className="card">
        <h3>Tu restaurante</h3>
        <div className="grid2">
          <div><label>Nombre</label><input value={f.name} onChange={set("name")} /></div>
          <div><label>Eslogan</label><input value={f.tagline} onChange={set("tagline")} /></div>
          <div><label>Color de marca</label><input type="color" value={f.color} onChange={set("color")} style={{ height: 44, padding: ".2em" }} /></div>
          <div><label>Logo</label><input type="file" accept="image/*" onChange={(e) => uploadLogo(e.target.files?.[0])} /></div>
          <div><label>Propina sugerida (%)</label><input type="number" min={0} max={30} value={f.tip} onChange={set("tip")} /></div>
          <div><label>Moneda</label><select value={f.cur} onChange={set("cur")}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></div>
          <div><label>Zona horaria (minutos vs UTC)</label><input type="number" value={f.tz} onChange={set("tz")} /></div>
          <div><label>Link reseñas de Google</label><input value={f.google} onChange={set("google")} placeholder="https://g.page/r/..." /></div>
        </div>
      </div>
      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>Operación</h3>
        <label className="chk"><input type="checkbox" checked={f.accepting} onChange={(e) => setF({ ...f, accepting: e.target.checked })} /> Recibir pedidos desde el QR (si lo apagas, el QR solo muestra la carta)</label>
        <label>PIN del equipo (cocina y meseros) — entran en <b>/kitchen</b> con el código <b>{r.slug}</b></label>
        <input value={f.pin} onChange={set("pin")} inputMode="numeric" maxLength={8} style={{ maxWidth: 160 }} />
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
          {r.subscription_status === "active" ? <span className="pill ok">Activo</span> : ME.active ? <span className="pill warn">Prueba · {ME.trial_days_left} días</span> : <span className="pill bad">Vencido</span>}
        </p>
      </div>
      <div className="card" style={{ marginTop: ".8rem" }}>
        <h3>Tus datos</h3>
        <p className="muted small" style={{ marginTop: 0 }}>
          Consulta los <a href="/terminos" target="_blank">Términos</a> y la <a href="/privacidad" target="_blank">Política de datos</a>. Puedes llevarte tus pedidos o borrar todo (derecho de supresión).
        </p>
        <p><a className="btn ghost sm" href="/api/export/orders.csv">⬇ Exportar pedidos (CSV)</a> <button className="btn bad sm" onClick={deleteAccount}>Borrar mi cuenta y mis datos</button></p>
      </div>
    </>
  );
}
