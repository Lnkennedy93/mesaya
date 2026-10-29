// Cliente del backend de MesaYa (mismo contrato que web/assets/common.js).
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method, credentials: "same-origin" };
  if (opts.body instanceof FormData) {
    init.body = opts.body; // subida de archivos: el navegador pone el Content-Type
  } else if (opts.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    /* sin cuerpo */
  }
  if (!res.ok) {
    const msg = data && (data.error || (Array.isArray(data.detail) ? "Revisa los datos ingresados" : data.detail));
    throw new ApiError(msg || "Error de red", res.status);
  }
  return data as T;
}

export function makeMoney(decimals: number, currency: string) {
  const f = new Intl.NumberFormat("es-CO", { style: "currency", currency, minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return (v: number) => f.format(v / Math.pow(10, decimals));
}

/** Aplica el color de marca del restaurante (variables CSS en <html>). */
export function setBrand(color: string) {
  const root = document.documentElement;
  root.style.setProperty("--brand", color);
  const rgb = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
  const lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
  root.style.setProperty("--brand-ink", lum > 0.62 ? "#1d1a16" : "#fff");
}

/** localStorage a prueba de fallos (modo privado, cookies bloqueadas...). */
export function ls(key: string, value?: string): string | null {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch {
    /* sin almacenamiento */
  }
  return null;
}

/** Consulta cada `ms` milisegundos mientras la pestaña esté visible. Devuelve la función para detenerla.
 *  En Vercel no hay conexiones en vivo (SSE) que compartan las instancias del servidor, así que se consulta. */
export function poll(fn: () => unknown, ms: number) {
  const t = setInterval(() => { if (!document.hidden) fn(); }, ms);
  return () => clearInterval(t);
}

/** Reduce una foto de celular (3-10 MB) antes de subirla: una petición a Vercel admite 4,5 MB y el servidor la baja a 1000 px igual. */
export async function shrinkImage(file: File, max = 1600): Promise<File> {
  if (file.size < 1_500_000 || !file.type.startsWith("image/")) return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k);
    c.height = Math.round(bmp.height * k);
    c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
    const blob: Blob | null = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.85));
    return blob ? new File([blob], "foto.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}

/** Segundos desde una fecha UTC del backend ("2026-10-27 18:03:11"). */
export function secsSince(iso: string) {
  return Math.max(0, (Date.now() - Date.parse(iso.replace(" ", "T") + "Z")) / 1000);
}

/** Doble pitido de aviso (pedido nuevo, llamado, pago por confirmar). */
export function beep() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    [880, 1175].forEach((f, i) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = f;
      o.connect(g);
      g.connect(ctx.destination);
      g.gain.setValueAtTime(0.25, ctx.currentTime + i * 0.18);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.18 + 0.16);
      o.start(ctx.currentTime + i * 0.18);
      o.stop(ctx.currentTime + i * 0.18 + 0.17);
    });
  } catch {
    /* sin audio */
  }
}
