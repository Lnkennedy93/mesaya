import AuthForm from "@/components/AuthForm";
import "../login/auth.css";

export const metadata = { title: "Nueva contraseña · MesaYa", description: undefined };

// /reset?token=...  (sin token se muestra "recuperar contraseña", igual que la versión actual)
export default async function ResetPage({ searchParams }: { searchParams: Promise<{ token?: string | string[] }> }) {
  const sp = await searchParams;
  const token = (Array.isArray(sp.token) ? sp.token[0] : sp.token) || "";
  return <AuthForm mode={token ? "reset" : "forgot"} token={token} />;
}
