// How much of each face is sited (by water, over a vent), and a look at a smelter by a brook and one over a vent.
// OUT=prefix [URL=] node _siteshot.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(6000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth > 600) c.style.visibility = 'visible'; });
const r = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES, N = F.N, per = [];
  let wet = null, hot = null;
  for (let f = 0; f < 6; f++) { let q = 0, v = 0, n = 0;
    for (let i = 2; i < N - 2; i++) for (let j = 2; j < N - 2; j++) { n++; const s = F.siteOf(f, i, j); if (s === 'quench') { q++; if (!wet && f === 0 && F.cells[f][i][j].t === TY.EMPTY && Math.hypot(i - N / 2, j - N / 2) > 5) wet = { f, i, j }; } else if (s === 'vent') { v++; if (!hot && F.cells[f][i][j].t === TY.EMPTY) hot = { f, i, j }; } }
    per.push({ f, quench: +(q / n).toFixed(3), vent: +(v / n).toFixed(3) }); }
  const pins = [];
  for (const s of [wet, hot]) { if (!s) continue;
    F.place(s.f, s.i, s.j, TY.SMELTER, 0); const c = F.cells[s.f][s.i][s.j]; c.buf = 2; c.bt = TY.CRYSTAL;
    const wp = F.tileWorld(s.f, s.i, s.j), fc = F.FACES[s.f], n = fc.n, u = fc.u;
    pins.push({ site: c.site, pos: [wp[0] + n[0] * 3.2 + u[0] * 4.5, wp[1] + n[1] * 3.2 + u[1] * 4.5, wp[2] + n[2] * 3.2 + u[2] * 4.5], look: [wp[0] + n[0] * 0.6, wp[1] + n[1] * 0.6, wp[2] + n[2] * 0.6] }); }
  return { per, pins };
});
console.log(JSON.stringify(r.per));
let k = 0;
for (const pin of r.pins) {
  await p.evaluate(pn => { window.__camPin = { pos: pn.pos, look: pn.look }; for (let s = 0; s < 4; s++) window.__factory.step(); }, pin);
  await w(1400);
  await p.screenshot({ path: `${process.env.OUT}_${pin.site}.jpg`, type: 'jpeg', quality: 88 }); k++;
}
console.log('shots', k, errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
