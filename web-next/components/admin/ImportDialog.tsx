"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Any, useAdmin } from "./ctx";

export default function ImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { ME, money, toMinor, toast } = useAdmin();
  const [draft, setDraft] = useState<Any>(null);
  const [text, setText] = useState("");
  const [reading, setReading] = useState<{ name: string; reason: string } | null>(null);
  const [secs, setSecs] = useState(0);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    if (!reading) return;
    const t0 = Date.now();
    setSecs(0);
    const t = setInterval(() => setSecs(Math.round((Date.now() - t0) / 1000)), 500);
    return () => clearInterval(t);
  }, [!!reading]); // eslint-disable-line react-hooks/exhaustive-deps

  async function waitForRead(jobId: string, reason?: string) {
    if (reason) setReading((r) => (r ? { ...r, reason: reason === "local_baja_confianza" ? "La lectura local no quedó segura: usamos IA para mejorarla." : reason } : r));
    const t0 = Date.now();
    while (true) {
      await new Promise((r) => setTimeout(r, 2000));
      if (!alive.current) throw new Error("Lectura cancelada");
      if (Date.now() - t0 > 6 * 60 * 1000) throw new Error("La lectura tardó demasiado. Inténtalo de nuevo.");
      const s = await api("/api/import/ai/" + jobId);
      if (s.status === "done") return s.result;
      if (s.status === "error") throw new Error(s.error);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.target;
    const f = input.files?.[0];
    if (!f) return;
    if (f.size > ME.max_import_mb * 1024 * 1024) {
      input.value = "";
      toast(`El archivo pesa ${(f.size / 1048576).toFixed(1)} MB y el máximo es ${ME.max_import_mb} MB. Exporta el PDF en calidad media o sin fotos pesadas.`, true);
      return;
    }
    const fd = new FormData();
    fd.append("file", f);
    setReading({ name: f.name, reason: "" });
    try {
      let r = await api("/api/import/ai", { method: "POST", body: fd });
      if (r.job_id) r = await waitForRead(r.job_id, r.reason);
      if (alive.current) { setReading(null); setDraft(r); }
    } catch (err: Any) {
      if (alive.current) { setReading(null); toast(err.message, true); }
    } finally { input.value = ""; }
  }

  async function parseText() {
    try {
      const r = await api("/api/import/text", { method: "POST", body: { text } });
      if (!r.categories.length) { toast("No pudimos leer platos. Usa «Nombre - precio» por línea.", true); return; }
      setDraft(r);
    } catch (e: Any) { toast(e.message, true); }
  }

  async function commit() {
    setBusy(true);
    try {
      const r = await api("/api/import/commit", { method: "POST", body: draft });
      toast(`${r.added} platos agregados${r.photos ? ` (${r.photos} con foto)` : ""}`);
      onDone();
    } catch (err: Any) { toast(err.message, true); setBusy(false); }
  }

  // ---- edición del borrador (fotos)
  const strip = (pred: (i: Any) => boolean) =>
    setDraft((d: Any) => ({ ...d, categories: d.categories.map((c: Any) => ({ ...c, items: c.items.map((i: Any) => { if (!pred(i)) return i; const { image, image_ref, ...rest } = i; return rest; }) })) }));

  if (reading)
    return (
      <div style={{ textAlign: "center", padding: "1.2rem .4rem" }}>
        <div style={{ fontSize: "2.4rem" }}>📖</div>
        <h2>Leyendo tu carta…</h2>
        <p className="muted small" style={{ margin: ".2rem 0" }}>{reading.name}</p>
        <p className="small" style={{ margin: ".2rem 0" }}>{reading.reason}</p>
        <p className="big"><span>{secs}</span> s</p>
        <p className="muted small">Si trae fotos de los platos, las extraemos también. Las cartas grandes pueden tardar un poco: no cierres esta ventana.</p>
      </div>
    );

  const canImg = ME.ai_available || ME.ocr_available;

  if (draft) {
    const counts: Record<string, number> = {};
    draft.categories.forEach((c: Any) => c.items.forEach((i: Any) => { if (i.image_ref) counts[i.image_ref[1]] = (counts[i.image_ref[1]] || 0) + 1; }));
    const withPhoto = draft.categories.reduce((s: number, c: Any) => s + c.items.filter((i: Any) => i.image_ref).length, 0);
    const repeated = Object.values(counts).filter((v) => v >= 3).length;
    return (
      <>
        <div className="row spread"><h2 style={{ margin: 0 }}>Importar carta</h2><button className="btn sm ghost" onClick={onClose}>✕</button></div>
        <p>
          Encontramos <b>{draft.categories.reduce((s: number, c: Any) => s + c.items.length, 0)} platos</b> en {draft.categories.length} categorías.{" "}
          {draft.source === "local" ? <span className="pill ok">Leído sin IA</span> : draft.source === "ai" ? <span className="pill brand">Leído con IA</span> : null} Revisa y confirma:
        </p>
        {(draft.warnings || []).map((w: string, i: number) => <div key={i} className="banner" style={{ margin: ".4rem 0", fontSize: ".85rem" }}>⚠️ {w}</div>)}
        {withPhoto > 0 && (
          <div className="row wrap small" style={{ margin: ".3rem 0", gap: ".5rem" }}>
            <span>📷 <b>{withPhoto}</b> platos con foto.</span>
            {repeated > 0 && <button className="btn sm ghost" onClick={() => strip((i) => !!i.image_ref && counts[i.image_ref[1]] >= 3)}>Quitar {repeated} foto(s) repetida(s)</button>}
            <button className="btn sm ghost" onClick={() => strip(() => true)}>Quitar todas las fotos</button>
          </div>
        )}
        <div style={{ maxHeight: "46vh", overflow: "auto" }} className="card">
          {draft.categories.map((c: Any, ci: number) => (
            <div key={ci}>
              {ci > 0 && <hr />}
              <b>{c.name}</b>
              {c.items.map((i: Any, ii: number) => (
                <div className="row small" style={{ padding: ".25rem 0", gap: ".6rem" }} key={ii}>
                  {i.image && (
                    <span style={{ position: "relative", flex: "none" }}>
                      <img src={i.image} alt="" style={{ width: 44, height: 44, borderRadius: 8, objectFit: "cover", display: "block" }} />
                      <button title="Quitar esta foto" style={{ position: "absolute", top: -6, right: -6, width: 18, height: 18, borderRadius: "50%", border: 0, background: "#1d1a16", color: "#fff", fontSize: ".7rem", lineHeight: 1, cursor: "pointer" }}
                        onClick={() => setDraft((d: Any) => ({ ...d, categories: d.categories.map((cc: Any, a: number) => (a !== ci ? cc : { ...cc, items: cc.items.map((x: Any, b: number) => { if (b !== ii) return x; const { image, image_ref, ...rest } = x; return rest; }) })) }))}>✕</button>
                    </span>
                  )}
                  <span className="grow">{i.name}</span><span className="muted">{i.price ? money(toMinor(i.price)) : "sin precio"}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="row spread" style={{ marginTop: "1rem" }}>
          <button className="btn ghost" onClick={() => setDraft(null)}>Volver</button>
          <button className="btn" disabled={busy} onClick={commit}>Agregar a mi carta</button>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="row spread"><h2 style={{ margin: 0 }}>Importar carta</h2><button className="btn sm ghost" onClick={onClose}>✕</button></div>
      <label>Opción 1 · Pega el texto de tu carta</label>
      <textarea placeholder={"# Entradas\nEmpanadas - 8.000 - Rellenas de carne\nLimonada | 6500\n\n# Platos fuertes\nBandeja paisa 32.000"} value={text} onChange={(e) => setText(e.target.value)} />
      <button className="btn block" style={{ marginTop: ".5rem" }} onClick={parseText}>Leer texto</button>
      <label style={{ marginTop: "1.2rem" }}>
        Opción 2 · Sube tu carta: PDF, Word, Excel{canImg ? ", foto" : ""}, .txt o .csv <span className="pill ok">Lectura sin IA</span> {ME.ai_available && <span className="pill brand">IA de respaldo</span>}
      </label>
      <input type="file" accept={".pdf,.docx,.xlsx,.txt,.csv" + (canImg ? ",image/*" : "")} onChange={onFile} />
      <p className="muted small" style={{ margin: ".4rem 0 0" }}>
        Los PDF con texto, Word y Excel se leen en tu servidor, al instante y sin enviar nada a terceros.{" "}
        {ME.ai_available
          ? "Las fotos y los PDF escaneados o difíciles se envían a " + (ME.ai_provider === "anthropic" ? "Anthropic (Claude)" : "Google (Gemini)") + " solo para leer la carta."
          : ME.ocr_available ? "Las fotos se leen con OCR." : "Para fotos y PDF escaneados el administrador debe activar la IA o el OCR."}{" "}
        Máximo {ME.max_import_mb} MB. Siempre revisas todo antes de agregarlo.
      </p>
    </>
  );
}
