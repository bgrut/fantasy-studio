// Which frames stall in the first minute, and what the world was doing when
// they did. On the real card with the limit off, a frame over 30 ms is a hitch.
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const q = URL.includes('?') ? '&' : '?';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
await p.goto(URL + q + 'fresh=1&nointro=1' + (process.env.EXTRA || ''), { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 4000));
const out = await p.evaluate(async (secs) => {
  const hits = []; let last = performance.now(), n = 0;
  const F = window.__factory;
  if (F.droneAt) F.droneAt(F.DRONE ? F.DRONE.rest - 3 : 23);   // the drone flies early, inside the window
  await new Promise(done => {
    const t0 = performance.now();
    const tick = (t) => {
      const dt = t - last; last = t; n++;
      if (dt > 30 && n > 2) {
        const f = window.__game.facts();
        hits.push({ at: +((t - t0) / 1000).toFixed(1), ms: +dt.toFixed(0), drone: f.drone, firstSale: f.firstSale, tags: f.tagsLive, idle: f.idleNudges, hint: f.hintGone, sfx: f.sfxLast, calls: window.__game.stats().calls, programs: window.__game.stats().programs });
      }
      if (t - t0 < secs * 1000) requestAnimationFrame(tick); else done();
    };
    requestAnimationFrame(tick);
  });
  return { frames: n, hits, programs: window.__game.stats().programs };
}, +(process.env.SECS || 50));
console.log('frames', out.frames, '| programs at end', out.programs);
for (const h of out.hits) console.log(JSON.stringify(h));
await b.close();
