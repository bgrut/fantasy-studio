// The walk in the factory: the body eases up to speed and down, a sprint
// widens the view. Both targets.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 6000));
await p.evaluate(() => { document.getElementById('tutor')?.classList.remove('on'); window.__factory.ageHints(); });
const wait = ms => new Promise(r => setTimeout(r, ms));
const F = () => p.evaluate(() => { const f = window.__game.facts(); return { v: f.moveVel, sprint: f.sprintK, fov: f.fov, base: f.fovBase }; });
const rest = await F();
await p.keyboard.down('KeyW'); await wait(50); const early = await F(); await wait(450); const full = await F();
await p.keyboard.up('KeyW'); await wait(60); const easing = await F(); await wait(500); const stopped = await F();
await p.keyboard.down('ShiftLeft'); await p.keyboard.down('KeyW'); await wait(1400); const sprint = await F();
await p.keyboard.up('KeyW'); await p.keyboard.up('ShiftLeft'); await wait(1200); const settled = await F();
console.log('the walk  : rest', rest.v, '| 50 ms in', early.v, '| 500 ms in', full.v, '| 60 ms after release', easing.v, '| stopped', stopped.v);
console.log('the sprint: fov', sprint.fov, 'of', sprint.base, '(k ' + sprint.sprint + ') | settled', settled.fov);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = rest.v === 0 && early.v > 0.3 && early.v < 5.0 && full.v > 5.8 && easing.v > 0.2 && easing.v < full.v && stopped.v < 0.05
  && sprint.fov > sprint.base + 3 && Math.abs(settled.fov - settled.base) < 0.6
  && errs.length === 0;
if (!ok) console.log('FAIL: the walk');
process.exit(ok ? 0 : 1);
