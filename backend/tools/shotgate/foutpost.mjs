// The starter outpost: a place at spawn. Four props stand by the hub on a
// new world; you cannot build on them or erase them; the look label names
// them; a save carries none of them and a reload puts them back by the hub;
// a blueprint drawn round the hub copies no prop; a world that moved its
// hub gets its outpost by the new one.
//   URL=<demo>  or  J=<studio job id>
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const URL = process.env.URL || 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/';
const q = URL.includes('?') ? '&' : '?';

await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4000);

// 1. four props by the hub; build and erase refuse; the look label names one
const s1 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let hub = null;
  for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const kinds = []; let solid = true;
  for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) { const c = F.cells[0][i][j]; if (c.t === TY.PROP) { kinds.push(c.prop); if (!c.build) solid = false; } }
  const hc = F.habitatOf ? F.habitatOf() : (F.cells[0][hub[0] + 2][hub[1]].t === TY.PROP ? F.cells[0][hub[0] + 2][hub[1]] : F.cells[0][hub[0] + 3][hub[1]]);
  const wasHab = hc.t === TY.PROP && hc.prop === 'habitat';
  const hx = F.cells[0][hub[0] + 2][hub[1]].t === TY.PROP ? hub[0] + 2 : hub[0] + 3;
  F.removeAt(0, hx, hub[1]);
  const stillThere = hc.t === TY.PROP;
  const built = F.place(0, hx, hub[1], TY.SMELTER, 0);
  // look at it from the hub's side
  const w = F.tileWorld(0, hx, hub[1]);
  F.player.pos.set(w[0] - 3.4, F.HALF + 1.6, w[2] - 2.2);
  F.player.fwd.set(w[0] - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.2;
  await new Promise(r => setTimeout(r, 700));
  const look = document.getElementById('look').textContent;
  return { props: window.__game.facts().props, kinds: kinds.sort(), solid, hub, wasHab, stillThere, built, look };
});
console.log('the outpost:', s1.props, 'props', JSON.stringify(s1.kinds), '| built', s1.solid, '| by the hub', s1.wasHab, '| erase refused', s1.stillThere, '| build refused', !s1.built, '| look', JSON.stringify(s1.look));
await p.screenshot({ path: process.env.OUT || 'outpost.png' });

// 2. a blueprint round the hub copies no prop; the save carries none; a reload has them back
const s2 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, [hi, hj] = (() => { for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[0][i][j].t === TY.HUB) return [i, j]; })();
  F.captureBlueprint(0, hi - 2, hj - 1, hi + 4, hj + 1);
  const bp = F.blueprint ? F.blueprint.cells.map(c => c.t) : [];
  const inBp = bp.filter(t => t === TY.PROP).length;
  const saved = F.saveState();
  const inSave = saved.m.filter(r => r[3] === TY.PROP).length;
  F.save();
  return { bpCells: bp.length, inBp, inSave };
});
console.log('blueprint :', s2.bpCells, 'cells,', s2.inBp, 'props | save carries', s2.inSave, 'props');
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4000);
const s3 = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES;
  let hub = null; for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const hc = F.habitatOf ? F.habitatOf() : (F.cells[0][hub[0] + 2][hub[1]].t === TY.PROP ? F.cells[0][hub[0] + 2][hub[1]] : F.cells[0][hub[0] + 3][hub[1]]);
  return { props: window.__game.facts().props, byHub: hc.t === TY.PROP && hc.prop === 'habitat' };
});
console.log('reloaded  :', s3.props, 'props | habitat by the hub', s3.byHub);

// 3. a world that moved its hub: erase it, build one elsewhere, reload; the outpost stands by the new one
const s4 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let hub = null; for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  F.removeAt(0, hub[0], hub[1]);
  let spot = null;
  for (let i = 3; i < F.N - 4 && !spot; i++) for (let j = 3; j < F.N - 5 && !spot; j++)
    if (F.cells[0][i][j].t === TY.EMPTY && F.cells[0][i + 2][j].t === TY.EMPTY && Math.abs(i - hub[0]) > 4) spot = [i, j];
  F.addValue(5000);
  F.place(0, spot[0], spot[1], TY.HUB, 0);
  F.save();
  return { old: hub, spot };
});
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4000);
const s5 = await p.evaluate((spot) => {
  const F = window.__factory, TY = F.TYPES;
  let hub = null; for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const hc = F.habitatOf ? F.habitatOf() : (F.cells[0][hub[0] + 2][hub[1]].t === TY.PROP ? F.cells[0][hub[0] + 2][hub[1]] : F.cells[0][hub[0] + 3][hub[1]]);
  return { hub, props: window.__game.facts().props, byNewHub: hc.t === TY.PROP && hc.prop === 'habitat' };
}, s4.spot);
console.log('moved hub :', JSON.stringify(s4.old), '->', JSON.stringify(s5.hub), '| props', s5.props, '| habitat by the new hub', s5.byNewHub);
// 4. the supply drone: at rest on the habitat, out over the hub mid-flight, home again at the end of its day
const fly = await p.evaluate(async () => {
  const F = window.__factory, f = () => window.__game.facts().drone;
  F.droneAt(2); await new Promise(r => setTimeout(r, 300));
  const rest = f();
  F.droneAt(29); await new Promise(r => setTimeout(r, 300));
  const mid = f();
  F.droneAt(34); await new Promise(r => setTimeout(r, 300));   // mid-hover: rest 26 + out 6 = 32, hover to 36
  const hover = f();
  F.droneAt(41.9); await new Promise(r => setTimeout(r, 300));
  const home = f();
  const d = (a, b) => Math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1], a.pos[2] - b.pos[2]);
  let hub = null; const TY = F.TYPES; for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = F.tileWorld(0, i, j);
  return { rest, mid, hover, home, moved: rest && mid ? d(rest, mid) : 0, overHub: hover ? Math.hypot(hover.pos[0] - hub[0], hover.pos[2] - hub[2]) : 99, back: rest && home ? d(rest, home) : 99 };
});
console.log('the drone :', fly.rest ? 'rests on the habitat' : 'MISSING', '| moved', fly.moved.toFixed(1), 'm by mid-flight | over the hub within', fly.overHub.toFixed(2), 'm | home within', fly.back.toFixed(2), 'm');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();

const ok = s1.props === 4 && s1.kinds.join(',') === 'crates,habitat,mast,mast' && s1.solid && s1.wasHab && s1.stillThere && !s1.built
  && /HABITAT/.test(s1.look) && /crew/.test(s1.look)
  && s2.bpCells > 0 && s2.inBp === 0 && s2.inSave === 0
  && s3.props === 4 && s3.byHub
  && s5.props >= 1 && s5.byNewHub
  && fly.rest && fly.moved > 2 && fly.overHub < 0.3 && fly.back < 0.3
  && errs.length === 0;
process.exit(ok ? 0 : 1);
