// Steady-state fps, measured well after load so the one-time facade-relief
// generation cannot be mistaken for a running cost. Also times that generation.
import puppeteer from 'puppeteer-core';
const job = process.argv[2];
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 200)));
// longest task observed during startup ~= the worst single-frame hitch
await p.evaluateOnNewDocument(() => {
  window.__longTasks = [];
  try { new PerformanceObserver(l => { for (const e of l.getEntries())
    window.__longTasks.push(Math.round(e.duration)); }).observe({ entryTypes: ['longtask'] }); } catch (e) {}
});
await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 20000));           // let everything settle
await p.evaluate(() => window.__game.tp(117.7, -65.1));
await new Promise(r => setTimeout(r, 3000));
if (!process.env.NOAIM) await p.evaluate(() => { if (window.__game.aim) window.__game.aim(1.15, 0.22); });
await new Promise(r => setTimeout(r, 2000));
for (let i = 0; i < 3; i++) {
  const m = await p.evaluate(() => new Promise(res => {
    let n = 0; const t0 = performance.now();
    const tick = () => { n++; if (performance.now() - t0 < 5000) requestAnimationFrame(tick);
      else res({ fps: n / ((performance.now() - t0) / 1000), calls: window.__game.stats().calls }); };
    requestAnimationFrame(tick); }));
  console.log(`steady[${i}] fps=${m.fps.toFixed(1)} calls=${m.calls}`);
}
const lt = await p.evaluate(() => window.__longTasks.slice().sort((a, c) => c - a).slice(0, 5));
console.log('longest main-thread tasks during the whole session (ms):', JSON.stringify(lt));
await b.close();
