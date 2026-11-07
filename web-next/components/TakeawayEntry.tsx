"use client";
// El QR para llevar apunta a /r/<slug>?pl=<clave>: aquí se canjea por una «mesa» propia de este cliente y se abre la carta de siempre.
import { useEffect, useState } from "react";
import { api, ls } from "@/lib/api";

export default function TakeawayEntry({ slug, pl }: { slug: string; pl: string }) {
  const [err, setErr] = useState("");
  useEffect(() => {
    (async () => {
      try {
        let c: { table: string; key: string; pl: string } | null = null;
        try { c = JSON.parse(ls("mesaya_pl_" + slug) || "null"); } catch { /* sin datos guardados */ }
        if (!c || c.pl !== pl) { // el mismo celular conserva su código entre visitas (así ve el estado de su pedido)
          c = { ...(await api<{ table: string; key: string }>(`/api/public/${slug}/takeaway/start`, { method: "POST", body: { pl } })), pl };
          ls("mesaya_pl_" + slug, JSON.stringify(c));
        }
        location.replace(`/r/${slug}?t=${encodeURIComponent(c!.table)}&k=${encodeURIComponent(c!.key)}`);
      } catch (e: any) {
        setErr(e.message);
      }
    })();
  }, [slug, pl]);
  return <div style={{ padding: "3rem 1rem", textAlign: "center" }}>{err ? <p>{err}</p> : <p className="muted">…</p>}</div>;
}
