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

// THE MECHANIC: walk far enough to go over an edge and check that the world
// rotated under you rather than that you fell off it.
const startFace = t1.player_face;
let crossed = null, offCube = 0;
await p.keyboard.down('KeyW');
for (let k = 0; k < 24; k++) {
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
  || !wrap.arrived || !wrap.left || !meltOk) ? 1 : 0);
