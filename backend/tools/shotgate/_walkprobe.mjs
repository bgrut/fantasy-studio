// Does the hero walk? Load a job, hold W from the spawn and from a teleport,
// and print speed, position and anything holding the body.   J=job_N node _walkprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html${process.env.Q || ""}`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(4000); await p.click('#startbtn').catch(() => {}); await wait(3000);
const st = () => p.evaluate(() => { const f = window.__game.facts(); return { v: f.walk_v, pos: window.__game.pos().map(x => +x.toFixed(2)), gait: f.gait && f.gait.walk, paused: f.paused, intro: f.intro, mode: f.mode, ui: document.activeElement && document.activeElement.tagName }; });
for (const at of [null, [0, 0], [10, 10]]) {
  if (at) { await p.evaluate(a => window.__game.tp(a[0], a[1]), at); await wait(800); }
  const a = await st();
  await p.keyboard.down('KeyW'); await wait(1200); const m = await st(); await p.keyboard.up('KeyW'); await wait(400);
  console.log(JSON.stringify({ at, before: a, holding: m }));
}
console.log('errors', JSON.stringify(errs));
await b.close();
