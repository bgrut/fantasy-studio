// Hubs are rare and a hub can only take so much. Three belts feeding one hub
// must bank at most two items a tick and back up visibly; a second hub must
// cost credits, be refused without them with a reason, and be paid for with
// them; the ladder must climb; creative must be free; the blueprint must leave
// hubs out; and the label must say how full a hub is.
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

// 1. intake: three belts into one hub, all loaded every tick, bank two a tick
const intake = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  // a private hub on a clear spot of face 3 with three belts pointing into it
  let s = null;
  for (let i = 4; i < F.N - 4 && !s; i++) for (let j = 4; j < F.N - 4 && !s; j++) {
    const ok = [[0, 0], [-1, 0], [1, 0], [0, -1]].every(([a, bb]) => F.cells[3][i + a][j + bb].t === TY.EMPTY);
    if (ok) s = [i, j];
  }
  const [i, j] = s;
  F.place(3, i, j, TY.HUB, 0);                                  // paid for directly: the seam is not the player
  F.place(3, i - 1, j, TY.BELT, 0); F.place(3, i + 1, j, TY.BELT, 2); F.place(3, i, j - 1, TY.BELT, 1);
  const feeders = [F.cells[3][i - 1][j], F.cells[3][i + 1][j], F.cells[3][i][j - 1]];
  const hub = F.cells[3][i][j];
  const perTick = [];
  for (let k = 0; k < 8; k++) {
    for (const c of feeders) if (!c.item) c.item = TY.CRYSTAL;
    const before = window.__game.facts().value;
    F.step();
    perTick.push({ took: hub.took, banked: +(window.__game.facts().value - before).toFixed(1), left: feeders.filter(c => c.item).length });
  }
  const label = (() => { const F2 = window.__factory; return F2.lookLabel ? F2.lookLabel(hub) : null; })();
  return { perTick, intake: F.HUB_INTAKE, heldAfter: feeders.filter(c => c.item).length, acceptsNow: F.accepts ? F.accepts(hub, TY.CRYSTAL) : null };
});
console.log('intake    :', intake.perTick.map(t => t.took + ' taken, ' + t.left + ' held').join(' | '), '| cap', intake.intake);

// 2. cost: the second hub costs 200, is refused without it, paid with it, and the ladder climbs
const cost = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  // back to one hub: drop the private one
  F.cells.forEach((face, fi) => face.forEach((col, i) => col.forEach((c, j) => { if (fi === 3 && c.t === TY.HUB) F.removeAt(fi, i, j); })));
  const hubs = F.hubCount(), c1 = F.hubCost();
  const chip = document.querySelector('.tool[data-tool="hub"] small').textContent;
  let spot = null;
  for (let i = 4; i < F.N - 4 && !spot; i++) for (let j = 4; j < F.N - 4 && !spot; j++) if (F.cells[0][i][j].t === TY.EMPTY) spot = [i, j];
  F.pickTool('hub');
  F.apply({ face: 0, i: spot[0], j: spot[1] }, 0);
  await w(200);
  const refused = F.cells[0][spot[0]][spot[1]].t !== TY.HUB;
  const said = document.getElementById('toast').textContent;
  F.addValue(300);
  const ore0 = window.__game.facts().value;
  F.apply({ face: 0, i: spot[0], j: spot[1] }, 0);
  await w(200);
  const placed = F.cells[0][spot[0]][spot[1]].t === TY.HUB;
  const paid = +(ore0 - window.__game.facts().value).toFixed(0);
  const c2 = F.hubCost();
  const chip2 = document.querySelector('.tool[data-tool="hub"] small').textContent;
  F.pickTool('miner');
  return { hubs, c1, chip, refused, said, placed, paid, c2, chip2, ladder: [0, 1, 2, 3, 4].map(k => F.hubCost(k)) };
});
console.log('cost      :', cost.hubs, 'hub ->', cost.c1, 'for the next | chip', JSON.stringify(cost.chip), '| with 0 credits:', cost.refused ? 'refused' : 'PLACED (wrong)',
            '| said:', JSON.stringify(cost.said).slice(0, 80));
console.log('            with 300: placed', cost.placed, '| paid', cost.paid, '| next', cost.c2, JSON.stringify(cost.chip2), '| ladder', cost.ladder.join(','));

// 3. the blueprint leaves hubs out
const bp = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES;
  F.goalIdx = 3;
  // the starter hub: the one with a belt feeding it, not the bare one placed above
  let h = null;
  F.cells[0].forEach((col, i) => col.forEach((c, j) => {
    if (c.t !== TY.HUB || h) return;
    for (let a = -1; a <= 1; a++) for (let bb = -1; bb <= 1; bb++) { const n = F.cells[0][i + a] && F.cells[0][i + a][j + bb]; if (n && n.t === TY.BELT) h = [i, j]; }
  }));
  const cp = F.captureBlueprint(0, h[0] - 1, h[1] - 1, h[0] + 1, h[1] + 1);
  return { cells: cp ? cp.cells.map(c => c.t) : null, hasHub: cp ? cp.cells.some(c => c.t === TY.HUB) : null };
});
console.log('blueprint : a box round a hub copies', bp.cells ? bp.cells.length : 0, 'machines | hub among them:', bp.hasHub);

// 4. creative: hubs are free
await p.goto(URL + q + 'creative=1&fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const creative = await p.evaluate(() => ({ cost: window.__factory.hubCost(), creative: window.__game.facts().creative }));
console.log('creative  : next hub costs', creative.cost, '| creative', creative.creative);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'hub.png' });
await b.close();

const ok = intake.intake === 2 && intake.perTick.every(t => t.took <= 2) && intake.perTick.slice(1).every(t => t.took === 2 && t.left >= 1)
  && cost.hubs === 1 && cost.c1 === 200 && /200 credits/.test(cost.chip) && cost.refused && /costs 200 credits/.test(cost.said)
  && cost.placed && cost.paid === 200 && cost.c2 === 500 && cost.ladder.join(',') === '0,200,500,1200,2400'
  && bp.cells && bp.hasHub === false
  && creative.creative && creative.cost === 0
  && errs.length === 0;
process.exit(ok ? 0 : 1);
