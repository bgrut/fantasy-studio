// A plant-water-harvest game played through: stands at each sprout, holds E
// to water it, waits for it to grow, walks over it to pull it, and reports
// the step's count; shoots the beds as sprouts and again grown.
//   J=job_N OUT=<dir> TAG=<name> node growshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'grow';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await sleep(12000);
await p.click('#startbtn').catch(() => {}); await sleep(3000); await p.keyboard.press('g').catch(() => {});
const g0 = await p.evaluate(() => window.__grow ? window.__grow() : null);
if (!g0) { console.log(TAG, 'NO GROW SYSTEM', JSON.stringify(errs.slice(0, 3))); await b.close(); process.exit(1); }
const pin = async (file) => { await p.evaluate(() => { window.__camPin = { pos: [7, 6, -5], look: [0, 0.3, 5] }; }); await sleep(1200);
  await p.screenshot({ path: `${OUT}/${TAG}_${file}.jpg`, type: 'jpeg', quality: 90 }); await p.evaluate(() => { window.__camPin = null; }); };
await pin('sprouts');
const log = [];
for (const [x, z] of g0.spots) {
  // stand on the path side of the sprout, a little off it
  await p.evaluate((x, z) => window.__game.tp(x + (x > 0 ? -1.1 : 1.1), z), x, z);
  await sleep(500);
  await p.keyboard.down('KeyE'); await sleep(1400); await p.keyboard.up('KeyE');
}
await sleep(3200);                                   // the last ones finish growing
await pin('grown');
const g1 = await p.evaluate(() => window.__grow());
// one grown crop up close, the HUD out of the way
if (g1.grown && g1.grown.length) { const [x, y, z] = g1.grown[g1.grown.length - 1];
  await p.evaluate(() => { for (const el of document.body.children) if (el.tagName !== 'CANVAS' && !el.querySelector('canvas')) el.style.visibility = 'hidden'; });
  await p.evaluate((x, y, z) => { window.__camPin = { pos: [x + 1.3, y + 1.1, z + 1.5], look: [x, y + 0.3, z] }; }, x, y, z); await sleep(1200);
  await p.screenshot({ path: `${OUT}/${TAG}_close.jpg`, type: 'jpeg', quality: 90 });
  await p.evaluate(() => { window.__camPin = null; for (const el of document.body.children) el.style.visibility = ''; }); }
// a sprout the walk-by missed gets a second try from right on top of it
for (const [x, z] of g1.spots) { await p.evaluate((x, z) => window.__game.tp(x, z), x, z); await sleep(400);
  await p.keyboard.down('KeyE'); await sleep(1400); await p.keyboard.up('KeyE'); }
if (g1.spots.length) { await sleep(3000); }
if (g1.spots.length) console.log(TAG, 'missed on the walk-by', JSON.stringify(g1.spots), 'after a second try', JSON.stringify((await p.evaluate(() => window.__grow())).spots));
for (const [x, z] of g0.spots) { await p.evaluate((x, z) => window.__game.tp(x, z), x, z); await sleep(350); }
await sleep(1200);
const q = await p.evaluate(() => { const t = document.body.innerText; const m = t.match(/(\d+)\/(\d+)/); return { counter: m ? m[0] : null, won: !!(m && m[1] === m[2]) || /you win|mission complete/i.test(t.slice(0, 3000)) }; });
console.log(TAG, JSON.stringify({ sprouts: g0.sprouts, locked0: g0.locked, wateredAfter: g1.watered, lockedAfter: g1.locked }), JSON.stringify(q), 'errors', JSON.stringify(errs.slice(0, 3)));
await p.screenshot({ path: `${OUT}/${TAG}_end.jpg`, type: 'jpeg', quality: 88 });
await b.close();
