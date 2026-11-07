"use client";
// Panel del dueño (portada de web/admin.html). Mismos endpoints /api/... y mismas pestañas.
import { useEffect, useMemo, useState } from "react";
import { api, makeMoney, setBrand } from "@/lib/api";
import Modal from "@/components/Modal";
import Powered from "@/components/Powered";
import { useToast } from "@/components/useToast";
import { AdminCtx, Any } from "./ctx";
import HomeTab from "./HomeTab";
import MenuTab from "./MenuTab";
import { TablesTab, ReviewsTab } from "./TablesTab";
import SettingsTab from "./SettingsTab";
import AssistantTab from "./AssistantTab";
import FiscalTab from "./FiscalTab";
import CustomersTab from "./CustomersTab";
import TakeawayTab from "./TakeawayTab";

export default function AdminApp({ welcome }: { welcome: boolean }) {
  const [ME, setMEState] = useState<Any>(null);
  const [tab, setTab] = useState(welcome ? "menu" : "home");
  const [termsOpen, setTermsOpen] = useState(false);
  const [toastNode, toast] = useToast();

  useEffect(() => {
    let dead = false;
    (async () => {
      let me: Any;
      try { me = await api("/api/me"); } catch { location.href = "/login"; return; }
      if (me.role !== "owner") { location.href = "/kitchen"; return; }
      if (dead) return;
      setBrand(me.restaurant.brand_color);
      setMEState(me);
      if (!me.terms_current) setTermsOpen(true);
    })();
    return () => { dead = true; };
  }, []);

  const ctx = useMemo(() => {
    if (!ME) return null;
    const factor = Math.pow(10, ME.restaurant.decimals);
    return {
      ME,
      setME: (m: Any) => { setBrand(m.restaurant.brand_color); setMEState(m); },
      money: makeMoney(ME.restaurant.decimals, ME.restaurant.currency),
      toMajor: (v: number) => v / factor,
      toMinor: (v: Any) => Math.round(parseFloat(v || 0) * factor),
      toast,
    };
  }, [ME, toast]);

  if (!ME || !ctx) return <div className="admin-root" />;

  const tabs: [string, string][] = [["home", "📊 Resumen"], ["menu", "🍽️ Carta"], ["tables", "🔳 Mesas y QR"], ["takeaway", "🥡 Para llevar"], ["reviews", "⭐ Opiniones"], ["customers", "🎁 Fidelización Clientes"], ["assistant", "🤖 Asistente"], ["settings", "⚙️ Ajustes"]];
  if (ME.features.payments || ME.features.invoicing) tabs.splice(3, 0, ["fiscal", "🧾 Facturas y pagos"]);
  // funciones que el superusuario dejó apagadas para este negocio: no se muestran (y el servidor las rechaza)
  const shownTabs = tabs.filter(([k]) => k === "fiscal" || ME.modules?.[k] !== false);
  const cur = shownTabs.some(([k]) => k === tab) ? tab : shownTabs[0]?.[0] ?? "";

  const mail = `mailto:ventas@mesaya.app?subject=Activar%20${encodeURIComponent(ME.restaurant.slug)}`;
  const banner =
    ME.restaurant.subscription_status === "active" ? null : !ME.active ? (
      <div className="banner bad"><b>Tu prueba terminó: estás en el plan Gratis.</b> Solo las primeras {ME.plan.tables} mesas reciben pedidos desde el QR. <a className="btn sm" href={mail}>Activar mi plan</a></div>
    ) : (
      <div className="banner"><span>🎁 Prueba gratis: te quedan <b>{ME.trial_days_left} días</b></span><a className="btn sm" href={mail}>Elegir plan</a></div>
    );

  const Tab = ({ home: HomeTab, menu: MenuTab, tables: TablesTab, fiscal: FiscalTab, reviews: ReviewsTab, customers: CustomersTab, takeaway: TakeawayTab, assistant: AssistantTab, settings: SettingsTab } as Record<string, React.ComponentType>)[cur];

  return (
    <AdminCtx.Provider value={ctx}>
      <div className="admin-root">
        <div className="layout">
          <nav>
            <div className="logo">Mesa<b>Ya</b></div>
            <div>
              {shownTabs.map(([k, l]) => (
                <button key={k} className={k === cur ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
              ))}
            </div>
            <div className="sp"></div>
            <a className="btn sm ghost" href="/kitchen" target="_blank">Cocina y sala ↗</a>
            <button style={{ marginTop: ".3rem" }} onClick={async () => { await api("/api/logout", { method: "POST" }); location.href = "/login"; }}>Salir</button>
            <Powered />
          </nav>
          <main>
            {banner}
            {Tab ? <Tab key={cur} /> : <p className="muted">Tu cuenta no tiene funciones activas por ahora. Escríbenos y las activamos.</p>}
          </main>
        </div>

        <Modal open={termsOpen} locked onClose={() => {}}>
          <h2>Actualizamos nuestros términos</h2>
          <p>
            Para seguir usando MesaYa necesitamos que revises y aceptes la versión vigente de los <a href="/terminos" target="_blank" rel="noopener">Términos y condiciones</a> y de la{" "}
            <a href="/privacidad" target="_blank" rel="noopener">Política de tratamiento de datos</a>.
          </p>
          <button className="btn block" onClick={async () => { await api("/api/accept-terms", { method: "POST" }); setTermsOpen(false); }}>Los leí y los acepto</button>
        </Modal>
        {toastNode}
      </div>
    </AdminCtx.Provider>
  );
}
