// Unlockable worlds. A world that is only a palette swap in the HUD is a lie,
// so this checks the SCENE actually changed, that a locked one refuses, and
// that travelling keeps the thing you paid with.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
p.on('console', m => { const u = (m.location() && m.location().url) || '';
  if (m.type()==='error' && !/favicon/i.test(u)) errs.push('console: '+m.text().slice(0,160)); });
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
await p.goto(URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

const look = () => p.evaluate(()=>({
  world: window.__game.facts().world,
  open: window.__game.facts().worlds_open,
  sky: '#' + window.__scene.background.getHexString(),
  cores: window.__game.facts().cores,
  machines: window.__game.facts().machines,
  value: window.__game.facts().value,
  rows: [...document.querySelectorAll('#world .wr')].map(o =>
    o.textContent + (o.classList.contains('can') ? ' [open]' : ' [locked]')),
}));

const a = await look();
console.log('start     :', a.world, '| sky', a.sky, '| open', a.open);
console.log('panel     :', a.rows.join(' · '));

// 1. a world you cannot afford refuses
const refused = await p.evaluate(async ()=>{
  const F = window.__factory;
  const before = F.worldIdx;
  F.travelTo(1);
  await new Promise(r => setTimeout(r, 300));
  return { before, after: F.worldIdx };
});
console.log('locked    : travel to Ember at 0 cores ->',
            refused.after === refused.before ? 'refused' : 'ALLOWED (wrong)');

// 2. earn the cores and it opens
await p.evaluate(()=>{ window.__factory.addValue(300); window.__factory.addCores(3); });
await new Promise(r=>setTimeout(r,400));
const armed = await look();
console.log('3 cores   : open', armed.open, '|', armed.rows.join(' · '));

// 3. travelling changes the scene and keeps the cores
await p.evaluate(()=>window.__factory.travelTo(1));
await new Promise(r=>setTimeout(r,700));
const c = await look();
console.log('travelled :', c.world, '| sky', a.sky, '->', c.sky,
            '| cores kept', c.cores, '| value reset to', c.value.toFixed(0),
            '| machines', c.machines);

// 4. and it is where you are when you come back
await p.goto(URL, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,5500));
const back = await look();
console.log('reloaded  :', back.world, '| sky', back.sky, '| cores', back.cores);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'world.png' });
await b.close();
const ok = a.world === 'prompt' && a.open === 1
  && refused.after === refused.before
  && armed.open >= 2
  && c.world === 'ember' && c.sky !== a.sky && c.cores === 3 && c.value < 5
  && back.world === 'ember' && back.sky === c.sky && back.cores === 3
  && errs.length === 0;
process.exit(ok ? 0 : 1);
