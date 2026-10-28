import AdminApp from "@/components/admin/AdminApp";
import "./admin.css";

export const metadata = { title: "Panel · MesaYa", description: undefined };

// /admin  (?welcome=1 al terminar el registro: abre directamente la Carta)
export default async function AdminPage({ searchParams }: { searchParams: Promise<{ welcome?: string | string[] }> }) {
  const sp = await searchParams;
  return <AdminApp welcome={!!(Array.isArray(sp.welcome) ? sp.welcome[0] : sp.welcome)} />;
}
