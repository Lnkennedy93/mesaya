import CustomerSignup from "@/components/CustomerSignup";
import "../menu.css";

export const metadata = { title: "Registro de fidelización", description: undefined, robots: { index: false, follow: false } };

// /r/<slug>/registro?k=<clave>  (el QR de «Fidelización Clientes» apunta aquí)
export default async function SignupPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ [k: string]: string | string[] | undefined }>;
}) {
  const { slug } = await params;
  const sp = await searchParams;
  const k = Array.isArray(sp.k) ? sp.k[0] : sp.k;
  return <CustomerSignup slug={slug} k={k || ""} />;
}
