const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', ...opts };
  if (o.body && !(o.body instanceof FormData)) {
    o.headers = { 'Content-Type': 'application/json', ...(o.headers || {}) };
    o.body = JSON.stringify(o.body);
  }
  const res = await fetch(path, o);
  let data = null;
  try { data = await res.json(); } catch (e) { /* sin cuerpo */ }
  if (!res.ok) {
    const err = new Error((data && (data.error || (Array.isArray(data.detail) ? 'Revisa los datos ingresados' : data.detail))) || 'Error de red');
    err.status = res.status;
    throw err;
  }
  return data;
}

let _toastT;
function toast(msg, isErr) {
  let t = $('#toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg;
  t.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(_toastT);
  _toastT = setTimeout(() => t.classList.remove('show'), 3200);
}

function makeMoney(decimals, currency) {
  const f = new Intl.NumberFormat('es-CO', { style: 'currency', currency, minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return v => f.format(v / Math.pow(10, decimals));
}

function ago(iso) {
  const s = Math.max(0, (Date.now() - Date.parse(iso.replace(' ', 'T') + 'Z')) / 1000);
  if (s < 60) return Math.floor(s) + ' s';
  return Math.floor(s / 60) + ' min';
}
function secsSince(iso) { return Math.max(0, (Date.now() - Date.parse(iso.replace(' ', 'T') + 'Z')) / 1000); }

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1175].forEach((f, i) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f; o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(.25, ctx.currentTime + i * .18);
      g.gain.exponentialRampToValueAtTime(.001, ctx.currentTime + i * .18 + .16);
      o.start(ctx.currentTime + i * .18); o.stop(ctx.currentTime + i * .18 + .17);
    });
  } catch (e) { /* sin audio */ }
}

function liveStream(url, handlers) {
  let es;
  const open = () => {
    es = new EventSource(url);
    Object.entries(handlers).forEach(([k, fn]) => es.addEventListener(k, e => fn(JSON.parse(e.data || '{}'))));
    es.onerror = () => { es.close(); setTimeout(open, 3000); };
  };
  open();
  return () => es && es.close();
}

function setBrand(color) {
  document.documentElement.style.setProperty('--brand', color);
  const rgb = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16));
  const lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
  document.documentElement.style.setProperty('--brand-ink', lum > 0.62 ? '#1d1a16' : '#fff');
}
