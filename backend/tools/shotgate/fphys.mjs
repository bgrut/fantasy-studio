// Two things a factory sim has to get right and neither shows up as an error:
// you cannot walk through your own machines, and a merge does not eat items.
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
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'fresh=1',
  { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

// ── 1. a wall of machines stops you, and you slide along it ───────────────
const wall = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  // clear a lane, stand in it, and build a wall three tiles ahead
  const face = 0, ci = Math.floor(F.N / 2), cj = Math.floor(F.N / 2);
  for (let i = ci - 4; i <= ci + 4; i++)
    for (let j = cj - 4; j <= cj + 4; j++)
      if (F.cells[face][i][j].t !== TY.EMPTY) F.removeAt(face, i, j);
  for (let i = ci - 3; i <= ci + 3; i++) F.place(face, i, cj + 2, TY.SMELTER, 0);
  // stand two tiles short of the wall, facing it (+v on the top face is -Z)
  const T = F.T, N = F.N, HALF = F.HALF;
  const a = (ci + 0.5 - N / 2) * T, bb = (cj - 0.5 - N / 2) * T;
  F.player.face = face; F.player.h = 0; F.player.vy = 0;
  F.player.pos.set(a, HALF + 1.68, -bb);      // top face: v = -Z
  F.player.fwd.set(0, 0, -1);                 // straight at the wall
  F.player.up.set(0, 1, 0);
  return { wallRow: cj + 2, startZ: +F.player.pos.z.toFixed(2) };
}, );
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,2500));
await p.keyboard.up('KeyW');
const stopped = await p.evaluate(()=>{
  const F = window.__factory;
  const z = F.player.pos.z, T = F.T, N = F.N;
  const j = Math.floor(-z / T + N / 2);
  return { z: +z.toFixed(2), tileJ: j, face: F.player.face };
});
console.log('walked into a wall of smelters -> stopped at tile j', stopped.tileJ,
            '(wall is at', wall.wallRow + ')');

// still able to slide sideways along it
const beforeA = await p.evaluate(()=>+window.__factory.player.pos.x.toFixed(2));
await p.keyboard.down('KeyD');
await new Promise(r=>setTimeout(r,1200));
await p.keyboard.up('KeyD');
const afterA = await p.evaluate(()=>+window.__factory.player.pos.x.toFixed(2));
console.log('slides along it :', Math.abs(afterA - beforeA).toFixed(2) + 'm sideways');

// ── 2. a merge must not eat items, and must not starve one input ──────────
const merge = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const face = 0, ci = 6, cj = 6;
  // EVERY machine, not just the ones in the way: the starter line keeps mining
  // and banking through the test, and its output landed in the same counter —
  // the first run "lost" nothing and gained 26 value from somewhere else.
  for (let f = 0; f < 6; f++)
    for (let i = 0; i < F.N; i++)
      for (let j = 0; j < F.N; j++)
        if (F.cells[f][i][j].t !== TY.EMPTY && F.cells[f][i][j].t !== TY.NODE)
          F.removeAt(f, i, j);
  // two feeders pointing into one collector; the collector points at a hub
  const mid = { i: ci, j: cj };
  const hub = F.stepTile(face, mid.i, mid.j, 0);
  F.place(face, mid.i, mid.j, TY.BELT, 0);
  F.place(hub.face, hub.i, hub.j, TY.HUB, 0);
  const inA = F.stepTile(face, mid.i, mid.j, 2);           // behind
  const inB = F.stepTile(face, mid.i, mid.j, 1);           // to the side
  F.place(inA.face, inA.i, inA.j, TY.BELT, 0);
  F.place(inB.face, inB.i, inB.j, TY.BELT, (inB.d + 2) % 4);
  const A = F.cells[inA.face][inA.i][inA.j];
  const B = F.cells[inB.face][inB.i][inB.j];
  // point B at the collector explicitly
  for (let d = 0; d < 4; d++) {
    const s = F.stepTile(inB.face, inB.i, inB.j, d);
    if (s && s.face === face && s.i === mid.i && s.j === mid.j) B.d = d;
  }
  let fedA = 0, fedB = 0;
  const start = window.__game.facts().value;
  // keep both inputs saturated for a while and count what goes in
  for (let k = 0; k < 60; k++) {
    if (!A.item) { A.item = TY.CRYSTAL; fedA++; }
    if (!B.item) { B.item = TY.CRYSTAL; fedB++; }
    await new Promise(r => setTimeout(r, 100));
  }
  await new Promise(r => setTimeout(r, 900));
  const inFlight = (A.item ? 1 : 0) + (B.item ? 1 : 0)
    + (F.cells[face][mid.i][mid.j].item ? 1 : 0);
  return { fedA, fedB, banked: window.__game.facts().value - start,
           inFlight, price: F.PRICE[TY.CRYSTAL] || 1 };
});
// raw ore banks at its base value, so items in == value in (minus what is still moving)
const expected = merge.fedA + merge.fedB - merge.inFlight;
console.log('merge fed      :', merge.fedA, 'from A +', merge.fedB, 'from B =',
            merge.fedA + merge.fedB, '| banked', merge.banked.toFixed(1),
            '| still moving', merge.inFlight);
const lossless = Math.abs(merge.banked - expected) < 1.5;
const fair = Math.min(merge.fedA, merge.fedB) / Math.max(merge.fedA, merge.fedB) > 0.7;
console.log('lossless       :', lossless, '| fair to both inputs:', fair,
            '(' + merge.fedA + ' vs ' + merge.fedB + ')');
console.log('errors         :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'phys.png' });
await b.close();
const blocked = stopped.tileJ < wall.wallRow;
const slid = Math.abs(afterA - beforeA) > 2;
process.exit((blocked && slid && lossless && fair && errs.length === 0) ? 0 : 1);
