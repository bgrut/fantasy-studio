// Ice on a cold world. A pressure has to be real (a frozen seam starves its
// rig), answerable by building (a furnace within reach keeps the seams round
// it thawed, and melts ice it reaches faster), answered outright by the
// capability the chain hands out (the heated drill), confined to cold worlds,
// and gone in creative.
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

// the cold world, without the drill: travel refuses without the capability
// (which is the point), so ?world= puts us there without the chain
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const home = await p.evaluate(() => { const F = window.__factory;
  return { cold: F.WORLDS.findIndex(w => w.ice), homeIce: !!F.WORLDS[0].ice, homeActive: window.__game.facts().ice.active }; });
if (home.cold > 0) { await p.goto(URL + q + 'fresh=1&nointro=1&world=' + home.cold, { waitUntil:'domcontentloaded', timeout:90000 }); await wait(4500); }
const where = await p.evaluate(async () => {
  const f = window.__game.facts();
  return { world: f.world, active: f.ice.active, heated: f.caps.includes('heated') };
});
where.cold = home.cold; where.homeIce = home.homeIce; where.homeActive = home.homeActive;
console.log('cold world:', where.cold, '->', where.world, '| ice active', where.active, '| drill', where.heated,
            '| home', where.homeIce ? 'is cold' : 'not cold', '| active at home', where.homeActive);

// 1. a strike freezes a seam no heat is near; its rig starves; a shell appears
const frozen = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  // the strike proves the shell; the yield test picks its own seam — one with
  // no rig and a free tile beside it, so the rig has somewhere to deliver
  const hit = F.iceStrike();
  if (!hit) return { hit: null };
  const shell = !!F.cells[hit[0]][hit[1]][hit[2]].iceMesh && !!window.__scene.getObjectByName('ice');
  // any face, any seam with an empty tile beside it in the +i direction
  let pick = null;
  for (let f = 0; f < 6 && !pick; f++)
    for (let i = 1; i < F.N - 2 && !pick; i++) for (let j = 1; j < F.N - 1 && !pick; j++) {
      const s = F.cells[f][i][j];
      if (s.t === TY.NODE && s.mesh && F.cells[f][i + 1][j].t === TY.EMPTY) pick = [f, i, j];
    }
  if (!pick) return { hit, shell, outFrozen: 0, outThawed: 0, noSeam: true };
  const c = F.cells[pick[0]][pick[1]][pick[2]];
  c.ice = F.ICE_THAW;
  F.place(pick[0], pick[1], pick[2], TY.MINER, 0);
  const to = F.stepTile(pick[0], pick[1], pick[2], 0);
  F.place(to.face, to.i, to.j, TY.BELT, 0);
  const belt = F.cells[to.face][to.i][to.j];
  let outFrozen = 0;
  for (let k = 0; k < 60; k++) { belt.item = 0; F.step(); if (belt.item) outFrozen++; }
  const iceLeft = c.ice;
  c.ice = 0; if (c.iceMesh) { window.__scene.remove(c.iceMesh); c.iceMesh = null; }
  let outThawed = 0;
  for (let k = 0; k < 60; k++) { belt.item = 0; F.step(); if (belt.item) outThawed++; }
  return { hit, shell, outFrozen, outThawed, iceLeft: +iceLeft.toFixed(1), frozenCount: window.__game.facts().ice.frozen,
           toast: document.getElementById('toast').textContent };
});
console.log('frozen    : shell', frozen.shell, '| rig yielded', frozen.outFrozen, 'of 60 ticks frozen vs',
            frozen.outThawed, 'thawed | said:', JSON.stringify(frozen.toast));

// 2. a furnace within reach shields the seams round it, and strikes land only past it
const shield = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, R = F.ICE_REACH;
  // every seam on the top face; put a smelter next to the first and count
  let seam = null;
  for (let i = 0; i < F.N && !seam; i++) for (let j = 0; j < F.N && !seam; j++) if (F.cells[0][i][j].mesh) seam = [i, j];
  const [i, j] = seam;
  let spot = null;
  for (let a = -R + 1; a < R && !spot; a++) for (let bb = -R + 1; bb < R && !spot; bb++) {
    const c = F.cells[0][i + a] && F.cells[0][i + a][j + bb];
    if (c && c.t === TY.EMPTY) spot = [i + a, j + bb];
  }
  F.place(0, spot[0], spot[1], TY.SMELTER, 0);
  const inside = F.iceShielded(0, i, j);
  let onShielded = 0, landed = 0;
  for (let k = 0; k < 30; k++) { const h = F.iceStrike(); if (!h) break; landed++; if (F.iceShielded(h[0], h[1], h[2])) onShielded++; }
  // and ice that heat reaches melts faster: put ice on the shielded seam and time it
  const c = F.cells[0][i][j];
  c.ice = 3; const t0 = performance.now();
  await new Promise(r => setTimeout(r, 1300));
  const near = c.ice;
  return { inside, landed, onShielded, near: +near.toFixed(2) };
});
console.log('shield    : seam beside a furnace shielded', shield.inside, '|', shield.landed, 'strikes,', shield.onShielded,
            'on shielded seams | 3s of ice beside heat after 1.3s:', shield.near, '(would be 1.7 without)');

// 3. the drill: with the capability the ice is gone and strikes stop
const drill = await p.evaluate(async () => {
  const F = window.__factory;
  F.goalIdx = F.GOALS.length;             // hands out the heated drill
  await new Promise(r => setTimeout(r, 400));
  const f = window.__game.facts();
  return { heated: f.caps.includes('heated'), active: f.ice.active, frozen: f.ice.frozen, shells: !!window.__scene.getObjectByName('ice') };
});
console.log('the drill : heated', drill.heated, '| ice active', drill.active, '| frozen seams', drill.frozen, '| shells left', drill.shells);

// 4. creative: no ice
await p.goto(URL + q + 'creative=1&fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const creative = await p.evaluate(async () => {
  const F = window.__factory;
  const cold = F.WORLDS.findIndex(w => w.ice);
  if (cold > 0) { F.travelTo(cold); F.endIntro(); }
  await new Promise(r => setTimeout(r, 500));
  const f = window.__game.facts();
  return { world: f.world, active: f.ice.active, creative: f.creative };
});
console.log('creative  :', creative.world, '| creative', creative.creative, '| ice active', creative.active);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'ice.png' });
await b.close();

const ok = where.cold >= 0 && where.active && !where.heated && (where.homeIce || !where.homeActive)
  && frozen.hit && frozen.shell && frozen.outFrozen < frozen.outThawed * 0.5 && /ICE/.test(frozen.toast)
  && shield.inside && shield.onShielded === 0 && shield.near < 1.2
  && drill.heated && !drill.active && drill.frozen === 0 && !drill.shells
  && creative.creative && !creative.active
  && errs.length === 0;
process.exit(ok ? 0 : 1);
