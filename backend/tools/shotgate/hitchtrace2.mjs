// What fills the longest main-thread task across the first sale: the timeline
// categories only, so the tracer's own overhead does not hide the stall.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const q = URL.includes('?') ? '&' : '?';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 4000));
await p.tracing.start({ path: 'hitch2.trace.json', categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline', 'disabled-by-default-devtools.timeline.stack', 'blink.user_timing', 'disabled-by-default-v8.gc'] });
const hit = await p.evaluate(async () => {
  const F = window.__factory; F.droneAt(23);
  let last = performance.now(), worst = 0; const hits = []; const t0 = performance.now();
  await new Promise(done => { const tick = (t) => { const dt = t - last; last = t; if (dt > worst) worst = dt; if (dt > 60) hits.push(dt.toFixed(0) + '@' + ((t - t0) / 1000).toFixed(1)); if (t - t0 < 14000) requestAnimationFrame(tick); else done(); }; requestAnimationFrame(tick); });
  return { worst: +worst.toFixed(0), hits, firstSale: window.__game.facts().firstSale };
});
await p.tracing.stop();
console.log('worst frame', hit.worst, 'ms | hits', hit.hits.join(' ') || 'none', '| first sale', hit.firstSale);
const tr = JSON.parse(fs.readFileSync('hitch2.trace.json', 'utf-8'));
const ev = (tr.traceEvents || tr);
const tasks = ev.filter(e => e.name === 'RunTask' && e.dur > 60000).sort((a, b) => b.dur - a.dur).slice(0, 3);
for (const t of tasks) {
  console.log('-- task', (t.dur / 1000).toFixed(0), 'ms on pid', t.pid, 'tid', t.tid, '--');
  const inside = ev.filter(e => e.pid === t.pid && e.tid === t.tid && e.ts >= t.ts && e.ts + (e.dur || 0) <= t.ts + t.dur && e !== t && e.dur);
  const by = new Map();
  for (const e of inside) { const k = e.name + (e.args && e.args.data && e.args.data.functionName ? ' ' + e.args.data.functionName + ':' + e.args.data.lineNumber : ''); const v = by.get(k) || { n: 0, us: 0, max: 0 }; v.n++; v.us += e.dur; v.max = Math.max(v.max, e.dur); by.set(k, v); }
  for (const [k, v] of [...by.entries()].sort((a, b) => b[1].max - a[1].max).slice(0, 14)) console.log(String((v.max / 1000).toFixed(1)).padStart(8), 'ms max |', String((v.us / 1000).toFixed(1)).padStart(8), 'ms total |', v.n, 'x', k);
  const gc = inside.filter(e => /GC|Garbage/i.test(e.name)).map(e => e.name + ' ' + (e.dur / 1000).toFixed(0) + 'ms ' + JSON.stringify(e.args || {}).slice(0, 120));
  if (gc.length) console.log('   gc:', gc.slice(0, 4).join(' | '));
}
await b.close();
