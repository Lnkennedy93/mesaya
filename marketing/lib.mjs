// Ayudas compartidas por los guiones de captura: abre Chrome sin ventana contra la app LOCAL (nunca producción).
import { Browser, sleep } from 'file:///C:/Users/lnken/.claude/skills/design-taste-frontend/scripts/lib/cdp.mjs';

export { sleep };
export const BASE = 'http://localhost:3100';
export const OWNER = { email: 'demo@mesaya.app', password: 'demo12345' }; // cuenta de demostración local (backend/seed.py)

export async function launch() {
  return Browser.launch({ width: 1440, height: 900 });
}

/** Abre una página con el tamaño dado e inicia sesión como dueño (o como cocina con el PIN). */
export async function openPage(browser, { width, height, dsf = 1, mobile = false, login = 'owner' }) {
  const page = await browser.newPage({ width, height, dsf, mobile });
  if (login) {
    await page.goto(BASE + '/login', { settleMs: 500 });
    const body = login === 'owner' ? OWNER : null;
    if (body) await page.eval(`fetch('/api/login',{method:'POST',headers:{'content-type':'application/json'},body:${JSON.stringify(JSON.stringify(body))}}).then(r=>r.status)`);
    else await page.eval(`fetch('/api/staff-login',{method:'POST',headers:{'content-type':'application/json'},body:${JSON.stringify(JSON.stringify({ slug: 'dragon-dorado', pin: '1234' }))}}).then(r=>r.status)`);
  }
  return page;
}

export const text = (page, sel = 'body') => page.eval(`document.querySelector(${JSON.stringify(sel)})?.innerText || ''`);

/** Hace clic en el primer elemento clicable cuyo texto contiene `label` (sin importar mayúsculas). */
export async function clickText(page, label, { sel = 'button, a, [role=button], label, summary, .it, li' } = {}) {
  const ok = await page.eval(`(() => {
    const want = ${JSON.stringify(label)}.toLowerCase();
    const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find(e => e.offsetParent !== null && (e.innerText || '').toLowerCase().includes(want));
    if (!el) return false; el.scrollIntoView({ block: 'center' }); el.click(); return true; })()`);
  if (!ok) throw new Error('No encontré un elemento con el texto: ' + label);
  await sleep(450);
}
