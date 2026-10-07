// A repair game played through: walks up to each broken thing, holds E
// until it comes back, and checks the count and the win. Shoots a broken
// panel up close and the same panel fixed.
//   J=job_N OUT=<dir> TAG=<name> node repairshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'repair';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await sleep(12000);
await p.click('#startbtn').catch(() => {}); await sleep(2500); await p.keyboard.press('g').catch(() => {});
const r0 = await p.evaluate(() => window.__repair ? window.__repair() : null);
if (!r0) { console.log(TAG, 'NO REPAIR SYSTEM', JSON.stringify(errs.slice(0, 3))); await b.close(); process.exit(1); }
const log = [];
for (let i = 0; i < r0.panels.length; i++) {
  const [x, z, , ry, padY] = r0.panels[i];
  const fx = Math.sin(ry || 0), fz = Math.cos(ry || 0);     // the way the panel faces
  // stand a metre out from the panel, on the side it faces (a pad on a roof: hover over it)
  if (padY !== null && padY !== undefined) await p.evaluate((x, y, z) => window.__game.tpy(x, y, z), x, padY + 1.6, z);
  else await p.evaluate((x, z) => window.__game.tp(x, z), x + fx * 1.0, z + fz * 1.0);
  await sleep(700);
  if (i === 0) {
    await p.evaluate((x, z, fx, fz, py) => { const y0 = py === null || py === undefined ? 0 : py; window.__camPin = { pos: [x + fx * 1.7 + fz * 0.7 + (py ? 2.2 : 0), y0 + (py ? 9 : 1.6), z + fz * 1.7 - fx * 0.7 + (py ? 2.2 : 0)], look: [x, y0 + (py ? 0.3 : 1.25), z] }; }, x, z, fx, fz, padY);
    await sleep(900);
    await p.screenshot({ path: `${OUT}/${TAG}_broken.jpg`, type: 'jpeg', quality: 90 });
    await p.evaluate(() => { window.__camPin = null; });
  }
  await p.keyboard.down('KeyE'); await sleep(3000); await p.keyboard.up('KeyE'); await sleep(300);
  const r = await p.evaluate(() => window.__repair());
  log.push(`${i}: fixed ${r.fixed}`);
  if (i === 0) {
    await p.evaluate((x, z, fx, fz, py) => { const y0 = py === null || py === undefined ? 0 : py; window.__camPin = { pos: [x + fx * 1.7 + fz * 0.7 + (py ? 2.2 : 0), y0 + (py ? 9 : 1.6), z + fz * 1.7 - fx * 0.7 + (py ? 2.2 : 0)], look: [x, y0 + (py ? 0.3 : 1.25), z] }; }, x, z, fx, fz, padY);
    await sleep(700);
    await p.screenshot({ path: `${OUT}/${TAG}_fixed.jpg`, type: 'jpeg', quality: 90 });
    await p.evaluate(() => { window.__camPin = null; });
  }
}
await sleep(1500);
const end = await p.evaluate(() => ({ won: !!document.querySelector('#winscreen, .win, #fswin') || /you win|mission complete/i.test(document.body.innerText), quest: window.__quest ? window.__quest() : null }));
await p.screenshot({ path: `${OUT}/${TAG}_end.jpg`, type: 'jpeg', quality: 88 });
console.log(TAG, JSON.stringify(log), JSON.stringify(end), 'errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
