import KitchenApp from "@/components/KitchenApp";
import "./kitchen.css";

export const metadata = { title: "Cocina y sala", description: undefined };

// /kitchen?r=<código del restaurante>  (el equipo entra con el PIN; el dueño ya trae sesión)
export default async function KitchenPage({ searchParams }: { searchParams: Promise<{ r?: string | string[] }> }) {
  const sp = await searchParams;
  return <KitchenApp slugHint={(Array.isArray(sp.r) ? sp.r[0] : sp.r) || ""} />;
}
