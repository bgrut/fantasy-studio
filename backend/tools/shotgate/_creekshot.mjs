// A creek, looked at: from the bank at a crossing, and down along it. J=job_N OUT=prefix node _creekshot.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await w(500); }
await w(4000); await p.click('#startbtn').catch(() => {}); await w(7000);
const c = await p.evaluate(() => window.__creek ? window.__creek() : null);
console.log('creek', JSON.stringify(c));
const spots = (c && c.crossings.length ? c.crossings : [[0, 12]]).slice(0, 2);
let n = 0;
for (const [x, z] of spots) {
  const y = await p.evaluate((x, z) => window.__game.groundAt ? window.__game.groundAt(x, z) : 0, x, z).catch(() => 0);
  for (const [dx, dz, h] of [[5, 4, 2.2], [1.5, 9, 1.7]]) {
    await p.evaluate((pin) => { window.__camPin = pin; }, { pos: [x + dx, (y || 0) + h, z + dz], look: [x, (y || 0) - 0.2, z] });
    await w(2200);
    await p.screenshot({ path: `${process.env.OUT}_${n++}.jpg`, type: 'jpeg', quality: 88 });
  }
}
console.log(errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
