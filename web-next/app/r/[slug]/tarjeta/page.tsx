import LoyaltyCard from "@/components/LoyaltyCard";
import "../menu.css";

export const metadata = { title: "Mi tarjeta de sellos", description: undefined, robots: { index: false, follow: false } };

// /r/<slug>/tarjeta?c=<clave>  (el QR o la tarjeta NFC personal de cada cliente apunta aquí)
export default async function CardPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const { slug } = await params;
  const sp = await searchParams;
  const c = Array.isArray(sp.c) ? sp.c[0] : sp.c;
  return <LoyaltyCard slug={slug} c={c || ""} nuevo={sp.nuevo === "1"} />;
}
