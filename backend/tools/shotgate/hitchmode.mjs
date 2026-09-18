// The same first-sale window in headless and in headed Chrome, with a long-task
// observer in the page: a stall the observer sees is main-thread work; one it
// does not see is the compositor or the frame scheduler.
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const q = URL.includes('?') ? '&' : '?';
const run = async (label, headless) => {
  const b = await puppeteer.launch({ headless, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760', '--window-position=100,100'] });
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
  await p.evaluateOnNewDocument(() => { window.__long = []; try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__long.push({ at: e.startTime, ms: Math.round(e.duration), who: (e.attribution || []).map(a => a.containerType + ':' + (a.containerName || a.containerSrc || '')).join(',') }); }).observe({ entryTypes: ['longtask'] }); } catch (e) {} });
  await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await new Promise(r => setTimeout(r, 4000));
  const out = await p.evaluate(async () => {
    const F = window.__factory; F.droneAt(23); const hits = []; let last = performance.now(), n = 0; const t0 = performance.now();
    await new Promise(done => { const tick = (t) => { const dt = t - last; last = t; n++; if (n > 2 && dt > 60) hits.push(dt.toFixed(0) + 'ms@' + ((t - t0) / 1000).toFixed(1) + 's(' + window.__game.facts().sfxLast + ')'); if (t - t0 < 20000) requestAnimationFrame(tick); else done(); }; requestAnimationFrame(tick); });
    return { hits, long: window.__long.filter(l => l.at > t0 - 100).map(l => l.ms + 'ms@' + ((l.at - t0) / 1000).toFixed(1) + 's[' + l.who + ']'), firstSale: window.__game.facts().firstSale };
  });
  console.log(label.padEnd(9), '| hitches', out.hits.join(' ') || 'none', '| long tasks', out.long.join(' ') || 'none', '| first sale', out.firstSale);
  await b.close();
};
await run('headless', 'new');
await run('headed', false);
