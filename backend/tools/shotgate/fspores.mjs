// The Verdant Fault's spores. A pressure has to be real (a clogged belt holds
// its load), answerable by building (a filter within reach shields the belts
// around it), confined to where it belongs (green worlds only, never before
// the filter exists, never in creative), and explained once when it first
// lands.
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

// 1. where the spores live, and where they do not
const where = await p.evaluate(async () => {
  const F = window.__factory;
  const homeActiveBefore = window.__game.facts().spores.active;
  F.goalIdx = F.GOALS.length; F.addCores(9);          // the chain walked: filter exists, every world open
  await new Promise(r => setTimeout(r, 300));
  const homeActive = window.__game.facts().spores.active;
  const green = F.WORLDS.findIndex(w => w.spores);
  if (green > 0) { F.travelTo(green); F.endIntro(); }
  await new Promise(r => setTimeout(r, 600));
  const f = window.__game.facts();
  return { homeSpores: !!F.WORLDS[0].spores, homeActiveBefore, homeActive, green,
           world: f.world, active: f.spores.active,
           belts: (() => { let n = 0; F.cells.forEach(fc => fc.forEach(col => col.forEach(c => { if (c.t === F.TYPES.BELT) n++; }))); return n; })() };
});
console.log('home      :', where.homeSpores ? 'is green' : 'not green', '| spores active before the chain',
            where.homeActiveBefore, '| after', where.homeActive);
console.log('green     : world', where.green, '->', where.world, '| active', where.active, '| belts', where.belts);

// 2. a clogged belt holds its load; a clean one passes it on the next tick
const hold = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  // a private two-belt run on an empty stretch, pointing +i
  let spot = null;
  for (let i = 3; i < F.N - 6 && !spot; i++)
    for (let j = 3; j < F.N - 3 && !spot; j++)
      if ([0, 1, 2].every(k => F.cells[F.player.face][i + k][j].t === TY.EMPTY)) spot = [i, j];
  const f = F.player.face, [i, j] = spot;
  F.place(f, i, j, TY.BELT, 0); F.place(f, i + 1, j, TY.BELT, 0); F.place(f, i + 2, j, TY.BELT, 0);
  const A = F.cells[f][i][j], B = F.cells[f][i + 1][j], C = F.cells[f][i + 2][j];
  A.clog = F.SPORE_CLOG; A.item = TY.CRYSTAL;
  await w(1600);
  const heldA = A.item, heldB = B.item, clogged = window.__game.facts().spores.clogged;
  A.clog = 0;
  await w(1600);
  // a freed crystal may have made two ticks by now: it is on B or on C, not on A
  return { spot, heldA, heldB, clogged, afterA: A.item, afterB: B.item || C.item, dir: A.d };
});
// an empty belt holds 0, not null
console.log('hold      : clogged belt kept its crystal', !!hold.heldA && !hold.heldB,
            '(clogged', hold.clogged + ') | cleared -> moved on', !hold.afterA && !!hold.afterB);

// 3. a filter shields the belts within reach, and strikes land only outside it
const shield = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, R = F.SPORE_REACH;
  const f = F.player.face;
  // from the far corner, so the filter does not also shield the starter line
  // and the hold test's belts, which would leave the strikes nothing to hit
  let spot = null;
  for (let i = F.N - R - 3; i > R && !spot; i--)
    for (let j = F.N - R - 3; j > R && !spot; j--)
      if (F.cells[f][i][j].t === TY.EMPTY && F.cells[f][i + R][j].t === TY.EMPTY && F.cells[f][i + R + 1][j].t === TY.EMPTY) spot = [i, j];
  const [i, j] = spot;
  F.place(f, i, j, TY.FILTER, 0);
  F.place(f, i + R, j, TY.BELT, 0);
  F.place(f, i + R + 1, j, TY.BELT, 0);
  const inside = F.sporeShielded(f, i + R, j), outside = F.sporeShielded(f, i + R + 1, j);
  // forty strikes: every one lands on an unshielded belt and clogs it
  let landed = 0, onShielded = 0, notBelt = 0;
  for (let k = 0; k < 40; k++) {
    const hit = F.sporeStrike();
    if (!hit) break;
    landed++;
    const c = F.cells[hit[0]][hit[1]][hit[2]];
    if (c.t !== TY.BELT || !(c.clog > 0)) notBelt++;
    if (F.sporeShielded(hit[0], hit[1], hit[2])) onShielded++;
  }
  const toast = document.getElementById('toast').textContent;
  return { inside, outside, landed, onShielded, notBelt, toast, hits: window.__game.facts().spores.hits };
});
console.log('shield    : belt', shield.inside ? 'inside reach is shielded' : 'inside reach NOT shielded',
            '| one past reach', shield.outside ? 'shielded (wrong)' : 'exposed');
console.log('strikes   :', shield.landed, 'landed |', shield.onShielded, 'on shielded belts |',
            shield.notBelt, 'not a clogged belt | said:', JSON.stringify(shield.toast));

// 4. the clock strikes on its own
//    (the forty strikes above clogged every exposed belt; a strike needs an
//    open one, so the clogs are cleared first)
const clock = await p.evaluate(async () => {
  const F = window.__factory;
  F.cells.forEach(fc => fc.forEach(col => col.forEach(c => { c.clog = 0; })));
  const a = window.__game.facts().spores.hits;
  await new Promise(r => setTimeout(r, 6500));
  return { a, b: window.__game.facts().spores.hits, clogged: window.__game.facts().spores.clogged };
});
console.log('clock     : hits', clock.a, '->', clock.b, 'over 6.5s | clogged now', clock.clogged);

// 5. creative has no spores, even on the green world
await p.goto(URL + q + 'creative=1&fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const creative = await p.evaluate(async () => {
  const F = window.__factory;
  const green = F.WORLDS.findIndex(w => w.spores);
  if (green > 0) { F.travelTo(green); F.endIntro(); }
  await new Promise(r => setTimeout(r, 500));
  const f = window.__game.facts();
  return { world: f.world, active: f.spores.active, creative: f.creative };
});
console.log('creative  :', creative.world, '| creative', creative.creative, '| spores active', creative.active);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'spores.png' });
await b.close();

const ok = where.green >= 0 && !where.homeActiveBefore
  && (where.homeSpores || !where.homeActive)
  && where.active && where.belts > 0
  && !!hold.heldA && !hold.heldB && hold.clogged >= 1 && !hold.afterA && !!hold.afterB
  && shield.inside && !shield.outside && shield.landed >= 3 && shield.onShielded === 0 && shield.notBelt === 0
  && /SPORES/.test(shield.toast) && shield.hits >= shield.landed
  && clock.b > clock.a
  && creative.creative && !creative.active
  && errs.length === 0;
process.exit(ok ? 0 : 1);
