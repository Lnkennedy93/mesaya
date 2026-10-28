import MenuApp from "@/components/MenuApp";
import "./menu.css";

export const metadata = { title: "Carta", description: undefined };

// /r/<slug>?t=<mesa>&k=<clave>  (el QR de cada mesa apunta aquí; mismo formato que la versión actual)
export default async function MenuPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const { slug } = await params;
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) || "";
  return <MenuApp slug={slug} table={one(sp.t)} tableKey={one(sp.k)} initialView={one(sp.view) === "bill" ? "bill" : "menu"} justPaid={one(sp.paid) === "1"} />;
}
