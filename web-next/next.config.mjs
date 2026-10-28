// Frontend Next.js de MesaYa. El backend (FastAPI) sigue siendo el mismo: aquí solo se reenvía.
// MESAYA_API_URL = dónde corre el backend (por defecto el de desarrollo local).
const API = (process.env.MESAYA_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  compress: false, // el stream en vivo (SSE) de la cocina no debe comprimirse ni quedarse en buffer
  poweredByHeader: false,
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
