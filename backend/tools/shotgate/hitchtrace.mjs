// A Chrome trace across the first sale: every event longer than 40 ms, named,
// so a stall that is not JavaScript (layout, paint, raster, GC, the GPU) shows.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const q = URL.includes('?') ? '&' : '?';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
await p.goto(URL + q + 'fresh=1&nointro=1' + (process.env.EXTRA || ''), { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 4000));
await p.tracing.start({ path: 'hitch.trace.json', categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline', 'blink', 'blink.user_timing', 'v8', 'v8.execute', 'cc', 'gpu', 'disabled-by-default-v8.gc'] });
const hit = await p.evaluate(async () => {
  let last = performance.now(), worst = 0, at = 0; const t0 = performance.now();
  await new Promise(done => { const tick = (t) => { const dt = t - last; last = t; if (dt > worst) { worst = dt; at = t - t0; performance.mark('worst-' + Math.round(dt)); } if (t - t0 < 12000) requestAnimationFrame(tick); else done(); }; requestAnimationFrame(tick); });
  return { worst: +worst.toFixed(0), at: +(at / 1000).toFixed(1), firstSale: window.__game.facts().firstSale, tags: window.__game.facts().tagsSeen };
});
await p.tracing.stop();
console.log('worst frame', hit.worst, 'ms at', hit.at, 's | first sale', hit.firstSale, '| tags seen', hit.tags);
const tr = JSON.parse(fs.readFileSync('hitch.trace.json', 'utf-8'));
const ev = (tr.traceEvents || tr).filter(e => e.dur && e.dur > 40000).sort((a, b) => b.dur - a.dur).slice(0, 25);
console.log('-- events over 40 ms --');
for (const e of ev) console.log(String((e.dur / 1000).toFixed(0)).padStart(6), 'ms', e.name.padEnd(34), (e.cat || '').slice(0, 30).padEnd(30), JSON.stringify(e.args || {}).slice(0, 160));
const marks = (tr.traceEvents || tr).filter(e => e.name && e.name.startsWith('worst-'));
console.log('-- worst-frame marks --', marks.map(m => m.name).join(' '));
await b.close();
