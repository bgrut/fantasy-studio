// The CPU profile across the first sale: which functions own the stall.
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const q = URL.includes('?') ? '&' : '?';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
await p.goto(URL + q + 'fresh=1&nointro=1' + (process.env.EXTRA || ''), { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 4000));
const cdp = await p.createCDPSession();
await cdp.send('Profiler.enable');
await cdp.send('Profiler.setSamplingInterval', { interval: 200 });
await cdp.send('Profiler.start');
const t0 = Date.now();
const hit = await p.evaluate(async () => {
  let last = performance.now(), worst = 0, at = 0; const t0 = performance.now();
  await new Promise(done => { const tick = (t) => { const dt = t - last; last = t; if (dt > worst) { worst = dt; at = t - t0; } if (t - t0 < 14000) requestAnimationFrame(tick); else done(); }; requestAnimationFrame(tick); });
  return { worst: +worst.toFixed(0), at: +(at / 1000).toFixed(1), firstSale: window.__game.facts().firstSale };
});
const { profile } = await cdp.send('Profiler.stop');
console.log('worst frame', hit.worst, 'ms at', hit.at, 's | first sale', hit.firstSale);
// self time per node, from the sample stream
const self = new Map(), byId = new Map();
for (const n of profile.nodes) byId.set(n.id, n);
const dt = profile.timeDeltas;
for (let k = 0; k < profile.samples.length; k++) { const id = profile.samples[k]; self.set(id, (self.get(id) || 0) + (dt[k] || 0)); }
// total time including children, by walking parents
const parent = new Map();
for (const n of profile.nodes) for (const c of (n.children || [])) parent.set(c, n.id);
const total = new Map();
for (const [id, us] of self) { let cur = id; const seen = new Set(); while (cur !== undefined && !seen.has(cur)) { seen.add(cur); total.set(cur, (total.get(cur) || 0) + us); cur = parent.get(cur); } }
const name = n => (n.callFrame.functionName || '(anon)') + ' ' + (n.callFrame.url || '').split('/').pop() + ':' + n.callFrame.lineNumber;
const rows = [...total.entries()].map(([id, us]) => ({ id, us, s: self.get(id) || 0 })).sort((a, b) => b.us - a.us);
console.log('-- heaviest by total time (ms), with self time --');
let shown = 0;
for (const r of rows) { const n = byId.get(r.id); if (/^\((root|program|idle|garbage)/.test(n.callFrame.functionName)) continue; console.log(String((r.us / 1000).toFixed(1)).padStart(8), String((r.s / 1000).toFixed(1)).padStart(8), name(n)); if (++shown >= 28) break; }
await b.close();
