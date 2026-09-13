// Captura la página con el Chrome instalado (protocolo DevTools), a un viewport exacto y sin que el ancho mínimo de
// ventana de Chrome lo deforme. Con `full` mide el alto del documento y captura la página entera; la expresión opcional
// se evalúa en la página y se imprime como JSON (útil para medir rects).
// Uso: node scripts/screenshot.mjs <url> <ancho> <alto> <salida.png|-> [full] [expresión JS]
// Ej.: node scripts/screenshot.mjs http://localhost:3000/ 1440 900 /tmp/hero.png
//      node scripts/screenshot.mjs http://localhost:3000/ 390 844 /tmp/movil.png full
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const [, , url, width, height, out, full, expr] = process.argv;
const port = 9300 + Math.floor(Math.random() * 500);

const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
  `--remote-debugging-port=${port}`, `--user-data-dir=/tmp/matine-screenshot-${port}`, 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function targets() {
  for (let i = 0; i < 60; i++) {
    try { return await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
  }
  throw new Error('Chrome no levantó');
}

try {
  const page = (await targets()).find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0;
  const pending = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true })).result?.result?.value;

  const metrics = (h) => send('Emulation.setDeviceMetricsOverride', { width: +width, height: h, deviceScaleFactor: 1, mobile: +width < 600 });
  await metrics(+height);
  await send('Page.enable');
  await send('Page.navigate', { url });
  await sleep(3500);

  if (full === 'full') {
    const h = await evaluate('document.documentElement.scrollHeight');
    await metrics(h);
    await sleep(1500);
  }
  if (expr) console.log(JSON.stringify(await evaluate(expr), null, 1));
  if (out && out !== '-') {
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
    console.log('guardado', out);
  }
} finally {
  chrome.kill('SIGKILL');
}
