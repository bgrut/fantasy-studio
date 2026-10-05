// Scenery up close: the nearest tree trunk and the nearest rock or boulder to
// the hero, each from a couple of metres, in the level's own light.
//   J=job_N OUT=<dir> TAG=<name> node natureshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 11000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1000));
const picks = await p.evaluate(() => {
  const f = window.__flora || {}, near = f.near || [], pp = window.__game.pos();
  const by = (test) => near.filter(c => test(c[4])).sort((a, b) => Math.hypot(a[0] - pp[0], a[2] - pp[2]) - Math.hypot(b[0] - pp[0], b[2] - pp[2]))[0] || null;
  return { tree: by(k => !['rock', 'boulder', 'mesa', 'crystal', 'bush'].includes(k)), rock: by(k => ['rock', 'boulder'].includes(k)), kinds: f.kinds };
});
console.log(TAG, JSON.stringify(picks));
for (const [name, c, d, h, lh] of [['trunk', picks.tree, 5.2, 1.5, 1.6], ['rock', picks.rock, 2.6, 1.4, 0.5]]) {
  if (!c) continue;
  await p.evaluate((c, d, h, lh) => {
    const pp = window.__game.pos(), ax = pp[0] - c[0], az = pp[2] - c[2], l = Math.hypot(ax, az) || 1;
    // from the hero's side of it, so the light is the light the player sees
    window.__camPin = { pos: [c[0] + ax / l * d * c[3] ** 0.5, c[1] + h, c[2] + az / l * d * c[3] ** 0.5], look: [c[0], c[1] + lh * c[3] ** 0.5, c[2]] };
  }, c, d, h, lh);
  await new Promise(r => setTimeout(r, 900));
  await p.screenshot({ path: `${OUT}/${TAG}_${name}.jpg`, type: 'jpeg', quality: 92 });
}
console.log('errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
