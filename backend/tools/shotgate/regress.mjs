// Regression: the pure racing game and the on-foot heist must both still work.
// Usage: node regress.mjs <jobId> <label> <drive|walk>
import puppeteer from 'puppeteer-core';
import fs from 'fs';

const [JOB, LABEL, MODE] = process.argv.slice(2);
fs.mkdirSync('./shots_regress', { recursive: true });
const errs = [];
const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
});
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message.slice(0, 250)));
p.on('console', m => { const t=m.text(); if (/VALIDATE_STATUS|Info Log|shader/i.test(t)) errs.push('CONSOLE: '+t.slice(0,160)); });
const sleep = ms => new Promise(r => setTimeout(r, ms));

await p.goto(`http://127.0.0.1:8789/games/job_${JOB}/dist/`,
  { waitUntil: 'networkidle2', timeout: 90000 });
await sleep(6000);
await p.click('#startbtn').catch(() => {});
await sleep(MODE === 'drive' ? 6500 : 3000);   // race has a GO countdown

console.log(LABEL, 'alive:', await p.evaluate(() => typeof window.__game));
console.log(LABEL, 'cars:', JSON.stringify(await p.evaluate(() => window.__game.cars ? window.__game.cars() : 'n/a')));

const p0 = await p.evaluate(() => window.__game.pos());
await p.keyboard.down('KeyW');
await sleep(3500);
await p.keyboard.up('KeyW');
await sleep(400);
const p1 = await p.evaluate(() => window.__game.pos());
const moved = Math.hypot(p1[0] - p0[0], p1[2] - p0[2]);
console.log(LABEL, 'moved on W:', moved.toFixed(2), 'm', JSON.stringify(p0), '->', JSON.stringify(p1));
console.log(LABEL, 'quest:', JSON.stringify(await p.evaluate(() => window.__game.quest())));
console.log(LABEL, 'npcs:', JSON.stringify(await p.evaluate(
  () => window.__game.npcs().map(n => n.behavior + ':' + n.mode))));
await p.screenshot({ path: `./shots_regress/${LABEL}.png` });
console.log(LABEL, 'ERRORS:', errs.length ? JSON.stringify(errs) : 'none');
await b.close();
