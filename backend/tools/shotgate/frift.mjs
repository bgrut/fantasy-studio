// The Chronos rift: it lends, it is repaid, and when it is not it takes the
// factory. All three have to be checked — a rift that only ever pays out is a
// free ore dispenser, and a storm nobody can trigger is a threat that is not
// really there.
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
await p.goto(URL, { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

// 1. a rift wired to a belt opens and pays its loan out onto it
const lend = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const free = (a,bb) => F.cells[0][a][bb].t === TY.EMPTY;
  for (let i = 5; i < F.N - 5; i++) for (let j = 5; j < F.N - 5; j++) {
    const out = F.stepTile(0, i, j, 0), beyond = F.stepTile(out.face, out.i, out.j, out.d);
    const back = F.stepTile(0, i, j, 2);
    if (![[i,j],[out.i,out.j],[beyond.i,beyond.j],[back.i,back.j]].every(([a,bb]) => free(a,bb)))
      continue;
    F.place(0, i, j, TY.RIFT, 0);
    F.place(out.face, out.i, out.j, TY.BELT, out.d);   // catches the loan
    F.place(back.face, back.i, back.j, TY.BELT, 0);    // points back INTO the rift
    await new Promise(r => setTimeout(r, 1800));
    const f = window.__game.facts().rift;
    return { at: [i,j], back: [back.face, back.i, back.j], rift: f,
             onBelt: F.cells[out.face][out.i][out.j].item };
  }
  return { skipped: true };
});
console.log('rift opens :', JSON.stringify(lend.rift), '| loan on belt:', lend.onBelt);

// 2. feed the debt back through the ring and it settles, paying out
const repay = await p.evaluate(async (back) => {
  const F = window.__factory;
  const before = window.__game.facts();
  const owed = before.rift.debt, ore = before.rift.ore;
  const MIN = { crystal: F.TYPES.CRYSTAL, ember: F.TYPES.EMBER, salt: F.TYPES.SALT };
  const cell = F.cells[back[0]][back[1]][back[2]];
  for (let k = 0; k < owed + 2; k++) {
    cell.item = MIN[ore];
    await new Promise(r => setTimeout(r, 480));
  }
  const after = window.__game.facts();
  return { owed, ore, valueBefore: before.value, valueAfter: after.value,
           rift: after.rift };
}, lend.back);
console.log('repaid     :', repay.owed, '\u00d7', repay.ore,
            '| value', repay.valueBefore.toFixed(1), '->', repay.valueAfter.toFixed(1),
            '| now', JSON.stringify(repay.rift));

// 3. and a rift that is NOT paid takes the factory around it
const storm = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let at = null;
  F.cells.forEach((face, f) => face.forEach((col, i) => col.forEach((c, j) => {
    if (c.t === TY.RIFT && !at) at = [f, i, j];
  })));
  if (!at) return { skipped: true };
  // put something of ours next to it, then let the clock run out
  const near = F.stepTile(at[0], at[1], at[2], 1);
  F.place(near.face, near.i, near.j, TY.SMELTER, 0);
  const before = window.__game.facts().machines;
  F.riftStorm(at[0], at[1], at[2]);
  await new Promise(r => setTimeout(r, 300));
  const mid = window.__game.facts();
  return { before, after: mid.machines, debris: mid.debris,
           smelterGone: F.cells[near.face][near.i][near.j].t !== TY.SMELTER };
});
console.log('storm      : machines', storm.before, '->', storm.after,
            '| debris', storm.debris, '| the neighbour is gone:', storm.smelterGone);
console.log('errors     :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'rift.png' });
await b.close();
const ok = lend.rift && lend.rift.debt > 0 && lend.rift.ore && lend.onBelt
  && repay.valueAfter > repay.valueBefore && repay.rift.debt === 0 && repay.rift.cool > 0
  && storm.after < storm.before && storm.debris > 0 && storm.smelterGone
  && errs.length === 0;
process.exit(ok ? 0 : 1);
