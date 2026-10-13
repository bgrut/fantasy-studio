// the opening of a job, in four frames: J=job_N OUT=prefix node _open.mjs
//   _a the start screen, _b the chapter reveal, _c the narrator's card and the first line, _d the goal
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000);
const O = process.env.OUT;
await p.screenshot({ path: O + '_a.jpg', type: 'jpeg', quality: 85 });
await p.click('#startbtn').catch(() => {});
await wait(1800); await p.screenshot({ path: O + '_b.jpg', type: 'jpeg', quality: 85 });
await wait(3600); await p.screenshot({ path: O + '_c.jpg', type: 'jpeg', quality: 85 });
const info = await p.evaluate(() => ({ art: window.__art, mark: window.__goalMark, story: !!window.__story }));
await p.evaluate(() => { const g = window.__spec.world.level.goal, y = window.__game.pos()[1];
  window.__camPin = { pos: [g[0] + 6, y + 2.6, g[1] + 6], look: [g[0], y + 1.2, g[1]] }; }).catch(() => {});
await wait(2500); await p.screenshot({ path: O + '_d.jpg', type: 'jpeg', quality: 85 });
console.log(JSON.stringify(info), errs.length ? 'ERR ' + errs.join(' | ') : '');
await b.close();
