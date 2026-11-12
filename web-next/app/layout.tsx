import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import LabelFix from "@/components/LabelFix";

const DESC = "Tu QR ya no solo muestra la carta: tus clientes piden desde su celular y el pedido llega a cocina con el número de mesa. Sin app. 14 días gratis, sin tarjeta.";
export const metadata: Metadata = {
  metadataBase: new URL(process.env.MESAYA_BASE_URL || "https://mesaya-phi.vercel.app"),
  title: "MesaYa · Menú QR que sí recibe pedidos",
  description: DESC,
  openGraph: { title: "MesaYa · Menú QR que sí recibe pedidos", description: DESC, siteName: "MesaYa", locale: "es_CO", type: "website" },
};

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font" }); // se descarga al compilar y se sirve desde el propio dominio

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: [{ media: "(prefers-color-scheme: light)", color: "#e8f0f8" }, { media: "(prefers-color-scheme: dark)", color: "#070b12" }] };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" data-auto-theme className={inter.variable}>
      <body>
        {children}
        <LabelFix />
      </body>
    </html>
  );
}
