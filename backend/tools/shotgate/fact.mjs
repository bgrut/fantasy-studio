// Does a factory the STUDIO generated actually play? Same harness shape as the
// adventure gates: load it, let it run, and read the numbers off the running
// game rather than off the source.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
// a missing favicon is not a game defect
p.on('console', m => { const t = m.text();
  // the message text is generic ("Failed to load resource"); the URL is in
  // location(), which is where the favicon has to be filtered
  const u = (m.location() && m.location().url) || '';
  if (m.type()==='error' && !/favicon/i.test(u)) errs.push('console: '+t.slice(0,200)); });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/',
  { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

const t0 = await p.evaluate(()=> window.__game ? window.__game.facts() : null);
if (!t0) { console.log('FAIL: no window.__game'); console.log(errs.join('\n')); await b.close(); process.exit(1); }
console.log('facts @6s :', JSON.stringify(t0));

// let the starter line actually produce
await new Promise(r=>setTimeout(r,12000));
const t1 = await p.evaluate(()=> window.__game.facts());
console.log('facts @18s:', JSON.stringify(t1));
const st = await p.evaluate(()=> window.__game.stats());
console.log('render    :', JSON.stringify(st));

// SHOOT BEFORE WALKING (2026-09-07). The walk test pushes the player 7.5m
// forward, which is exactly onto the starter line — the "bug" in the first
// screenshot was a smelter at point-blank range.
await p.screenshot({ path: process.env.OUT || 'factory.png' });

// the player is a first-person camera: can it walk?
const a = await p.evaluate(()=> window.__game.pos());
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,1200)); await p.keyboard.up('KeyW');
await new Promise(r=>setTimeout(r,300));
const c = await p.evaluate(()=> window.__game.pos());
console.log('walked    :', Math.hypot(c[0]-a[0], c[2]-a[2]).toFixed(2)+'m');

console.log('produced  :', t1.value - t0.value, 'value in 12s |', 'ingots', t1.ingots);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
process.exit(errs.length || (t1.value <= t0.value) ? 1 : 0);
