"use client";
// Tarjeta de sellos del cliente: se abre con su QR o su tarjeta NFC. Si quien la abre es del equipo del restaurante (sesión abierta), ve también los botones para sumar sello o canjear el premio.
import { useCallback, useEffect, useState } from "react";
import { api, setBrand } from "@/lib/api";
import Icon from "@/components/Icon";

type Card = { name: string; stamps: number; goal: number; filled: number; rewards: number; ready: boolean; reward: string; restaurant: { name: string; logo: string; brand_color: string; brand_color2: string; brand_color3: string } };

export default function LoyaltyCard({ slug, c, nuevo = false }: { slug: string; c: string; nuevo?: boolean }) {
  const [card, setCard] = useState<Card | null>(null);
  const [err, setErr] = useState("");
  const [staff, setStaff] = useState(false);
  const [msg, setMsg] = useState<{ t: string; bad?: boolean } | null>(null);
  const [install, setInstall] = useState<any>(null); // evento de Chrome para instalar el acceso directo
  const [howTo, setHowTo] = useState(false); // instrucciones cuando el navegador no deja instalarlo con un toque (iPhone, por ejemplo)
  const [installed, setInstalled] = useState(false);

  const load = useCallback(async () => {
    try {
      const x = await api<Card>(`/api/public/${slug}/loyalty/card?c=${encodeURIComponent(c)}`);
      setCard(x);
      try { localStorage.setItem("mesaya_card_" + slug, c); } catch { /* sin almacenamiento */ } // este celular recuerda la tarjeta: la próxima vez que escanee el QR del local llega directo
      if (x.restaurant.brand_color) setBrand(x.restaurant.brand_color, x.restaurant.brand_color2, x.restaurant.brand_color3);
    } catch (e: any) { setErr(e.message); }
  }, [slug, c]);

  useEffect(() => {
    load();
    api("/api/me").then(() => setStaff(true)).catch(() => setStaff(false)); // con sesión del equipo aparecen los botones
  }, [load]);

  useEffect(() => {
    const standalone = window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone;
    if (standalone) { setInstalled(true); return; } // ya abierta desde el ícono: no se ofrece de nuevo
    const onPrompt = (e: Event) => { e.preventDefault(); setInstall(e); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", () => setInstalled(true));
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  useEffect(() => { // el acceso directo lleva el nombre y el logo del restaurante y abre ESTA tarjeta
    if (!card) return;
    const q = `c=${encodeURIComponent(c)}`;
    const add = (rel: string, href: string) => { const l = document.createElement("link"); l.rel = rel; l.href = href; document.head.appendChild(l); return l; };
    const links = [add("manifest", `/api/public/${slug}/loyalty/manifest.webmanifest?${q}`), add("apple-touch-icon", `/api/public/${slug}/loyalty/icon.png?${q}&s=192`)];
    document.title = `${card.restaurant.name} · Mi tarjeta`;
    return () => links.forEach((l) => l.remove());
  }, [card?.restaurant.name, slug, c]); // eslint-disable-line react-hooks/exhaustive-deps

  async function shortcut() {
    if (install) { install.prompt(); setInstall(null); return; }
    setHowTo(true);
  }

  async function act(kind: "stamp" | "redeem") {
    try {
      const r = await api<Card>("/api/loyalty/" + kind, { method: "POST", body: { card: c } });
      setMsg({ t: kind === "stamp" ? `Sello sumado: ${r.filled} de ${r.goal}` : "Premio canjeado. La tarjeta vuelve a empezar." });
      await load();
    } catch (e: any) { setMsg({ t: e.message, bad: true }); }
  }

  if (err) return <div className="menu-root"><div className="notice" role="alert">{err}</div></div>;
  if (!card) return <div className="menu-root" aria-busy="true"><p className="muted" style={{ textAlign: "center", marginTop: "3rem" }}>…</p></div>;
  const left = card.goal - card.filled;

  return (
    <div className="menu-root">
      <div className="hero">
        <div className="thumb logo">{card.restaurant.logo ? <img src={card.restaurant.logo} alt="" /> : card.restaurant.name.slice(0, 1).toUpperCase()}</div>
        <div className="grow"><h1>{card.restaurant.name}</h1><div className="muted small">Tarjeta de sellos</div></div>
      </div>
      <main>
        {nuevo && <div className="notice" role="status" style={{ marginTop: "1rem" }}><b>¡Listo, ya estás registrado!</b> Esta es tu tarjeta de sellos: guárdala en tu celular con el botón de abajo.</div>}
        <div className="card" style={{ marginTop: "1rem", textAlign: "center" }}>
          <h2 style={{ marginTop: 0 }}>Hola, {card.name}</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: ".5rem", justifyContent: "center", margin: "1rem 0" }} role="img" aria-label={`${card.filled} de ${card.goal} sellos`}>
            {Array.from({ length: card.goal }, (_, i) => (
              <span key={i} style={{ width: 44, height: 44, borderRadius: "50%", display: "grid", placeItems: "center", border: "2px solid var(--brand)", background: i < card.filled ? "var(--brand)" : "transparent", color: "var(--brand-ink)" }}>
                {i < card.filled ? <Icon n="check" /> : null}
              </span>
            ))}
          </div>
          <b className="big">{card.filled} de {card.goal} sellos</b>
          {card.ready ? (
            <p style={{ fontWeight: 800, marginBottom: 0 }}><Icon n="gift" /> ¡Tu tarjeta está completa!{card.reward ? ` Premio: ${card.reward}.` : ""}{card.rewards > 1 ? ` Tienes ${card.rewards} premios.` : ""} Pídelo en tu próxima visita.</p>
          ) : (
            <p className="muted" style={{ marginBottom: 0 }}>Te {left === 1 ? "falta 1 sello" : `faltan ${left} sellos`}{card.reward ? ` para: ${card.reward}` : " para tu premio"}.</p>
          )}
        </div>
        {!installed && !staff && (
          <div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}>
            <button className="btn block" onClick={shortcut}><Icon n="phone" /> Crear acceso directo</button>
            {howTo && (
              <p className="muted small" style={{ marginBottom: 0 }}>
                {/iPhone|iPad|iPod/.test(navigator.userAgent)
                  ? "En Safari toca el botón Compartir (el cuadro con la flecha hacia arriba) y elige «Agregar a pantalla de inicio»."
                  : "Abre el menú del navegador (los tres puntos) y elige «Agregar a pantalla de inicio» o «Instalar aplicación»."}
              </p>
            )}
          </div>
        )}
        <div className="card" style={{ marginTop: ".8rem", textAlign: "center" }}>
          <p className="muted small" style={{ marginTop: 0 }}>Muestra este QR al pagar y te suman tu sello.</p>
          <img src={`/api/public/${slug}/loyalty/qr.svg?c=${encodeURIComponent(c)}`} alt="Tu QR personal" style={{ width: 200, background: "#fff", borderRadius: 12, padding: 8 }} />
        </div>
        {staff && (
          <div className="card" style={{ marginTop: ".8rem" }}>
            <b>Equipo del restaurante</b>
            <div className="row" style={{ marginTop: ".6rem" }}>
              <button className="btn grow" onClick={() => act("stamp")}>Sumar sello</button>
              <button className="btn ok grow" disabled={!card.ready} onClick={() => act("redeem")}>Canjear premio</button>
            </div>
            {msg && <p role="status" style={{ color: msg.bad ? "var(--bad)" : "var(--ok)", fontWeight: 700, marginBottom: 0 }}>{msg.t}</p>}
          </div>
        )}
      </main>
    </div>
  );
}
