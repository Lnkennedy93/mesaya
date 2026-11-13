import CardFinder from "@/components/CardFinder";
import "../menu.css";

export const metadata = { title: "Mi tarjeta de sellos", description: undefined, robots: { index: false, follow: false } };

// /r/<slug>/mi-tarjeta?k=<clave>  (el QR de «ver la tarjeta» que el restaurante imprime apunta aquí)
export default async function FindPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const { slug } = await params;
  const sp = await searchParams;
  const k = Array.isArray(sp.k) ? sp.k[0] : sp.k;
  return <CardFinder slug={slug} k={k || ""} />;
}
