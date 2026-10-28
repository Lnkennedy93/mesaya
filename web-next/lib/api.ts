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

/** Canal en vivo (SSE) con reconexión automática. Devuelve la función para cerrarlo. */
export function liveStream(url: string, handlers: Record<string, (data: any) => void>) {
  let es: EventSource | null = null;
  let closed = false;
  const open = () => {
    if (closed) return;
    es = new EventSource(url);
    for (const [name, fn] of Object.entries(handlers)) {
      es.addEventListener(name, (e) => fn(JSON.parse((e as MessageEvent).data || "{}")));
    }
    es.onerror = () => {
      es?.close();
      if (!closed) setTimeout(open, 3000);
    };
  };
  open();
  return () => {
    closed = true;
    es?.close();
  };
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
