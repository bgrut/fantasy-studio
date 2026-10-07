// A candy land's cupcakes hold a player who lands on them: drop the hero
// onto each of the first few tops and read where they come to rest.
//   J=job_N OUT=<dir> node cakeprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1200, height: 700 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000));
const cakes = await p.evaluate(() => window.__candy && window.__candy.cakes);
console.log('cakes', JSON.stringify(cakes));
const res = [];
for (const [x, z, top] of (cakes || []).slice(0, 4)) {
  await p.evaluate((x, z, top) => window.__game.tpy(x, top + 0.6, z), x, z, top);
  await new Promise(r => setTimeout(r, 1500));
  const y = await p.evaluate(() => window.__game.pos()[1]);
  res.push([top, +y.toFixed(2)]);
}
console.log('stand', JSON.stringify(res), 'errs', JSON.stringify(errs.slice(0, 3)));
if (cakes && cakes.length > 2) {
  await p.evaluate(() => { const c = window.__candy.cakes[2]; window.__camPin = { pos: [c[0] + 6, c[2] + 2.5, c[1] + 6], look: [c[0], c[2], c[1]] }; });
  await new Promise(r => setTimeout(r, 1200));
  await p.screenshot({ path: OUT + '/cake_top.jpg', type: 'jpeg', quality: 90 });
}
await b.close();
