// The blueprint. It has to be locked until the forge tier, copy exactly the
// machines in a box with their headings and a filter's setting, stamp them
// on another face with the same headings, turn a quarter correctly (a belt
// heading +i becomes +j), refuse taken tiles and seamless rigs and say so,
// and survive a reload.
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
const q = URL.includes('?') ? '&' : '?';
const wait = ms => new Promise(r => setTimeout(r, ms));

await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);

// 1. locked until the forge tier; the chip exists
const lock = await p.evaluate(async () => {
  const F = window.__factory;
  const chip = !!document.querySelector('.tool[data-tool="blueprint"]');
  const before = !!F.UNLOCKED.blueprint;
  F.goalIdx = 3; await new Promise(r => setTimeout(r, 300));     // past "stand on a second face"
  return { chip, before, after: !!F.UNLOCKED.blueprint, forge: !!F.UNLOCKED.forge };
});
console.log('locked    : chip', lock.chip, '| before tier 3', lock.before, '| after: blueprint', lock.after, 'forge', lock.forge);

// 2. build a small line on the top face, copy it, stamp it on the east face
const copy = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  // find a clear 4x2 on face 0 away from the starter line
  let s = null;
  for (let i = 3; i < F.N - 6 && !s; i++) for (let j = 3; j < F.N - 4 && !s; j++) {
    let ok = true;
    for (let a = 0; a < 4 && ok; a++) for (let bb = 0; bb < 2 && ok; bb++) if (F.cells[0][i + a][j + bb].t !== TY.EMPTY) ok = false;
    if (ok) s = [i, j];
  }
  const [i, j] = s;
  F.place(0, i, j, TY.BELT, 0); F.place(0, i + 1, j, TY.BELT, 0); F.place(0, i + 2, j, TY.SMELTER, 0); F.place(0, i + 3, j, TY.BELT, 1);
  F.place(0, i + 1, j + 1, TY.FILTER, 3); F.cells[0][i + 1][j + 1].filt = TY.SALT;
  const bp = F.captureBlueprint(0, i, j, i + 3, j + 1);
  const said = document.getElementById('toast').textContent;
  // stamp on face 2 at a clear spot
  let t = null;
  for (let a = 3; a < F.N - 6 && !t; a++) for (let bb = 3; bb < F.N - 4 && !t; bb++) {
    let ok = true;
    for (let x = 0; x < 4 && ok; x++) for (let y = 0; y < 2 && ok; y++) if (F.cells[2][a + x][bb + y].t !== TY.EMPTY) ok = false;
    if (ok) t = [a, bb];
  }
  const placed = F.stampBlueprint(2, t[0], t[1]);
  const got = [];
  for (const c of bp.cells) { const cell = F.cells[2][t[0] + c.di][t[1] + c.dj]; got.push({ t: cell.t, d: cell.d, filt: cell.filt || 0 }); }
  const same = bp.cells.every((c, k) => got[k].t === c.t && got[k].d === c.d && (c.t !== TY.FILTER || got[k].filt === c.filt));
  return { n: bp.cells.length, w: bp.w, h: bp.h, said, placed, same, stampSaid: document.getElementById('toast').textContent, anchor: t };
});
console.log('copied    :', copy.n, 'machines over', copy.w + 'x' + copy.h, '| said:', JSON.stringify(copy.said));
console.log('stamped   :', copy.placed, 'placed on the east face | types, headings and the filter setting match:', copy.same, '| said:', JSON.stringify(copy.stampSaid));

// 3. a quarter turn: a belt heading +i becomes +j; taken tiles and seamless rigs are refused and named
const turn = await p.evaluate(async (anchor) => {
  const F = window.__factory, TY = F.TYPES;
  F.bpRot = 1;
  const cs = F.bpCells();
  const beltHead = cs.filter(c => c.t === TY.BELT).map(c => c.d);
  // stamp again on the same anchor: everything is taken now
  const facts = window.__game.facts();
  const again = F.stampBlueprint(2, anchor[0], anchor[1]);   // the same anchor: everything is taken
  const saidTaken = document.getElementById('toast').textContent;
  // a rig on empty ground is refused for want of a seam
  let e = null;
  for (let i = 3; i < F.N - 3 && !e; i++) for (let j = 3; j < F.N - 3 && !e; j++) if (F.cells[3][i][j].t === TY.EMPTY && F.cells[3][i][j + 1] && F.cells[3][i][j + 1].t === TY.EMPTY) e = [i, j];
  F.place(3, e[0], e[1], TY.MINER, 0);       // refused: not a seam, so nothing there
  F.captureBlueprint(3, e[0], e[1], e[0], e[1]);
  const nothing = document.getElementById('toast').textContent;
  return { rot: facts.blueprint && facts.blueprint.rot, beltHead, again, saidTaken, nothing };
}, copy.anchor);
console.log('turned    : belts now head', JSON.stringify(turn.beltHead), '(were 0,0,1) | stamp on taken ground placed', turn.again, '| said:', JSON.stringify(turn.saidTaken));
console.log('empty box :', JSON.stringify(turn.nothing));

// 4. the blueprint survives a reload
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const back = await p.evaluate(() => window.__game.facts().blueprint);
console.log('reloaded  : blueprint', JSON.stringify(back));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'blueprint.png' });
await b.close();

const ok = lock.chip && !lock.before && lock.after && lock.forge
  && copy.n === 5 && copy.w === 4 && copy.h === 2 && /Blueprint copied: 5 machines/.test(copy.said)
  && copy.placed === 5 && copy.same && /Stamped 5 of 5/.test(copy.stampSaid)
  && turn.beltHead.join(',') === '1,1,2' && turn.again < 5 && /in the way|fell off/.test(turn.saidTaken) && /Nothing to copy/.test(turn.nothing)
  && back && back.n === 5
  && errs.length === 0;
process.exit(ok ? 0 : 1);
