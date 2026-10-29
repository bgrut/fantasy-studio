// Why the first-sale frame froze: fhitch's run under a Chrome trace, then
// every slice over 100 ms named with its thread and the slices inside it.
// J=<job> or URL=; RUNS=n; stops at the first run with a hitch
import puppeteer from 'puppeteer-core';
import fs from 'fs';
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const RUNS = +(process.env.RUNS || 3);
const CATS = ['toplevel', 'gpu', 'skia', 'disabled-by-default-skia.shaders', 'disabled-by-default-gpu.service', 'devtools.timeline', 'viz'];
for (let run = 0; run < RUNS; run++) {
  const b = await puppeteer.launch({ headless: 'new',
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
  const p = await b.newPage();
  await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
  const q = URL.includes('?') ? '&' : '?';
  const path = (process.env.TMP || '.') + '/_hitch_' + run + '.json';
  await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await new Promise(r => setTimeout(r, 4000));
  await p.tracing.start({ path, categories: CATS });
  const r = await p.evaluate(async () => {
    window.__factory.droneAt(23);
    const hits = []; let last = performance.now(), n = 0;
    await new Promise(done => {
      const t0 = performance.now();
      const tick = (t) => { const dt = t - last; last = t; n++;
        if (n > 2 && dt > 60) hits.push({ at: +((t - t0) / 1000).toFixed(2), ms: +dt.toFixed(0), sfx: window.__game.facts().sfxLast, tags: [...document.querySelectorAll('#tags b')].map(e => e.className).join(','), toast: (document.getElementById('toast') || {}).className });
        if (t - t0 < 14000) requestAnimationFrame(tick); else done(); };
      requestAnimationFrame(tick);
    });
    return hits;
  });
  await p.tracing.stop();
  await b.close();
  console.log('run', run, 'hitches', JSON.stringify(r));
  if (!r.length) { fs.unlinkSync(path); continue; }
  const T = JSON.parse(fs.readFileSync(path, 'utf8'));
  const ev = T.traceEvents || T;
  const tn = {};
  for (const e of ev) if (e.ph === 'M' && e.name === 'thread_name') tn[e.pid + ':' + e.tid] = e.args.name;
  const long = ev.filter(e => e.ph === 'X' && e.dur > 100000).sort((a, b) => a.ts - b.ts);
  for (const e of long) {
    const inner = ev.filter(x => x.ph === 'X' && x.pid === e.pid && x.tid === e.tid && x.ts >= e.ts && x.ts + x.dur <= e.ts + e.dur && x !== e && x.dur > 20000)
      .map(x => x.name + ' ' + (x.dur / 1000).toFixed(0));
    console.log(`  ${(e.dur / 1000).toFixed(0)} ms ${e.name} [${tn[e.pid + ':' + e.tid] || e.tid}] ${JSON.stringify(e.args || {}).slice(0, 160)}`);
    if (inner.length) console.log('     inside: ' + [...new Set(inner)].slice(0, 12).join(' | '));
  }
  break;
}
