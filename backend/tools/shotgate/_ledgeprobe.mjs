// Ledge climb: start the game the way _walkprobe does, wait out the intro, put the hero at the
// foot of the first ledge facing up the route, hold W (+Space) and log the climb.  J=job_N node _ledgeprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(4000); await p.click('#startbtn').catch(() => {}); await wait(3000);
for (let i = 0; i < 30; i++) { const f = await p.evaluate(() => { const f = window.__game.facts(); return !f.intro && !f.paused; }); if (f) break; await wait(500); }
const g = await p.evaluate(() => window.__game.facts().level_goal || null);
const out = [];
for (const keys of [['KeyW'], ['KeyW', 'Space']]) {
  await p.evaluate(() => window.__game.tp(3.9, 3.1)); await wait(900);
  for (const k of keys) await p.keyboard.down(k);
  const pts = [];
  for (let t = 0; t < 14; t++) { await wait(500); pts.push((await p.evaluate(() => window.__game.pos())).map(v => +v.toFixed(1)).join(',')); }
  for (const k of keys) await p.keyboard.up(k);
  out.push(keys.join('+') + ': ' + pts.join(' | '));
}
console.log(out.join('\n'), errs.length ? 'ERR ' + errs[0] : '');
await b.close();
