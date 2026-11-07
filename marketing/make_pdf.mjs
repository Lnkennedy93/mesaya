// Exporta catalogo.html a PDF (A4) con Chrome sin ventana.   node make_pdf.mjs
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { Browser } from 'file:///C:/Users/lnken/.claude/skills/design-taste-frontend/scripts/lib/cdp.mjs';

mkdirSync('out', { recursive: true });
const b = await Browser.launch({ width: 794, height: 1123 });
try {
  const p = await b.newPage({ width: 794, height: 1123 });
  await p.goto(pathToFileURL(resolve('catalogo.html')).href, { settleMs: 1500 });
  const { data } = await p.send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true, marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0 }, 60000);
  writeFileSync('out/catalogo-mesaya.pdf', Buffer.from(data, 'base64'));
  console.log('✓ out/catalogo-mesaya.pdf');
} finally {
  await b.close();
}
