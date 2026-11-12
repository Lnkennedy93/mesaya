"use client";
// Para llevar: un solo QR para negocios sin mesas (postres, comida rápida...). Máximo N pedidos en curso a la vez.
import { useCallback, useEffect, useState } from "react";
import { api, poll, shrinkImage } from "@/lib/api";
import { Any, useAdmin } from "./ctx";
import Icon from "@/components/Icon";

export default function TakeawayTab() {
  const { ME, setME, toast } = useAdmin();
  const r = ME.restaurant;
  const max: number = ME.takeaway_max;
  const [active, setActive] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const o = (await api("/api/orders")).orders as Any[];
      setActive(o.filter((x) => String(x.table_label).startsWith("PL-")).length);
    } catch { /* se reintenta solo */ }
  }, []);
  useEffect(() => { load(); return poll(load, 8000); }, [load]);

  async function save(enabled: boolean, rotate = false) {
    try { setME(await api("/api/takeaway", { method: "POST", body: { enabled, rotate } })); } catch (e: Any) { toast(e.message, true); }
  }

  async function setQrPay(on: boolean) {
    try { setME(await api("/api/settings", { method: "PUT", body: { takeaway_qr: on ? 1 : 0 } })); } catch (e: Any) { toast(e.message, true); }
  }

  async function uploadQr(file: File | undefined) {
    if (!file) return;
    const fd = new FormData();
    try { fd.append("file", await shrinkImage(file, 1200)); const res = await api("/api/pay-qr", { method: "POST", body: fd }); setME({ ...ME, restaurant: { ...ME.restaurant, pay_qr: res.pay_qr } }); toast("QR de pago guardado"); } catch (e: Any) { toast(e.message, true); }
  }

  return (
    <>
      <h1><Icon n="takeaway" /> Para llevar</h1>
      <p className="muted">
        Para negocios sin mesas (postres, comida rápida…): el cliente escanea <b>un solo QR</b>, ve la carta y hace su pedido con su nombre.
        Se aceptan máximo <b>{max} pedidos a la vez</b>: mientras haya {max} en curso no entra ninguno más, y cuando entregas uno
        (botón «Entregado» en Cocina) entra el siguiente.
      </p>
      <div className="card">
        <div className="row spread">
          <div><b>Recibir pedidos para llevar</b><div className="muted small">{r.takeaway ? "Activado: los clientes ya pueden pedir con el QR." : "Apagado: el QR no funciona."}</div></div>
          <label className="switch"><input type="checkbox" checked={!!r.takeaway} onChange={(e) => save(e.target.checked)} /><span /></label>
        </div>
      </div>
      <div className="card" style={{ marginTop: ".8rem" }}>
        <div className="row spread">
          <div>
            <b>Pago ágil con QR (Bre-B o Nequi)</b>
            <div className="muted small">{r.takeaway_qr ? "Activado: al pedir para llevar, el cliente puede elegir «QR» y pagar escaneando el tuyo." : "Apagado: el cliente solo avisa si pagará en efectivo o con datáfono al recoger."}</div>
          </div>
          <label className="switch"><input type="checkbox" aria-label="Pago ágil con QR" checked={!!r.takeaway_qr} disabled={!r.pay_qr && !r.takeaway_qr} onChange={(e) => setQrPay(e.target.checked)} /><span /></label>
        </div>
        <div className="row wrap" style={{ alignItems: "center", marginTop: ".7rem" }}>
          {r.pay_qr && <img src={r.pay_qr} alt="QR de pago" style={{ width: 96, height: 96, objectFit: "contain", background: "#fff", borderRadius: 10, padding: 5 }} />}
          <div className="grow">
            <label style={{ marginTop: 0 }}>{r.pay_qr ? "Cambiar el QR de cobro" : "Sube el QR de cobro de tu negocio (Bre-B o Nequi)"}</label>
            <input type="file" accept="image/*" aria-label="Imagen del QR de pago" onChange={(e) => { uploadQr(e.target.files?.[0]); e.target.value = ""; }} />
            <div className="muted small" style={{ marginTop: ".3rem" }}>Es el mismo QR de Ajustes → «Pago por QR». Tu equipo ve el aviso en Cocina y Sala, revisa el comprobante y cobra con «Cobrado por QR».</div>
          </div>
        </div>
      </div>
      {r.takeaway ? (
        <div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}>
          <b style={{ fontSize: "1.2rem" }}>{active === null ? "…" : active} de {max} pedidos en curso</b>
          {active !== null && active >= max && <div className="pill warn" style={{ marginLeft: ".5rem" }}>Cupo lleno</div>}
          <div style={{ margin: "1rem auto", maxWidth: 220 }}><img src="/api/qr/takeaway.svg" alt="QR para llevar" style={{ width: "100%" }} /></div>
          <div className="muted small" style={{ wordBreak: "break-all" }}>{ME.takeaway_url}</div>
          <div className="row" style={{ justifyContent: "center", marginTop: ".8rem" }}>
            <a className="btn sm" href="/print/qr?solo=llevar" target="_blank"><Icon n="print" /> Imprimir QR</a>
            <button className="btn sm ghost" title="Genera un QR nuevo e invalida el impreso" onClick={() => { if (confirm("El QR impreso actual dejará de funcionar. ¿Renovar?")) save(true, true); }}>Renovar QR</button>
          </div>
        </div>
      ) : null}
    </>
  );
}
