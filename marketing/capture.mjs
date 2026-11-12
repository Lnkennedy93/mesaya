// Captura las pantallas REALES de MesaYa (app local con datos de demostración) para el video y el catálogo.
//   node capture.mjs            → todas las escenas      node capture.mjs 13 14   → solo esas
// Requiere: backend en :8000 (SQLite local, tras correr seed_live.py) y Next en :3100.
import { mkdirSync } from 'node:fs';
import { launch, openPage, BASE, sleep, text, clickText } from './lib.mjs';

mkdirSync('shots', { recursive: true });
const only = process.argv.slice(2);
const D = { width: 1440, height: 900, dsf: 1.5 };   // escritorio
const M = { width: 390, height: 844, dsf: 2, mobile: true };  // celular del cliente
const HIDE_DEV = 'nextjs-portal,#__next-build-watcher,[data-nextjs-toast]{display:none!important}';

const prep = async (p) => {
  await p.eval(`(() => { const s = document.createElement('style'); s.textContent = ${JSON.stringify(HIDE_DEV)}; document.head.appendChild(s); })()`);
  await sleep(250);
};
const shot = async (p, name) => { await prep(p); await p.screenshot({ path: `shots/${name}.png`, format: 'png' }); console.log('  ✓', name); };
const tab = async (p, label) => { await clickText(p, label, { sel: 'nav button' }); await sleep(1400); };
const adminAt = async (b, tabName) => {
  const p = await openPage(b, D);
  await p.goto(BASE + '/admin', { settleMs: 1800 });
  if (tabName) await tab(p, tabName);
  return p;
};
const typeInto = (p, sel, value) => p.eval(`(() => { const el = document.querySelector(${JSON.stringify(sel)});
  const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; set.call(el, ${JSON.stringify(value)});
  el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
const waitFor = async (p, test, ms = 60000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await p.eval(test)) return true; await sleep(700); }
  return false;
};

const scenes = {
  // --- panel del dueño
  async 1(b) {
    const p = await adminAt(b, 'Carta');
    await clickText(p, 'Importar carta', { sel: 'button' });
    await sleep(600);
    await typeInto(p, 'textarea', '# Entradas\nEmpanadas criollas - 8.000 - Rellenas de carne\nPapas rellenas | 9500\n# Platos fuertes\nBandeja paisa 32.000\nSancocho de gallina - 28.000\n# Bebidas\nLimonada de coco 9.000\nJugo natural - 7.000');
    await clickText(p, 'Leer texto', { sel: 'button' });
    await sleep(1200);
    await shot(p, '01-importar-carta');
  },
  async 2(b) { await shot(await adminAt(b, 'Carta'), '02-carta'); },
  async 3(b) { await shot(await adminAt(b, 'Mesas'), '03-mesas-qr'); },
  // --- cliente en su celular
  async 4(b) {
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado?t=6&k=demo6', { settleMs: 1800 });
    await shot(p, '04-cliente-carta');
  },
  async 5(b) {
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado?t=6&k=demo6', { settleMs: 1500 });
    await p.eval(`document.querySelector('.add').click()`); await sleep(700);
    await clickText(p, 'Para compartir', { sel: 'label' });
    await shot(p, '05-cliente-opciones');
    await clickText(p, 'Agregar al pedido', { sel: 'button' });
    await sleep(700);
    await shot(p, '06-cliente-carrito');
    await clickText(p, 'Ver pedido', { sel: 'button' });
    await sleep(900);
    console.log('  · hoja de pedido:', (await text(p)).slice(-260).replace(/\n/g, ' | '));
    await shot(p, '07-cliente-pedido');
  },
  async 6(b) {   // el cliente envía el pedido (queda en cocina como «Mesa 6 · Camila»)
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado?t=6&k=demo6', { settleMs: 1500 });
    await p.eval(`document.querySelectorAll('.add')[1].click()`); await sleep(600);
    await clickText(p, 'Agregar al pedido', { sel: 'button' }); await sleep(600);
    await p.eval(`document.querySelectorAll('.add')[5].click()`); await sleep(600);
    await clickText(p, 'Agregar al pedido', { sel: 'button' }); await sleep(600);
    await clickText(p, 'Ver pedido', { sel: 'button' }); await sleep(800);
    // el campo del nombre no tiene placeholder: es el primer input visible de la hoja que no es el buscador (#q)
    const typed = await p.eval(`(() => { const i=[...document.querySelectorAll('input')].find(i=>i.offsetParent && i.id!=='q' && i.type==='text'); if(!i) return false;
      const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; s.call(i,'Camila'); i.dispatchEvent(new Event('input',{bubbles:true})); return i.value; })()`);
    console.log('  · nombre escrito:', typed);
    await sleep(400);
    await shot(p, '08-cliente-nombre');
    await clickText(p, 'Enviar', { sel: 'button' });
    await sleep(1800);
    await shot(p, '09-cliente-enviado');
  },
  // --- cocina y sala
  async 7(b) {
    const p = await openPage(b, { ...D, login: 'staff' });
    await p.goto(BASE + '/kitchen', { settleMs: 3000 });
    await shot(p, '10-cocina');
    await clickText(p, 'Sala', { sel: 'button, a, [role=tab], .tab' });
    await sleep(1500);
    await shot(p, '11-sala');
  },
  async 8(b) {   // el cliente de la mesa 3 ve su cuenta y puede llamar al mesero
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado?t=3&k=demo3', { settleMs: 1500 });
    await clickText(p, 'Mi cuenta', { sel: 'button' });
    await sleep(1200);
    await shot(p, '12-cliente-cuenta');
  },
  // --- panel: opiniones, resumen, ajustes
  async 9(b) { await shot(await adminAt(b, 'Opiniones'), '13-opiniones'); },
  async 10(b) { await shot(await adminAt(b, 'Resumen'), '14-resumen'); },
  async 11(b) { await shot(await adminAt(b, 'Ajustes'), '15-ajustes'); },
  // --- asistente (Gemini real sobre la base local)
  async 12(b) {
    const p = await adminAt(b, 'Asistente');
    await shot(p, '16-asistente-inicio');
    const ask = async (q, file) => {
      await typeInto(p, 'input[aria-label="Pregunta"]', q);
      await sleep(300);
      if (file === '17-asistente-pregunta') await shot(p, file);
      await p.eval(`document.querySelector('form button').click()`);
      const ok = await waitFor(p, `!document.body.innerText.includes('Consultando tus datos')`, 90000);
      await sleep(900);
      if (file !== '17-asistente-pregunta') await shot(p, file);
      console.log('  · respuesta lista:', ok);
    };
    await ask('¿Cuánto vendí esta semana y cuál fue el plato más vendido?', '17-asistente-pregunta');
    await shot(p, '18-asistente-ventas');
    await ask('¿Qué mesas tengo libres y cuáles tienen la cuenta pendiente?', '19-asistente-mesas');
    await ask('Apaga la sopa wantán, se acabó.', '20-asistente-accion');
  },
  // --- pago por QR (Bre-B / Nequi): el cliente de la mesa 1 pide la cuenta con «QR» (queda el aviso en cocina) y el dueño ve dónde sube su QR
  async 14(b) {
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado?t=1&k=demo1', { settleMs: 1500 });
    await clickText(p, 'Mi cuenta', { sel: 'button' }); await sleep(1000);
    await clickText(p, 'Terminar mesa', { sel: 'button' }); await sleep(500);
    await shot(p, '24-cliente-metodo');
    await clickText(p, 'QR (Nequi', { sel: 'button' }); await sleep(1600);
    await shot(p, '25-cliente-pago-qr');
  },
  async 15(b) {
    const p = await adminAt(b, 'Ajustes');
    await p.eval(`[...document.querySelectorAll('h3')].find(h => h.textContent.includes('Pago por QR'))?.scrollIntoView({ block: 'center' })`);
    await sleep(900);
    await shot(p, '26-ajustes-qr');
  },
  // --- fidelización por QR y para llevar con pago ágil (el guion necesita REG_KEY, PL_TABLE y PL_KEY: los imprime mk_setup)
  async 16(b) {
    const p = await adminAt(b, 'Fidelización');
    await p.eval(`(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) n.nodeValue = n.nodeValue.replace('http://localhost:8000', 'https://mesaya.app'); })()`);
    await sleep(500);
    await shot(p, '27-fidelizacion');
  },
  async 17(b) {
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado/registro?k=' + process.env.REG_KEY, { settleMs: 1800 });
    await p.eval(`(() => { const s = (id, v) => { document.getElementById(id).value = v; }; s('cs-doc', '1032456789'); s('cs-name', 'Mariana Rojas'); s('cs-mail', 'mariana.rojas@correo.co'); s('cs-tel', '3105551122'); })()`);
    await sleep(500);
    await shot(p, '28-registro-cliente');
  },
  async 18(b) {
    const p = await adminAt(b, 'Para llevar');
    await p.eval(`(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) n.nodeValue = n.nodeValue.replace('http://localhost:8000', 'https://mesaya.app'); })()`);
    await sleep(500);
    await shot(p, '29-para-llevar');
  },
  async 19(b) {
    const p = await openPage(b, { ...M, login: null });
    await p.goto(BASE + '/r/dragon-dorado?t=' + encodeURIComponent(process.env.PL_TABLE) + '&k=' + process.env.PL_KEY, { settleMs: 1800 });
    await clickText(p, 'Mi pedido', { sel: 'button' }); await sleep(1200);
    await clickText(p, 'Avisar cómo', { sel: 'button' }); await sleep(700);
    await p.eval(`window.scrollTo(0, 40)`); await sleep(300);
    await shot(p, '30-para-llevar-pago');
  },
  // --- landing
  async 13(b) {
    const p = await openPage(b, { ...D, login: null });
    await p.goto(BASE + '/', { settleMs: 2000 });
    await p.eval(`document.getElementById('asistente').scrollIntoView({block:'start'})`); await sleep(900);
    await shot(p, '21-landing-asistente');
    await p.eval(`document.getElementById('precios').scrollIntoView({block:'start'})`); await sleep(900);
    await shot(p, '22-landing-precios');
    await p.eval(`window.scrollTo(0,0)`); await sleep(700);
    await shot(p, '23-landing-inicio');
  },
};

const b = await launch();
try {
  for (const n of Object.keys(scenes)) {
    if (only.length && !only.includes(n)) continue;
    console.log('Escena', n);
    try { await scenes[n](b); } catch (e) { console.log('  ✗ falló:', e.message); }
  }
} finally {
  await b.close();
}
