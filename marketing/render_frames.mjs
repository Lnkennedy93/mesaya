// Compone cada cuadro del video (título + pantalla real) con Chrome y lo guarda como PNG.
//   node render_frames.mjs            → horizontal (1920x1080) y vertical (1080x1920)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Browser, sleep } from 'file:///C:/Users/lnken/.claude/skills/design-taste-frontend/scripts/lib/cdp.mjs';

const scenes = JSON.parse(readFileSync('scenes.json', 'utf8'));
const ROOT = resolve('.');
const SIZES = { h: { w: 1920, h: 1080 }, v: { w: 1080, h: 1920 } };
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const VCROP = {   // [x, y, ancho, alto] como fracción de la pantalla de escritorio
  '01-importar-carta': [0.32, 0.22, 0.36, 0.56], '02-carta': [0.15, 0.03, 0.70, 0.55], '03-mesas-qr': [0.15, 0.02, 0.70, 0.75],
  '10-cocina': [0, 0.08, 0.67, 0.72], '11-sala': [0, 0, 0.82, 0.36], '13-opiniones': [0.15, 0, 0.72, 0.7],
  '17-asistente-pregunta': [0.16, 0.02, 0.68, 0.75], '18-asistente-ventas': [0.16, 0.02, 0.68, 0.5], '20-asistente-accion': [0.16, 0.02, 0.68, 0.82],
  '22-landing-precios': [0, 0, 1, 0.8],
};

function html(sc, i, o) {
  const { w, h } = SIZES[o];
  const V = o === 'v';
  const total = scenes.length;
  const img = sc.shot ? pathToFileURL(join(ROOT, 'shots', sc.shot + '.png')).href : '';
  const phone = sc.kind === 'phone';
  const crop = sc.crop || 1;
  // región para la pantalla
  const region = V ? { x: 70, y: 600, w: 940, h: 1080 } : { x: 700, y: 90, w: 1150, h: 900 };
  let vw, vh;   // tamaño del recuadro de la pantalla
  // en vertical una pantalla de escritorio completa queda ilegible: se recorta y se acerca a lo importante (fracciones del viewport 1440x900)
  const vc = V && !phone && sc.shot ? (VCROP[sc.shot] || [0.15, 0, 0.72, 0.75]) : null;
  let bg = `background-size:100% ${100 / crop}%;background-position:top`;
  if (phone) { vh = Math.min(region.h, V ? 1040 : 880); vw = vh * (390 / 844); }
  else if (vc) {
    const cw = vc[2] * 1440, ch = vc[3] * 900, s = Math.min(region.w / cw, region.h / ch);
    vw = cw * s; vh = ch * s;
    bg = `background-size:${1440 * s}px auto;background-position:${-vc[0] * 1440 * s}px ${-vc[1] * 900 * s}px`;
  } else { vw = Math.min(region.w, 1150); vh = vw * (900 / 1440) * crop; }
  const vx = region.x + (region.w - vw) / 2, vy = region.y + (region.h - vh) / 2;
  const frame = phone
    ? `<div class="phone" style="left:${vx - 16}px;top:${vy - 16}px;width:${vw + 32}px;height:${vh + 32}px"><div class="scr" style="background-image:url('${img}')"></div></div>`
    : `<div class="win" style="left:${vx}px;top:${vy}px;width:${vw}px;height:${vh}px"><div class="scr" style="background-image:url('${img}');${bg}"></div></div>`;
  const text = sc.kind === 'title'
    ? `<div class="big"><div class="logo">Mesa<b>Ya</b></div><h1>${esc(sc.title)}</h1><p>${esc(sc.caption)}</p></div>`
    : `<div class="txt"><div class="logo sm">Mesa<b>Ya</b></div><h2>${esc(sc.title)}</h2><p>${esc(sc.caption)}</p></div>${frame}`;
  return `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}
body{width:${w}px;height:${h}px;overflow:hidden;position:relative;font-family:'Segoe UI',system-ui,sans-serif;color:#1d1a16;
  background:${sc.kind === 'title' ? '#e4572e' : '#faf7f2'}}
.logo{font-weight:900;letter-spacing:-.02em}.logo b{color:#e4572e}
.big{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;color:#fff;padding:0 ${V ? 70 : 220}px;gap:${V ? 38 : 28}px}
.big .logo{font-size:${V ? 96 : 84}px}.big .logo b{color:#1d1a16}
.big h1{font-size:${V ? 104 : 96}px;line-height:1.02;font-weight:900;letter-spacing:-.03em}
.big p{font-size:${V ? 44 : 38}px;line-height:1.3;opacity:.95;max-width:${V ? 900 : 1200}px}
.txt{position:absolute;${V ? 'left:70px;top:90px;width:940px' : 'left:90px;top:0;bottom:0;width:540px;display:flex;flex-direction:column;justify-content:center'};gap:${V ? 22 : 26}px}
.txt .logo.sm{font-size:${V ? 46 : 40}px;${V ? 'margin-bottom:36px' : 'position:absolute;top:56px;left:0'}}
.txt h2{font-size:${V ? 86 : 70}px;line-height:1.04;font-weight:900;letter-spacing:-.03em}
.txt p{font-size:${V ? 40 : 31}px;line-height:1.35;color:#5b544b}
.win{position:absolute;border-radius:20px;overflow:hidden;background:#fff;box-shadow:0 40px 90px rgba(80,40,10,.28),0 0 0 1px rgba(0,0,0,.06)}
.phone{position:absolute;background:#1d1a16;border-radius:60px;padding:16px;box-shadow:0 40px 90px rgba(80,40,10,.32)}
.phone .scr{width:100%;height:100%;border-radius:46px;background-size:cover;background-position:top}
.win .scr{width:100%;height:100%;background-repeat:no-repeat}
.bar{position:absolute;left:0;bottom:0;height:10px;width:${((i + 1) / total) * 100}%;background:${sc.kind === 'title' ? '#fff' : '#e4572e'}}
${V && sc.kind !== 'title' ? `.cta{position:absolute;left:70px;right:70px;bottom:70px;background:#1d1a16;color:#fff;border-radius:99px;text-align:center;font-weight:800;font-size:40px;padding:26px}` : ''}
</style>${sc.kind === 'title' ? '' : ''}${text}${V && sc.kind !== 'title' ? '<div class="cta">Pruébalo gratis 14 días · sin tarjeta</div>' : ''}<div class="bar"></div>`;
}

const b = await Browser.launch({ width: 1920, height: 1080 });
try {
  for (const o of Object.keys(SIZES)) {
    mkdirSync(`frames/${o}`, { recursive: true });
    const { w, h } = SIZES[o];
    const page = await b.newPage({ width: w, height: h, dsf: 1 });
    for (const [i, sc] of scenes.entries()) {
      const file = resolve(`frames/${o}/_tpl.html`);
      writeFileSync(file, html(sc, i, o));
      await page.goto(pathToFileURL(file).href, { settleMs: 500 });
      await page.screenshot({ path: `frames/${o}/${sc.id}.png`, format: 'png' });
    }
    await page.close();
    console.log('✓ cuadros', o);
  }
} finally {
  await b.close();
}
