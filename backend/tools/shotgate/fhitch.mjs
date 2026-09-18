// The warm-up: a fresh boot across the first sale and the drone's first
// flight has no frame over 120 ms, on the card, with the limit off. Before the
// warm-up the first sale and the first flight cost a 300 ms frame every time:
// the driver building a shader's executable at its first draw.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--ignore-gpu-blocklist','--disable-frame-rate-limit','--disable-gpu-vsync','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760, deviceScaleFactor: 1 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4000));
const r = await p.evaluate(async () => {
  const F = window.__factory, f0 = window.__game.facts();
  F.droneAt(23);                                   // the drone flies inside the window
  const hits = []; let last = performance.now(), n = 0, worst = 0;
  await new Promise(done => {
    const t0 = performance.now();
    const tick = (t) => { const dt = t - last; last = t; n++;
      if (n > 2 && dt > worst) worst = dt;
      if (n > 2 && dt > 60) hits.push({ at: +((t - t0) / 1000).toFixed(1), ms: +dt.toFixed(0), sfx: window.__game.facts().sfxLast });
      if (t - t0 < 30000) requestAnimationFrame(tick); else done(); };
    requestAnimationFrame(tick);
  });
  const f = window.__game.facts();
  return { warmed: f0.warmed, layers: f0.warmLayers, frames: n, worst: +worst.toFixed(0), hits, firstSale: f.firstSale, flights: f.drone && f.drone.flights };
});
console.log('warm-up   : ran', r.warmed, '| stand-in layers', r.layers);
console.log('the window: ', r.frames, 'frames in 30 s | worst', r.worst, 'ms | first sale', r.firstSale, '| drone flights', r.flights);
console.log('hitches   :', r.hits.length ? r.hits.map(h => h.ms + 'ms@' + h.at + 's(' + h.sfx + ')').join(' ') : 'none over 60 ms');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = r.warmed && r.layers === 2 && r.firstSale && r.flights >= 1 && r.worst < 120 && errs.length === 0;
if (!ok) console.log('FAIL: the warm-up');
process.exit(ok ? 0 : 1);
