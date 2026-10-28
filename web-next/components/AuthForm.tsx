"use client";
// Entrar, registro, recuperar y crear nueva contraseña (portada de web/auth.html). Mismos endpoints /api/...
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import Powered from "@/components/Powered";
import { useToast } from "@/components/useToast";

export type AuthMode = "login" | "signup" | "forgot" | "reset";
const CURRENCIES = ["COP", "USD", "MXN", "PEN", "CLP", "ARS", "EUR", "GTQ", "DOP"];

export default function AuthForm({ mode, token = "" }: { mode: AuthMode; token?: string }) {
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [toastNode, toast] = useToast();
  const s = mode === "signup";

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d: Record<string, any> = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      if (mode === "forgot") {
        const r = await api("/api/forgot", { method: "POST", body: { email: d.email } });
        setSent(r.message);
        return;
      }
      if (mode === "reset") {
        if (d.password !== d.again) throw new Error("Las contraseñas no coinciden");
        await api("/api/reset", { method: "POST", body: { token, password: d.password } });
        location.href = "/admin";
        return;
      }
      if (d.tables) d.tables = +d.tables;
      if (s) d.accept_terms = !!d.accept_terms;
      await api("/api/" + mode, { method: "POST", body: d });
      location.href = s ? "/admin?welcome=1" : "/admin";
    } catch (err: any) {
      toast(err.message, true);
      setBusy(false);
    }
  }

  return (
    <div className="auth-root">
      <div className="box">
        <Link className="logo" href="/">Mesa<b>Ya</b></Link>
        <div className="card">
          {sent !== null ? (
            <>
              <h2>Revisa tu correo</h2>
              <p>{sent}</p>
              <p className="muted small">Si no te llega en unos minutos, revisa spam o escríbenos por WhatsApp para ayudarte.</p>
              <p className="swap small"><Link href="/login">Volver a entrar</Link></p>
            </>
          ) : mode === "forgot" ? (
            <>
              <h2>Recuperar contraseña</h2>
              <p className="muted small" style={{ marginTop: 0 }}>Escribe tu correo y te enviaremos un enlace para crear una nueva.</p>
              <form onSubmit={submit}>
                <label>Correo</label>
                <input name="email" type="email" required autoComplete="email" />
                <button className="btn block" style={{ marginTop: "1.2rem" }} disabled={busy}>Enviar enlace</button>
              </form>
              <p className="swap small"><Link href="/login">Volver a entrar</Link></p>
            </>
          ) : mode === "reset" ? (
            <>
              <h2>Crea tu nueva contraseña</h2>
              <form onSubmit={submit}>
                <label>Nueva contraseña</label>
                <input name="password" type="password" required minLength={8} autoComplete="new-password" placeholder="Mínimo 8 caracteres" />
                <label>Repítela</label>
                <input name="again" type="password" required minLength={8} autoComplete="new-password" />
                <button className="btn block" style={{ marginTop: "1.2rem" }} disabled={busy}>Guardar y entrar</button>
              </form>
            </>
          ) : (
            <>
              <h2>{s ? "Prueba gratis 14 días" : "Entrar a tu panel"}</h2>
              <p className="muted small" style={{ marginTop: 0 }}>{s ? "Sin tarjeta de crédito. Tu carta digital lista en minutos." : "Bienvenido de nuevo."}</p>
              <form onSubmit={submit}>
                {s && (
                  <>
                    <label>Nombre del restaurante</label>
                    <input name="name" required minLength={2} maxLength={60} autoComplete="organization" />
                  </>
                )}
                <label>Correo</label>
                <input name="email" type="email" required autoComplete="email" />
                <label>Contraseña</label>
                <input name="password" type="password" required minLength={8} autoComplete={s ? "new-password" : "current-password"} placeholder={s ? "Mínimo 8 caracteres" : ""} />
                {s && (
                  <>
                    <div className="two">
                      <div><label>Moneda</label><select name="currency">{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></div>
                      <div><label>Número de mesas</label><input name="tables" type="number" min={1} max={60} defaultValue={8} /></div>
                    </div>
                    <label className="terms">
                      <input type="checkbox" name="accept_terms" required />{" "}
                      <span>
                        Acepto los <a href="/terminos" target="_blank" rel="noopener">Términos y condiciones</a> y autorizo el tratamiento de mis datos según la{" "}
                        <a href="/privacidad" target="_blank" rel="noopener">Política de tratamiento de datos</a>.
                      </span>
                    </label>
                  </>
                )}
                <button className="btn block" style={{ marginTop: "1.2rem" }} disabled={busy}>{s ? "Crear mi cuenta" : "Entrar"}</button>
              </form>
              {!s && <p className="swap small" style={{ marginBottom: 0 }}><Link href="/forgot">¿Olvidaste tu contraseña?</Link></p>}
              <p className="swap small">
                {s ? <>¿Ya tienes cuenta? <Link href="/login">Entrar</Link></> : <>¿Aún no tienes cuenta? <Link href="/signup">Prueba gratis</Link></>}
              </p>
            </>
          )}
        </div>
      </div>
      {toastNode}
      <Powered />
    </div>
  );
}
