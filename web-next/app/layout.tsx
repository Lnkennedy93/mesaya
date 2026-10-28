import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MesaYa · Menú QR que sí recibe pedidos",
  description:
    "Tu QR ya no solo muestra la carta: tus clientes piden desde su celular y el pedido llega a cocina con el número de mesa. Sin app. 14 días gratis, sin tarjeta.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#e4572e" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" data-auto-theme>
      <body>{children}</body>
    </html>
  );
}
