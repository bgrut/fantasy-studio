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
// URL lets the same gate run against the standalone demo as well as a studio
// build — the point of generating one from the other is that both must pass it
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
// ?fresh=1: this run must not grade the previous run's factory
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'fresh=1',
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

// THE MECHANIC: walk far enough to go over an edge and check that the world
// rotated under you rather than that you fell off it.
// MACHINES ARE SOLID NOW (2026-09-08). The spawn stands you four tiles behind
// the starter line looking AT it, which is right for a first frame and wrong
// for a walk test: the edge walk ended against your own smelter two tiles in
// and reported that the world had no edges. Turn around first.
await p.evaluate(()=>{ window.__factory.player.fwd.negate(); });
const startFace = t1.player_face;
let crossed = null, offCube = 0;
await p.keyboard.down('KeyW');
// far enough to cross from anywhere on the face. Turning away from the line
// means the near edge is now behind the factory and the far one is up to 65m
// off; 24 samples covered 45m and reported that the world had no edges.
for (let k = 0; k < 46; k++) {
  await new Promise(r=>setTimeout(r,300));
  const f = await p.evaluate(()=>window.__game.facts());
  const H = await p.evaluate(()=>window.__factory.HALF);
  const d = Math.max(...(await p.evaluate(()=>window.__game.pos())).map(Math.abs));
  if (d < H - 1 || d > H + 4) offCube++;          // must stay ON the surface
  if (f.player_face !== startFace && !crossed) crossed = f;
}
await p.keyboard.up('KeyW');
const fin = await p.evaluate(()=>window.__game.facts());
console.log('faces     :', startFace, '->', (crossed||fin).player_face,
            '| up', JSON.stringify((crossed||fin).player_up));
console.log('on surface:', offCube === 0 ? 'always' : offCube + ' samples off the cube');
// AND THE SIM SIDE OF THE SAME MECHANIC: a belt that runs off an edge has to
// hand its crystal to the belt on the next face. The player walking over an
// edge and the items doing it are different code paths; a gate that only
// checks the camera would miss a factory that silently drops everything at
// the seam.
const wrap = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  for (let j = 2; j < F.N - 2; j++) {
    const src = { face: 0, i: F.N - 1, j };
    const dst = F.stepTile(src.face, src.i, src.j, 0);
    if (!dst || !dst.wrapped) continue;
    if (F.cells[src.face][src.i][src.j].t !== TY.EMPTY) continue;
    if (F.cells[dst.face][dst.i][dst.j].t !== TY.EMPTY) continue;
    F.place(src.face, src.i, src.j, TY.BELT, 0);
    F.place(dst.face, dst.i, dst.j, TY.BELT, dst.d);
    F.cells[src.face][src.i][src.j].item = TY.CRYSTAL;
    await new Promise(r => setTimeout(r, 1400));
    return { from: 'face' + src.face, to: 'face' + dst.face,
             arrived: F.cells[dst.face][dst.i][dst.j].item === TY.CRYSTAL,
             left: F.cells[src.face][src.i][src.j].item === 0 };
  }
  return { skipped: true };
});
console.log('belt wrap :', JSON.stringify(wrap));
// THE REASON TO LEAVE THE TOP FACE: an alloy needs two different ores, and no
// single face grows two. Fed one crystal and one ember, the forge must produce
// something the hub banks as an alloy.
const forge = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const faces = F.MINERAL_OF_FACE;
  const distinct = new Set(faces).size;
  for (let i = 3; i < F.N - 3; i++) {
    for (let j = 3; j < F.N - 3; j++) {
      const clear = [[i,j],[i+1,j],[i-1,j],[i,j-1]]
        .every(([a,b]) => F.cells[0][a][b].t === TY.EMPTY);
      if (!clear) continue;
      F.place(0, i, j, TY.FORGE, 0);
      F.place(0, i + 1, j, TY.HUB, 0);
      F.place(0, i - 1, j, TY.BELT, 0);        // points +u, into the forge
      F.place(0, i, j - 1, TY.BELT, 1);        // points +v, into the forge
      F.cells[0][i - 1][j].item = TY.CRYSTAL;
      F.cells[0][i][j - 1].item = TY.EMBER;
      const before = F.alloys;
      await new Promise(r => setTimeout(r, 3500));
      return { distinct, faces, made: F.alloys - before };
    }
  }
  return { distinct, faces, skipped: true };
});
console.log('minerals  :', forge.faces ? forge.faces.join(' ') : '?',
            '|', forge.distinct, 'distinct | alloys made', forge.made);

// THE MARKET: prices have to actually move, stay inside their rails, and be
// what the hub pays — a ticker that drifts but does not change the payout is
// decoration, and gives the player nothing to decide.
const mkt = await p.evaluate(async () => {
  const F = window.__factory;
  const a = F.TRADED.map(t => F.PRICE[t]);
  for (let k = 0; k < 40; k++) F.stepMarket(1.0);      // 40 simulated seconds
  const b = F.TRADED.map(t => F.PRICE[t]);
  const n = b.length;
  const moved = a.filter((v, i) => Math.abs(v - b[i]) > 1e-6).length;
  const inRange = b.every(v => v >= 0.55 - 1e-9 && v <= 1.85 + 1e-9);
  return { n, moved, inRange, sample: b.map(v => +v.toFixed(2)),
           alloyPrice: +F.PRICE[F.TYPES.ALLOY].toFixed(2) };
});
console.log('market    :', mkt.moved, 'of', mkt.n, 'prices moved | in range', mkt.inRange,
            '|', JSON.stringify(mkt.sample));

// THE FILTER: matching ore goes straight, everything else out of the side.
// Both halves are checked, because a filter that passes everything and a
// filter that rejects everything both "work" if you only test one ore.
const filt = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const free = (a, b) => F.cells[0][a][b].t === TY.EMPTY;
  for (let i = 4; i < F.N - 4; i++) {
    for (let j = 4; j < F.N - 4; j++) {
      const straight = F.stepTile(0, i, j, 0), side = F.stepTile(0, i, j, 1);
      const beyondS = F.stepTile(straight.face, straight.i, straight.j, straight.d);
      const beyondD = F.stepTile(side.face, side.i, side.j, side.d);
      const tiles = [[i,j], [straight.i,straight.j], [side.i,side.j],
                     [beyondS.i,beyondS.j], [beyondD.i,beyondD.j]];
      if (!tiles.every(([a,b]) => free(a,b))) continue;
      F.place(0, i, j, TY.FILTER, 0);
      // the two collectors point at empty ground, so whatever lands on them
      // stays there for the check instead of moving on next tick
      F.place(straight.face, straight.i, straight.j, TY.BELT, straight.d);
      F.place(side.face, side.i, side.j, TY.BELT, side.d);
      const cf = F.cells[0][i][j];
      const S = F.cells[straight.face][straight.i][straight.j];
      const D = F.cells[side.face][side.i][side.j];
      cf.filt = TY.CRYSTAL;

      cf.item = TY.CRYSTAL;
      await new Promise(r => setTimeout(r, 1100));
      const pass = { straight: S.item, side: D.item };
      S.item = 0; D.item = 0;

      cf.item = TY.EMBER;
      await new Promise(r => setTimeout(r, 1100));
      const rej = { straight: S.item, side: D.item };
      return { crystal: pass, ember: rej, CRYSTAL: TY.CRYSTAL, EMBER: TY.EMBER };
    }
  }
  return { skipped: true };
});
const filtOk = filt.crystal && filt.crystal.straight === filt.CRYSTAL
            && filt.crystal.side === 0
            && filt.ember.side === filt.EMBER && filt.ember.straight === 0;
console.log('filter    : crystal', JSON.stringify(filt.crystal),
            '| ember', JSON.stringify(filt.ember), '|', filtOk ? 'sorts' : 'WRONG');

// PRESTIGE: the factory is destroyed and the run is faster afterwards. Both
// halves matter — a meltdown that clears the cube but leaves you with nothing
// running is indistinguishable from having lost the game.
await p.evaluate(()=>{ const F = window.__factory; F.addValue(F.MELT_MIN + 240); });
await new Promise(r=>setTimeout(r,300));
const preMachines = (await p.evaluate(()=>window.__game.facts())).machines;
await p.evaluate(()=>window.__factory.meltdown());
await new Promise(r=>setTimeout(r,350));
const mid = await p.evaluate(()=>window.__game.facts());
await p.screenshot({ path: (process.env.OUT || 'factory.png').replace(/\.png$/, '_melt.png') });
await new Promise(r=>setTimeout(r,3200));
const post = await p.evaluate(()=>window.__game.facts());
const val = await p.evaluate(()=>window.__factory.TYPES && window.__SPEC ? null : null);
console.log('meltdown  : machines', preMachines, '-> debris', mid.debris,
            '-> rebuilt', post.machines, '| cores', post.cores,
            '| value reset to', post.value);
const meltOk = mid.debris >= preMachines && post.debris === 0
            && post.machines >= 5 && post.cores >= 1 && post.value < 40;
console.log('produced  :', t1.value - t0.value, 'value in 12s |', 'ingots', t1.ingots);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
process.exit((errs.length || t1.value <= t0.value || !crossed || offCube
  || !wrap.arrived || !wrap.left || !meltOk
  || forge.distinct !== 3 || !(forge.made > 0) || !filtOk
  || mkt.moved !== mkt.n || !mkt.inRange) ? 1 : 0);
