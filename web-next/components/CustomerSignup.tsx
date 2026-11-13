"use client";
// Lo que ve el cliente al escanear el QR de fidelización: llena sus datos y quedan en la base de ESE restaurante.
import { useEffect, useState } from "react";
import { api, setBrand } from "@/lib/api";

type Info = { name: string; logo: string; brand_color: string; brand_color2: string; brand_color3: string };

export default function CustomerSignup({ slug, k }: { slug: string; k: string }) {
  const [info, setInfo] = useState<Info | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const i = await api<Info>(`/api/public/${slug}/customers/signup?k=${encodeURIComponent(k)}`);
        setInfo(i);
        if (i.brand_color) setBrand(i.brand_color, i.brand_color2, i.brand_color3);
      } catch (e: any) { setErr(e.message); }
    })();
  }, [slug, k]);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d: any = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true); setMsg("");
    try {
      const res = await api<{ card?: string }>(`/api/public/${slug}/customers/signup`, { method: "POST", body: { k, ...d, consent: !!d.consent } });
      if (res.card) { location.replace(res.card); return; } // con tarjeta de sellos: directo a SU tarjeta, donde puede crear el acceso directo
      setDone(String(d.name).trim().split(" ")[0]);
    } catch (x: any) { setMsg(x.message); }
    setBusy(false);
  }

  if (err) return <div className="menu-root"><div className="notice" role="alert">{err}</div></div>;
  if (!info) return <div className="menu-root" aria-busy="true"><p className="muted" style={{ textAlign: "center", marginTop: "3rem" }}>…</p></div>;

  return (
    <div className="menu-root">
      <div className="hero">
        <div className="thumb logo">{info.logo ? <img src={info.logo} alt="" /> : info.name.slice(0, 1).toUpperCase()}</div>
        <div className="grow"><h1>{info.name}</h1><div className="muted small">Programa de fidelización</div></div>
      </div>
      <main>
        {done ? (
          <div className="card" style={{ marginTop: "1rem", textAlign: "center" }}>
            <h2>¡Gracias, {done}!</h2>
            <p className="muted">Ya haces parte de la fidelización de {info.name}. Puedes cerrar esta página.</p>
          </div>
        ) : (
          <form className="card" style={{ marginTop: "1rem" }} onSubmit={submit}>
            <h2 style={{ marginTop: 0 }}>Únete y recibe beneficios</h2>
            <p className="muted small">Llena tus datos una sola vez.</p>
            <label htmlFor="cs-doc">Número de cédula</label>
            <input id="cs-doc" name="document" inputMode="numeric" autoComplete="off" required maxLength={20} />
            <label htmlFor="cs-name">Nombre completo</label>
            <input id="cs-name" name="name" autoComplete="name" required minLength={3} maxLength={100} />
            <label htmlFor="cs-mail">Correo electrónico</label>
            <input id="cs-mail" name="email" type="email" autoComplete="email" required maxLength={120} />
            <label htmlFor="cs-tel">Número de celular</label>
            <input id="cs-tel" name="phone" type="tel" inputMode="tel" autoComplete="tel" required maxLength={20} />
            <label style={{ display: "flex", gap: ".5rem", alignItems: "flex-start", fontWeight: 500, color: "var(--ink)", marginTop: "1rem" }}>
              <input name="consent" type="checkbox" style={{ width: "auto", marginTop: ".2rem" }} required />
              <span>Autorizo a {info.name} a tratar mis datos personales (cédula, nombre, correo y celular) para su programa de fidelización, conforme a la Ley 1581 de 2012. <a href="/privacidad" target="_blank" rel="noopener">Política de privacidad</a>.</span>
            </label>
            {msg && <p role="alert" style={{ color: "var(--bad)", fontWeight: 700 }}>{msg}</p>}
            <button className="btn block" style={{ marginTop: "1rem" }} disabled={busy}>{busy ? "Enviando…" : "Registrarme"}</button>
          </form>
        )}
      </main>
    </div>
  );
}
