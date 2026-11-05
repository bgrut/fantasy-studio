// What draws this pixel? Crystal Works from a pin; every scene object is hidden in turn and the picture compared.
// PIN='{"pos":[..],"look":[..]}' BOX=x0,y0,x1,y1 [URL=] node _flagwho.mjs   -> objects whose removal changes the box most
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(8000);
const [x0, y0, x1, y1] = process.env.BOX.split(',').map(Number);
await p.evaluate(pn => { window.__camPin = pn; }, JSON.parse(process.env.PIN)); await w(2000);
const grab = async () => { await w(250); const s = await p.screenshot({ type: 'png', clip: { x: x0, y: y0, width: x1 - x0, height: y1 - y0 }, encoding: 'base64' }); return s; };
const lum = async (s) => p.evaluate(async (s) => { const i = new Image(); i.src = 'data:image/png;base64,' + s; await i.decode(); const c = document.createElement('canvas'); c.width = i.width; c.height = i.height; const g = c.getContext('2d'); g.drawImage(i, 0, 0); const d = g.getImageData(0, 0, c.width, c.height).data; let t = 0, hi = 0; for (let k = 0; k < d.length; k += 4) { const l = d[k] + d[k + 1] + d[k + 2]; t += l; if (l > 330) hi++; } return [t / (d.length / 4) / 3, hi]; }, s);
const base = await lum(await grab());
const n = await p.evaluate(() => { const L = []; window.__scene.traverse(o => { if (o.isMesh || o.isPoints || o.isLineSegments || o.isSprite) L.push(o); }); window.__L = L.filter(o => { for (let q = o; q; q = q.parent) if (!q.visible) return false; return true; }); return window.__L.length; });
const res = [];
console.log('base', base, 'objects', n);
for (let i = 0; i < n; i++) {
  const nm = await p.evaluate(i => { const o = window.__L[i]; o.visible = false; let par = o.parent ? o.parent.name : ''; return `${o.name || o.type}/${par}/${o.isInstancedMesh ? 'inst' + o.count : ''}/${o.material && (o.material.name || o.material.type)}`; }, i);
  const a = await lum(await grab());
  await p.evaluate(i => { window.__L[i].visible = true; }, i);
  const dh = base[1] - a[1], dl = base[0] - a[0];
  if (Math.abs(dh) > 8 || Math.abs(dl) > 0.6) res.push([dh, +dl.toFixed(2), nm]);
}
res.sort((a, b) => Math.abs(b[0]) - Math.abs(a[0]));
console.log(JSON.stringify(res.slice(0, 12)));
await b.close();
