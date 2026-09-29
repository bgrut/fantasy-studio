// A CITY BUILDER (TOWN=<job>), held to its rules (2026-09-29).
//
// The worldlet builds a town, and the quarry stands down: no seams, no market,
// no foreman, a bar of city tools with a road in hand, a town hall with a
// street out of its door. Then the rules, each on its own patch of ground:
// a click at the crosshair lays a road and it costs; no money, no road; the
// hall cannot be erased; homes beside a road that misses the hall stay empty
// until it is joined up; homes with no work stay small; a works keeps the homes
// beside it small and a park lets them grow into flats; people pay; a planned
// town reaches the sentence's population and says so; and the town is still
// there after a reload.
//
//   TOWN=<job> node ftown.mjs
import puppeteer from 'puppeteer-core';
const TOWN = process.env.TOWN;
if (!TOWN) { console.log('ftown: TOWN=<job> needed; FAIL'); process.exit(1); }
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const fails = [];
const check = (ok, what) => { console.log((ok ? '  ok   ' : '  FAIL ') + what); if (!ok) fails.push(what); };
const base = 'http://127.0.0.1:8789/games/job_' + TOWN + '/dist/';
async function boot(q) {
  await p.goto(base + q, { waitUntil: 'domcontentloaded', timeout: 120000 });
  for (let i = 0; i < 40; i++) { if (await p.evaluate(() => !!(window.__factory && window.__game))) break; await wait(500); }
  await wait(2500);
}
await boot('?fresh=1&nointro=1');
const C = () => p.evaluate(() => window.__factory.city.state());
const f0 = await p.evaluate(() => window.__game.facts());
check(!!f0.city, 'the game is a town (facts carry a city)');
if (f0.city) {
  check(f0.city.target === 500, `the sentence's population is the goal: ${f0.city.target}`);
  check(f0.nodes === 0 && !f0.contract && !(f0.tutorial && f0.tutorial.active), `the quarry stands down: ${f0.nodes} seams, no contract, no foreman`);
  const bar = await p.evaluate(() => [...document.querySelectorAll('#tools .tool')].map(o => o.dataset.tool).join(','));
  check(bar === 'road,home,shop,works,park,erase', `the bar is a town's: ${bar}`);
  const hidden = await p.evaluate(() => ['tick', 'ups', 'contract', 'melt'].every(id => { const e = document.getElementById(id); return !e || getComputedStyle(e).display === 'none'; }));
  check(hidden, 'the market, upgrades, contracts and meltdown are off the panel');
  check(f0.city.tool === 'road' && f0.city.reach >= 4 && f0.city.cash >= 300, `a road in hand, a hall with a street (${f0.city.reach} tiles reach it), ${f0.city.cash} to spend`);

  // a real click at the crosshair lays a road, and it costs
  const aim = await p.evaluate(() => {
    const F = window.__factory, N = F.N, hi = Math.floor(N / 2), hj = Math.floor(N / 2);
    F.goFace(0, hi + 6, hj - 6); F.player.pitch = -0.75; F.pickTool('road');
    return [hi, hj];
  });
  await wait(800);
  const before = await C();
  await p.mouse.move(640, 380); await p.mouse.down(); await wait(120); await p.mouse.up(); await wait(400);
  const after = await C();
  check(after.n.roads === before.n.roads + 1 && before.cash - after.cash >= 4.5, `a click lays a road: ${before.n.roads} -> ${after.n.roads} roads, ${before.cash} -> ${after.cash} money`);

  // the rules, through the same apply the mouse uses, on patches of their own
  const R = await p.evaluate(([hi, hj]) => {
    const F = window.__factory, cells = F.cells, T = F.city.TYPES;
    const put = (tool, i, j, face) => { F.pickTool(tool); F.apply({ face: face || 0, i, j }, 0); return cells[face || 0][i][j].t; };
    const out = {};
    F.city.cash(0);
    out.broke = put('home', 2, 2) === 0;
    F.city.cash(100000);
    F.pickTool('erase'); F.apply({ face: 0, i: hi, j: hj }, 0);
    out.hall = cells[0][hi][hj].t === T.HALL;
    // homes by a road that misses the hall: face 1 is nowhere near it
    for (let j = 3; j < 10; j++) put('road', 6, j, 1);
    for (let j = 3; j < 10; j++) put('home', 5, j, 1);
    F.city.run(90);
    out.cutoff = [3, 4, 5, 6, 7, 8, 9].every(j => (cells[1][5][j].lvl | 0) === 0 && !cells[1][5][j].served);
    return out;
  }, aim);
  check(R.broke, 'with no money, nothing is built');
  check(R.hall, 'the town hall cannot be erased');
  check(R.cutoff, 'homes by a road that misses the hall stay empty');

  // homes with no work stay small: only the hall's own street, homes along it
  const nowork = await p.evaluate(([hi, hj]) => {
    const F = window.__factory, cells = F.cells;
    const put = (tool, i, j) => { F.pickTool(tool); F.apply({ face: 0, i, j }, 0); };
    for (let k = 4; k <= 12; k++) put('road', hi + k, hj);
    for (let k = 1; k <= 12; k++) put('home', hi + k, hj - 1);
    F.city.run(120);
    return F.city.state();
  }, aim);
  check(nowork.pop <= 48 && nowork.jobs === 0, `homes with no work stay small: ${nowork.pop} people, ${nowork.jobs} jobs`);

  // work, a park and a works, and the town grows to the goal
  const grown = await p.evaluate(([hi, hj]) => {
    const F = window.__factory, cells = F.cells;
    const put = (tool, i, j) => { F.pickTool(tool); F.apply({ face: 0, i, j }, 0); };
    for (let k = 1; k <= 12; k++) put(k <= 7 ? 'shop' : 'works', hi + k, hj + 1);
    for (let k = -8; k <= 8; k++) put('road', hi + 13, hj + k);   // a cross street, joined to the main one
    for (let k = 1; k <= 8; k++) { put(k % 3 === 0 ? 'park' : 'home', hi + 14, hj - k); put('works', hi + 12, hj + k + 1); put('home', hi + 12, hj - k - 1); }
    for (let k = 1; k <= 6; k++) put('works', hi + 14, hj + k);
    const cash0 = F.city.state().cash;
    const s = F.city.run(240);
    // the homes beside the works, and the homes beside the parks
    const byWorks = cells[0][hi + 8][hj - 1], byPark = cells[0][hi + 14][hj - 2];
    return { s, cash0, byWorks: [byWorks.lvl | 0, byWorks.cap], byPark: [byPark.lvl | 0, byPark.cap] };
  }, aim);
  check(grown.byWorks[1] === 1 && grown.byWorks[0] <= 1, `a works keeps the homes beside it small: level ${grown.byWorks[0]} of ${grown.byWorks[1]}`);
  check(grown.byPark[1] === 3 && grown.byPark[0] >= 2, `a park lets homes grow into flats: level ${grown.byPark[0]} of ${grown.byPark[1]}`);
  check(grown.s.income > 0 && grown.s.cash > grown.cash0, `people pay: +${grown.s.income} a second, ${grown.cash0} -> ${grown.s.cash}`);
  check(grown.s.won && grown.s.pop >= 500, `a planned town reaches the goal: ${grown.s.pop} people, ${grown.s.jobs} jobs`);
  await wait(600);
  const said = await p.evaluate(() => (document.getElementById('citygoal') || {}).textContent || '');
  check(/IS GROWN/.test(said), 'the panel says the city is grown');
  const look = await p.evaluate(([hi, hj]) => window.__factory.describeCell(window.__factory.cells[0][hi + 14][hj - 2]), aim);
  check(/^HOMES/.test(look) && /people/.test(look), `the look label reads a home: "${look}"`);

  // the town is still there after a reload
  const n0 = (await C()).n;
  await p.evaluate(() => window.__factory.save());
  await boot('?nointro=1');
  const n1 = (await C()).n;
  check(n1.homes === n0.homes && n1.roads === n0.roads && n1.works === n0.works, `a reload keeps the town: ${n1.homes} homes, ${n1.roads} roads, ${n1.works} works`);
}
check(errs.length === 0, 'no page errors' + (errs.length ? ': ' + errs[0] : ''));
await b.close();
console.log(fails.length ? `${fails.length} failed; FAIL` : 'PASS');
process.exit(fails.length ? 1 : 0);
