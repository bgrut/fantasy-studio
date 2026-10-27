// Fell the marked trees: stand at one, hold E, shoot the chips flying, the fall, the crash; then look at
// the sled and the mill. J=job_N OUT=prefix [N=2] node _chopwalk.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,800', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
p.on('console', m => { if (m.type() === 'error' || /chop|sled|mill/i.test(m.text())) errs.push('console: ' + m.text().slice(0, 160)); });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 90000 }).catch(() => {});
await wait(4000); await p.click('#startbtn').catch(() => {});
await p.waitForFunction(() => window.__game && !(window.__game.facts && window.__game.facts().intro), { timeout: 30000 }).catch(() => {});
await wait(3000);
const spots = await p.evaluate(() => window.__repairSpots ? window.__repairSpots() : []);
const N = +(process.env.N || 2), out = [];
for (let i = 0; i < Math.min(N, spots.length); i++) {
  const [tx, tz] = spots[i];
  await p.evaluate((tx, tz) => { const a = Math.atan2(-tx, -tz), x = tx + Math.sin(a) * 1.5, z = tz + Math.cos(a) * 1.5; window.__game.tp(x, z); window.__game.face(tx, tz);
    window.__camPin = { pos: [x + Math.sin(a + 1.9) * 7, window.__game.pos()[1] + 3.2, z + Math.cos(a + 1.9) * 7], look: [tx, window.__game.pos()[1] + 2.5, tz] }; }, tx, tz);
  await wait(900);
  // the camera over the lumberjack's shoulder, high, looking down the line the tree will fall along
  await p.evaluate((tx, tz) => { const q = window.__game.pos(), fx = tx - q[0], fz = tz - q[2], L = Math.hypot(fx, fz) || 1, ux = fx / L, uz = fz / L;
    window.__camPin = { pos: [q[0] - ux * 4.5 - uz * 3.5, q[1] + 5.5, q[2] - uz * 4.5 + ux * 3.5], look: [tx + ux * 5, q[1] + 1.5, tz + uz * 5] }; }, tx, tz);
  const n0 = await p.evaluate(() => window.__repairSpots().length);
  await p.keyboard.down('KeyE');
  let shot = false, t0 = Date.now();
  while (Date.now() - t0 < 20000) { await wait(200);
    const n = await p.evaluate(() => window.__repairSpots().length);
    if (!shot && Date.now() - t0 > 900) { await p.screenshot({ path: `${process.env.OUT}_${i}a.jpg`, type: 'jpeg', quality: 86 }); shot = true; }
    if (n < n0) break; }
  await p.keyboard.up('KeyE');
  const held = Date.now() - t0;
  await wait(350); await p.screenshot({ path: `${process.env.OUT}_${i}b.jpg`, type: 'jpeg', quality: 86 });
  await wait(700); await p.screenshot({ path: `${process.env.OUT}_${i}c.jpg`, type: 'jpeg', quality: 86 });
  await wait(1600); await p.screenshot({ path: `${process.env.OUT}_${i}d.jpg`, type: 'jpeg', quality: 86 });
  console.log('held ms', held);
  await wait(1500);
  out.push(await p.evaluate(() => ({ sled: window.__sled && window.__sled(), mill: window.__mill && window.__mill(), left: (window.__game.objectives().left || []).length })));
}
// the sled behind the lumberjack, then the mill
await p.evaluate(() => { const q = window.__game.pos(), y = window.__heroYaw || 0; window.__camPin = { pos: [q[0] + Math.sin(y + 2.4) * 6, q[1] + 2.6, q[2] + Math.cos(y + 2.4) * 6], look: [q[0] - Math.sin(y) * 1.5, q[1] + 0.6, q[2] - Math.cos(y) * 1.5] }; });
await wait(900); await p.screenshot({ path: `${process.env.OUT}_sled.jpg`, type: 'jpeg', quality: 86 });
const g = await p.evaluate(() => window.__game.facts ? null : null);
console.log(JSON.stringify(out), errs.length ? 'ERR ' + errs.slice(0, 6).join(' | ') : 'no errors');
await b.close();
