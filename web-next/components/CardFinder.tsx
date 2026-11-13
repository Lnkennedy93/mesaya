"use client";
// El QR impreso de «ver mi tarjeta»: si este celular ya conoce su tarjeta, entra directo; si no, pide cédula y celular una sola vez.
import { useEffect, useState } from "react";
import { api, setBrand } from "@/lib/api";

type Info = { name: string; logo: string; brand_color: string; brand_color2: string; brand_color3: string };

export default function CardFinder({ slug, k }: { slug: string; k: string }) {
  const [info, setInfo] = useState<Info | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const i = await api<Info>(`/api/public/${slug}/customers/signup?k=${encodeURIComponent(k)}`); // valida el QR y trae el nombre y los colores
        let saved = "";
        try { saved = localStorage.getItem("mesaya_card_" + slug) || ""; } catch { /* sin almacenamiento */ }
        if (saved) { // este celular ya abrió su tarjeta: si sigue vigente, directo a ella
          try { await api(`/api/public/${slug}/loyalty/card?c=${encodeURIComponent(saved)}`); location.replace(`/r/${slug}/tarjeta?c=${encodeURIComponent(saved)}`); return; }
          catch { try { localStorage.removeItem("mesaya_card_" + slug); } catch { /* nada */ } }
        }
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
      const r = await api<{ card: string }>(`/api/public/${slug}/loyalty/find`, { method: "POST", body: { k, document: d.document, phone: d.phone } });
      location.replace(r.card);
    } catch (x: any) { setMsg(x.message); setBusy(false); }
  }

  if (err) return <div className="menu-root"><div className="notice" role="alert">{err}</div></div>;
  if (!info) return <div className="menu-root" aria-busy="true"><p className="muted" style={{ textAlign: "center", marginTop: "3rem" }}>…</p></div>;

  return (
    <div className="menu-root">
      <div className="hero">
        <div className="thumb logo">{info.logo ? <img src={info.logo} alt="" /> : info.name.slice(0, 1).toUpperCase()}</div>
        <div className="grow"><h1>{info.name}</h1><div className="muted small">Tarjeta de sellos</div></div>
      </div>
      <main>
        <form className="card" style={{ marginTop: "1rem" }} onSubmit={submit}>
          <h2 style={{ marginTop: 0 }}>Ver mi tarjeta</h2>
          <p className="muted small">Escribe tu cédula y el celular con el que te registraste. Solo lo pedimos esta vez: este celular recordará tu tarjeta.</p>
          <label htmlFor="cf-doc">Número de cédula</label>
          <input id="cf-doc" name="document" inputMode="numeric" autoComplete="off" required maxLength={20} />
          <label htmlFor="cf-tel">Número de celular</label>
          <input id="cf-tel" name="phone" type="tel" inputMode="tel" autoComplete="tel" required maxLength={20} />
          {msg && <p role="alert" style={{ color: "var(--bad)", fontWeight: 700 }}>{msg}</p>}
          <button className="btn block" style={{ marginTop: "1rem" }} disabled={busy}>{busy ? "Buscando…" : "Ver mi tarjeta"}</button>
        </form>
        <p className="muted small" style={{ textAlign: "center", marginTop: "1rem" }}>¿Aún no te has registrado? <a href={`/r/${slug}/registro?k=${encodeURIComponent(k)}`}>Regístrate aquí</a>.</p>
      </main>
    </div>
  );
}
