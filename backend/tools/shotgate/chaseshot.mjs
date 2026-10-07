// What the player actually sees a few seconds in: starts the game, skips the
// guide, walks (or flies) forward for a moment and shoots the chase camera.
//   J=job_N OUT=<dir> TAG=<name> [HOLD=ms] node chaseshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'chase', HOLD = +(process.env.HOLD || 1500);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await sleep(12000);
await p.click('#startbtn').catch(() => {}); await sleep(4000); await p.keyboard.press('g').catch(() => {}); await sleep(2500);
await p.keyboard.down('KeyW'); await sleep(HOLD); await p.keyboard.up('KeyW'); await sleep(900);
await p.screenshot({ path: `${OUT}/${TAG}_chase.jpg`, type: 'jpeg', quality: 90 });
const where = await p.evaluate(() => { let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
  const c = pl.position.clone().project(window.__camera); return { pos: pl.position.toArray().map(v => +v.toFixed(2)), screen: [Math.round((c.x + 1) * 700), Math.round((1 - c.y) * 400)],
    dist: +pl.position.distanceTo(window.__camera.position).toFixed(2) }; });
console.log(TAG, 'chase', JSON.stringify(where), 'errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
