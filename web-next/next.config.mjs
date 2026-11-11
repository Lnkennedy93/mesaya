// Frontend Next.js de MesaYa. El backend (FastAPI) sigue siendo el mismo: aquí solo se reenvía.
// MESAYA_API_URL = dónde corre el backend (por defecto el de desarrollo local).
const API = (process.env.MESAYA_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  compress: false, // el stream en vivo (SSE) de la cocina no debe comprimirse ni quedarse en buffer
  poweredByHeader: false,
  async headers() {
    // Páginas de Next (la API y las páginas de legado ya las pone FastAPI). Sin CSP completa: las páginas usan scripts y estilos en línea.
    return [{
      source: "/((?!api/|uploads/|healthz|assets/|terminos|privacidad).*)",
      headers: [
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
        // En modo «solo reporte»: el navegador avisa en la consola de lo que bloquearía, sin romper nada. Pasarla a Content-Security-Policy cuando salga limpia.
        { key: "Content-Security-Policy-Report-Only", value: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      ],
    }];
  },
  async rewrites() {
    return {
      // Siempre al backend: API, fotos subidas y salud del servicio.
      beforeFiles: [
        { source: "/api/:path*", destination: `${API}/api/:path*` },
        { source: "/uploads/:path*", destination: `${API}/uploads/:path*` },
        { source: "/healthz", destination: `${API}/healthz` },
      ],
      // Páginas que aún no están en Next.js (migradas: /, /r/<slug>, /login, /signup, /forgot, /reset, /kitchen, /admin, /print/qr): las sirve la versión actual (web/), con sus propios /assets.
      fallback: [
        { source: "/assets/:path*", destination: `${API}/assets/:path*` },
        { source: "/terminos", destination: `${API}/terminos` },
        { source: "/privacidad", destination: `${API}/privacidad` },
      ],
    };
  },
};

export default nextConfig;
