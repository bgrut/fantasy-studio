// Does a factory survive closing the tab? Build something distinctive, reload
// the page for real, and check it came back — a save tested by calling
// saveState() and reading it back would not prove the boot path restores it.
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
// ?fresh=1: this run must not grade the previous run's factory
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'fresh=1',
  { waitUntil:'domcontentloaded', timeout:90000 });
await p.evaluate(()=>{ try { localStorage.clear(); } catch (e) {} });
await p.reload({ waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,6000));

const firstBoot = await p.evaluate(()=>window.__game.facts().restored);
console.log('first boot :', 'restored =', firstBoot, '(should be false)');

// build something that could not be there by accident, and bank some value
const built = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let spot = null;
  for (let i = 6; i < F.N - 6 && !spot; i++)
    for (let j = 6; j < F.N - 6 && !spot; j++)
      if (F.cells[0][i][j].t === TY.EMPTY) spot = [i, j];
  F.place(0, spot[0], spot[1], TY.FORGE, 2);
  const f2 = F.stepTile(0, spot[0], spot[1], 1);
  F.place(f2.face, f2.i, f2.j, TY.FILTER, f2.d);
  F.cells[f2.face][f2.i][f2.j].filt = TY.SALT;
  F.addValue(500);
  F.buy('yield');                                   // and spend some of it
  F.save();
  const f = window.__game.facts();
  return { spot, filterAt: [f2.face, f2.i, f2.j], machines: f.machines,
           value: f.value, yieldLvl: F.UPGRADES.yield.lvl };
});
console.log('built      :', 'forge at', built.spot, '| filter set to salt |',
            'machines', built.machines, '| yield lvl', built.yieldLvl);

// a REAL reload with NO fresh flag — the path a returning player takes
await p.goto(URL, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,6000));
const back = await p.evaluate((b2) => {
  const F = window.__factory, TY = F.TYPES;
  const f = window.__game.facts();
  return { restored: f.restored, machines: f.machines, value: f.value,
           yieldLvl: F.UPGRADES.yield.lvl,
           forge: F.cells[0][b2.spot[0]][b2.spot[1]].t === TY.FORGE,
           filt: F.cells[b2.filterAt[0]][b2.filterAt[1]][b2.filterAt[2]].filt === TY.SALT };
}, built);
console.log('after reload:', JSON.stringify(back));

// and "new world" really does clear it
await p.evaluate(()=>window.__factory.wipe());
await new Promise(r=>setTimeout(r,300));
const wiped = await p.evaluate(()=>window.__game.facts());
console.log('wiped      : machines', wiped.machines, '| value', wiped.value);
console.log('errors     :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = firstBoot === false && back.restored === true && back.forge && back.filt
  && back.machines === built.machines
  // not equality: the factory keeps earning between save() and the reload,
  // so the property is that the banked value SURVIVED, not that it froze
  && back.value > built.value * 0.9
  && back.yieldLvl === built.yieldLvl
  && wiped.machines <= 7 && wiped.value === 0
  && errs.length === 0;
process.exit(ok ? 0 : 1);
