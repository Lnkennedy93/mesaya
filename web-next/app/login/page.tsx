import AuthForm from "@/components/AuthForm";
import "./auth.css";

export const metadata = { title: "Entrar · MesaYa", description: undefined };

export default function LoginPage() {
  return <AuthForm mode="login" />;
}
