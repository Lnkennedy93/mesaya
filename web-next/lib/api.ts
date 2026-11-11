// Cliente del backend de MesaYa (mismo contrato que web/assets/common.js).
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; headers?: Record<string, string>; timeout?: number } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method, credentials: "same-origin", headers: opts.headers };
  if (opts.body instanceof FormData) {
    init.body = opts.body; // subida de archivos: el navegador pone el Content-Type
  } else if (opts.body !== undefined) {
    init.headers = { ...opts.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }
  // con mala señal una petición no puede quedarse colgada para siempre (el botón de enviar quedaría deshabilitado)
  const ctl = new AbortController();
  init.signal = ctl.signal;
  const ms = opts.timeout ?? (opts.body instanceof FormData || /^\/api\/(assistant|import)/.test(path) ? 120000 : 25000);
  const timer = setTimeout(() => ctl.abort(), ms);
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Sin conexión o la red está lenta. Intenta de nuevo.", 0);
  } finally {
    clearTimeout(timer);
  }
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
  // texto del botón: el que dé más contraste (WCAG) sobre el color de marca, no una regla fija de luminosidad
  const L = (hex: string) => {
    const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const lb = L(color);
  const onWhite = 1.05 / (lb + 0.05);
  const onDark = (lb + 0.05) / (L("#1d1a16") + 0.05);
  root.style.setProperty("--brand-ink", onWhite >= onDark ? "#fff" : "#1d1a16");
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
  const back = () => { if (!document.hidden) fn(); }; // al volver a la pestaña se actualiza ya, sin esperar el próximo turno
  document.addEventListener("visibilitychange", back);
  return () => { clearInterval(t); document.removeEventListener("visibilitychange", back); };
}

/** Mantiene la pantalla encendida (una tablet de cocina que se bloquea deja de sondear y no suena nada). Devuelve cómo soltarla. */
export function keepAwake() {
  let lock: any = null;
  let off = false;
  const ask = async () => {
    try { if (!off && !document.hidden && "wakeLock" in navigator) lock = await (navigator as any).wakeLock.request("screen"); } catch { /* sin soporte o sin permiso */ }
  };
  const again = () => { if (!document.hidden) ask(); }; // el navegador la suelta al ocultar la pestaña
  ask();
  document.addEventListener("visibilitychange", again);
  return () => { off = true; document.removeEventListener("visibilitychange", again); try { lock?.release(); } catch { /* ya suelta */ } };
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

let ctx_: AudioContext | null = null; // uno solo para toda la sesión: crear uno por pitido agota los que admite el navegador y la cocina queda muda sin avisar
function audio(): AudioContext | null {
  try {
    ctx_ = ctx_ || new (window.AudioContext || (window as any).webkitAudioContext)();
    if (ctx_.state === "suspended") ctx_.resume();
    return ctx_;
  } catch {
    return null;
  }
}
/** Desbloquea el audio con el primer toque del usuario (iOS no deja sonar nada antes). */
export function unlockAudio() { audio(); }

/** Doble pitido de aviso (pedido nuevo, llamado, pago por confirmar). */
export function beep() {
  try {
    const ctx = audio();
    if (!ctx) return;
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
