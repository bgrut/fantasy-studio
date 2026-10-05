// The player's car up close from a pinned camera: three-quarter front, side,
// and three-quarter rear, after the countdown.   J=job_N OUT=<dir> TAG=<name> node carclose.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'car';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 10000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 7000));
for (const [name, ang, d, h] of [['front', 0.75, 4.4, 1.1], ['side', 1.57, 5.2, 1.0], ['rear', 2.5, 4.4, 1.2]]) {
  await p.evaluate((ang, d, h) => {
    const g = window.__game, pp = g.pos(), y = g.heading();
    const fx = -Math.sin(y), fz = -Math.cos(y);                  // the way the car faces
    const ca = Math.cos(ang), sa = Math.sin(ang);
    const dx = fx * ca - fz * sa, dz = fx * sa + fz * ca;
    window.__camPin = { pos: [pp[0] + dx * d, pp[1] + h, pp[2] + dz * d], look: [pp[0], pp[1] + 0.45, pp[2]] };
  }, ang, d, h);
  await new Promise(r => setTimeout(r, 900));
  await p.screenshot({ path: `${OUT}/${TAG}_${name}.jpg`, type: 'jpeg', quality: 92 });
}
console.log(TAG, JSON.stringify(errs.slice(0, 3)));
await b.close();
