// Who stalls the page? J=job_N [REPAIR=1] [URL=] node _stallwho.mjs
// Times every 2D-canvas readback and every shader-program link from before boot, keeping those over 40 ms with the
// stack that called them, through the opening (and, with REPAIR=1, through mending each repair spot).
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: process.env.EXE || 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: [`--use-angle=${process.env.ANGLE || 'd3d11'}`, ...(process.env.ARGS || '').split(' ').filter(Boolean), '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.evaluateOnNewDocument(() => {
  window.__st = []; window.__stClock = () => (window.__stPhase || 'boot');
  const stack = () => { const s = new Error().stack.split('\n').slice(3, 9).map(l => l.trim().replace(/^at /, '').replace(/https?:\/\/[^ )]*\//, '')); return s; };
  const wrap = (proto, name, info) => { const f = proto[name]; proto[name] = function (...a) { const t = performance.now(), r = f.apply(this, a), d = performance.now() - t; if (d > 40) window.__st.push({ phase: window.__stClock(), what: name, ms: Math.round(d), info: info ? info(this, a) : undefined, stack: stack() }); return r; }; };
  wrap(CanvasRenderingContext2D.prototype, 'getImageData', (c) => `${c.canvas.width}x${c.canvas.height} id=${c.canvas.id || ''} inDoc=${c.canvas.isConnected}`);
  for (const P of [WebGL2RenderingContext.prototype]) { wrap(P, 'getProgramInfoLog'); wrap(P, 'getProgramParameter', (c, a) => a[1]); wrap(P, 'linkProgram'); wrap(P, 'readPixels'); wrap(P, 'getShaderParameter'); wrap(P, 'texImage2D', (c, a) => { const s = a[a.length - 1] || a[5]; return s && s.width ? `${s.width}x${s.height}` : ''; }); }
  // the longest gaps between frames, with the phase they fell in
  window.__gaps = []; let last = performance.now(); const f = () => { const t = performance.now(); if (t - last > 120) window.__gaps.push({ phase: window.__stClock(), ms: Math.round(t - last), at: Math.round(t) }); last = t;
    try { const R = window.__renderer, L = R && R.info.programs; if (L && L.length !== (window.__pn || 0)) { for (let i = (window.__pn || 0); i < L.length; i++) (window.__newP = window.__newP || []).push({ phase: window.__stClock(), name: L[i].name, type: L[i].type, key: String(L[i].cacheKey).slice(0, 160) }); window.__pn = L.length; } } catch (e) {}
    requestAnimationFrame(f); }; requestAnimationFrame(f);
});
await p.goto(process.env.URL || `http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await w(500); }
await w(4000);
await p.evaluate(() => { window.__stPhase = 'start'; });
await p.click('#startbtn').catch(() => {});
await p.evaluate(() => new Promise(res => { let n = 0, last = performance.now(); const f = () => { const t = performance.now(); n = t - last < 100 ? n + 1 : 0; last = t; if (n >= 30) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); }));
await w(2500);
if (process.env.REPAIR) {
  const spots = await p.evaluate(() => window.__repairSpots ? window.__repairSpots() : []);
  for (let k = 0; k < spots.length; k++) {
    const [x, z] = spots[k];
    await p.evaluate((x, z, k) => { window.__stPhase = 'walk' + k; window.__game.tp(x + 1.0, z + 0.6); }, x, z, k); await p.keyboard.down('KeyW'); await w(300); await p.keyboard.up('KeyW'); await w(800);
    await p.evaluate((k) => { window.__stPhase = 'mend' + k; }, k);
    const left0 = (await p.evaluate(() => window.__repairSpots())).length;
    await p.keyboard.down('KeyE'); for (let i = 0; i < 100; i++) { await w(150); if ((await p.evaluate(() => window.__repairSpots().length)) < left0) break; } await p.keyboard.up('KeyE');
    await w(1500);
  }
} else await w(6000);
const r = await p.evaluate(() => ({ st: window.__st, gaps: window.__gaps, newP: (window.__newP || []).filter(q => q.phase !== 'boot') }));
console.log('new programs in play', JSON.stringify(r.newP).slice(0, 2400));
const after = r.st.filter(e => e.phase !== 'boot');
console.log('boot stalls', r.st.filter(e => e.phase === 'boot').length, 'ms', r.st.filter(e => e.phase === 'boot').reduce((a, e) => a + e.ms, 0));
console.log('gaps', JSON.stringify(r.gaps.filter(g => g.phase !== 'boot')));
for (const e of after.sort((a, b) => b.ms - a.ms).slice(0, 14)) console.log(JSON.stringify(e).slice(0, 900));
console.log('errors', errs);
await b.close();
