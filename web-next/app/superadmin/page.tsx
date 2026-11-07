import SuperAdmin from "./SuperAdmin";
import "./superadmin.css";

export const metadata = { title: "Superusuario · MesaYa", description: undefined, robots: { index: false, follow: false } };

export default function SuperAdminPage() {
  return <SuperAdmin />;
}
