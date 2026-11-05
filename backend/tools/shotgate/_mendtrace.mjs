// What freezes the game when a repair finishes? J=job_N [OUT=trace.json] node _mendtrace.mjs
// Mends each spot in turn with the JS profiler and a Chrome trace running, prints each mend's worst frame gap,
// the JS that took the time, and the longest GPU-process events.
import puppeteer from 'puppeteer-core'; import fs from 'fs';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await w(500); }
await w(4000); await p.click('#startbtn').catch(() => {});
await p.evaluate(() => new Promise(res => { let n = 0, last = performance.now(); const f = () => { const t = performance.now(); n = t - last < 100 ? n + 1 : 0; last = t; if (n >= 30) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); }));
await w(1500);
await p.evaluate(() => { window.__gap = { last: performance.now(), worst: 0, at: 0 }; const f = () => { const t = performance.now(), g = window.__gap; if (t - g.last > g.worst) { g.worst = t - g.last; g.at = t; } g.last = t; requestAnimationFrame(f); }; requestAnimationFrame(f); });
const cdp = await p.createCDPSession();
const spots = await p.evaluate(() => window.__repairSpots());
const out = [];
for (let k = 0; k < spots.length; k++) {
  const [x, z] = spots[k];
  await p.evaluate((x, z) => window.__game.tp(x + 1.0, z + 0.6), x, z); await p.keyboard.down('KeyW'); await w(300); await p.keyboard.up('KeyW'); await w(600);
  await p.evaluate(() => { window.__gap.worst = 0; });
  await cdp.send('Profiler.enable'); await cdp.send('Profiler.setSamplingInterval', { interval: 2000 }); await cdp.send('Profiler.start');
  let tr = null;
  if (k === 0) await p.tracing.start({ categories: ['gpu', 'disabled-by-default-gpu.service', 'toplevel', 'v8', 'blink', 'devtools.timeline', 'cc'], path: process.env.OUT || undefined });
  const left0 = (await p.evaluate(() => window.__repairSpots())).length;
  await p.keyboard.down('KeyE');
  let done = false; for (let i = 0; i < 100; i++) { await w(150); if ((await p.evaluate(() => window.__repairSpots().length)) < left0) { done = true; break; } }
  await p.keyboard.up('KeyE');
  await w(1200);
  const worst = await p.evaluate(() => Math.round(window.__gap.worst));
  const { profile } = await cdp.send('Profiler.stop');
  if (k === 0) await p.tracing.stop();
  // self time by function
  const self = new Map(), byId = new Map(profile.nodes.map(n => [n.id, n]));
  for (let i = 0; i < profile.samples.length; i++) { const n = byId.get(profile.samples[i]), dt = (profile.timeDeltas[i] || 0) / 1000, cf = n.callFrame, key = `${cf.functionName || '(anon)'}:${cf.lineNumber}`; self.set(key, (self.get(key) || 0) + dt); }
  const top = [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k2, v]) => [k2, Math.round(v)]);
  out.push({ k, done, worstMs: worst, top });
  console.log(JSON.stringify(out[out.length - 1]));
}
if (process.env.OUT) {
  const t = JSON.parse(fs.readFileSync(process.env.OUT, 'utf8')), ev = t.traceEvents || t;
  const names = new Map(); for (const e of ev) if (e.ph === 'M' && e.name === 'thread_name') names.set(e.pid + ':' + e.tid, e.args.name);
  const long = ev.filter(e => e.ph === 'X' && e.dur > 150000).sort((a, b) => b.dur - a.dur).slice(0, 18).map(e => [names.get(e.pid + ':' + e.tid) || e.tid, e.name, Math.round(e.dur / 1000), JSON.stringify(e.args || {}).slice(0, 120)]);
  console.log(JSON.stringify(long));
}
await b.close();
