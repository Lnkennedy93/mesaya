import AuthForm from "@/components/AuthForm";
import "../login/auth.css";

export const metadata = { title: "Prueba gratis · MesaYa", description: undefined };

export default function SignupPage() {
  return <AuthForm mode="signup" />;
}
