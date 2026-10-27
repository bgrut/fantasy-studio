// Frames per second at a place, idle and then with a key held: J=job_N AT='expr returning [x,z]' KEY=KeyE node _fpsat.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,800', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 800 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 90000 }).catch(() => {});
await wait(4000); await p.click('#startbtn').catch(() => {});
await wait(6000);
const fps = () => p.evaluate(() => new Promise(res => { let n = 0, worst = 0, last = performance.now(); const t0 = last; const f = () => { const t = performance.now(); worst = Math.max(worst, t - last); last = t; n++; if (t - t0 < 2000) requestAnimationFrame(f); else res({ fps: +(n / ((t - t0) / 1000)).toFixed(1), worst: Math.round(worst) }); }; requestAnimationFrame(f); }));
for (let k = 0; k < +(process.env.REPS || 1); k++) console.log('spawn', k, JSON.stringify(await fps()));
if (process.env.AT) {
  const at = await p.evaluate(src => eval(src), process.env.AT);
  await p.evaluate(([x, z]) => { const a = Math.atan2(-x, -z); window.__game.tp(x + Math.sin(a) * 1.5, z + Math.cos(a) * 1.5); window.__game.face(x, z); }, at);
  await wait(2500);
  console.log('at', JSON.stringify(at), JSON.stringify(await fps()));
  if (process.env.KEY) { await p.keyboard.down(process.env.KEY); await wait(500); console.log('held', JSON.stringify(await fps()));
    for (let k = 0; k < 8; k++) { await wait(500); console.log('bar', await p.evaluate(() => JSON.stringify({ w: (document.getElementById('fsrpB') || {}).style && document.getElementById('fsrpB').style.width, t: (document.getElementById('fsrpT') || {}).textContent, left: window.__repairSpots && window.__repairSpots().length, pos: window.__game.pos().map(v => +v.toFixed(2)) }))); }
    await p.keyboard.up(process.env.KEY); }
  const prof = await p.evaluate(() => { const r = window.__renderer || null; return r ? r.info.render : null; });
  console.log('render', JSON.stringify(prof));
}
await b.close();
