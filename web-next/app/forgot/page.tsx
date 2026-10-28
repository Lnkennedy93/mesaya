import AuthForm from "@/components/AuthForm";
import "../login/auth.css";

export const metadata = { title: "Recuperar contraseña · MesaYa", description: undefined };

export default function ForgotPage() {
  return <AuthForm mode="forgot" />;
}
