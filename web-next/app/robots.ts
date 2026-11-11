import type { MetadataRoute } from "next";

// Lo público es la página de inicio y el registro. El panel, la cocina y las cartas (con clave de mesa en la URL) no deben salir en Google.
export default function robots(): MetadataRoute.Robots {
  return { rules: [{ userAgent: "*", allow: "/", disallow: ["/admin", "/superadmin", "/kitchen", "/login", "/forgot", "/reset", "/print", "/api/", "/r/"] }] };
}
