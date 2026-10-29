// The forge played through: stand at the anvil, hold E through every heat, report the progress and the win.
// J=job [HOLD=ms] node _forgeplay.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J || 10005;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
const w = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 120000 }).catch(() => {});
await w(5000); await p.click('#startbtn').catch(() => {});
await p.waitForFunction(() => window.__forge, { timeout: 60000 }).catch(() => {});
await w(3000);
await p.evaluate(() => { const s = window.__smithy, f = window.__forge; window.__game.tp3(f.x + Math.sin(s.ry) * 1.2, f.y, f.z + Math.cos(s.ry) * 1.2); });
await w(800);
const rd = () => p.evaluate(() => {
  const t = document.getElementById('fsrpT'), tx = document.body.innerText;
  const m = tx.match(/(barrel.{0,60}|won.{0,40}|victory.{0,40}|complete.{0,40})/i);
  return { hint: t && t.textContent, rp: window.__rpP, end: m ? m[0] : null };
});
console.log('start', JSON.stringify(await rd()));
for (let k = 0; k < 4; k++) {
  await p.keyboard.down('KeyE'); await w(+(process.env.HOLD || 6000)); await p.keyboard.up('KeyE'); await w(700);
  console.log('after heat', k + 1, JSON.stringify(await rd()));
}
console.log('errs', JSON.stringify(errs));
await b.close();
