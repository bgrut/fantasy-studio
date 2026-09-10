// A played session, with real input. Keys walk, the number row picks tools,
// TAB opens the overhead, and the mouse clicks and drags on the screen where
// the tiles are — through the game's own handlers, never the seam — so a
// stuck state a player can hit is one this can hit. The one liberty taken is
// the heading: headless Chrome has no pointer lock, so the harness turns the
// player toward a target the way the mouse would and then walks with keys.
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
const facts = () => p.evaluate(() => window.__game.facts());
const step = () => p.evaluate(() => { const f = window.__game.facts().tutorial; return f ? f.step + ' ' + JSON.stringify(f.title) : 'none'; });
const face = async (tile) => p.evaluate(t => {
  const F = window.__factory, w = F.tileWorld(t.face, t.i, t.j);
  const dx = w[0] - F.player.pos.x, dz = w[2] - F.player.pos.z, d = Math.hypot(dx, dz) || 1;
  F.player.fwd.set(dx / d, 0, dz / d);
}, tile);
const screen = (tile) => p.evaluate(t => window.__factory.screenOf(t.face, t.i, t.j), tile);

await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
await p.mouse.click(640, 380);                                   // into the game
await wait(300);
const s1 = await step();

// 1. walk: hold W for a second and a half
await p.keyboard.down('KeyW'); await wait(1500); await p.keyboard.up('KeyW'); await wait(600);
let s2 = await step();
// a small world can put the line right ahead; a player would back up or turn
for (const key of ['KeyS', 'KeyD', 'KeyA']) { if (!/Look around/.test(s2)) break;
  await p.keyboard.down(key); await wait(1500); await p.keyboard.up(key); await wait(600); s2 = await step(); }

// 2. walk to the hub: face it, then W until close
const hub = await p.evaluate(() => { const F = window.__factory, TY = F.TYPES; for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[0][i][j].t === TY.HUB) return { face: 0, i, j }; return null; });
// approach the hub from its open side (opposite the belt that feeds it), the
// way a player walks round a line rather than through it; strafe when stuck
const goal = await p.evaluate(h => {
  const F = window.__factory, TY = F.TYPES;
  for (let d = 0; d < 4; d++) { const s = F.stepTile(h.face, h.i, h.j, d); if (s && F.cells[s.face][s.i][s.j].t === TY.BELT) { const o = F.stepTile(h.face, h.i, h.j, (d + 2) % 4); return o || h; } }
  return h;
}, hub);
const distTo = (tile) => p.evaluate(t => { const F = window.__factory, w = F.tileWorld(t.face, t.i, t.j); return Math.hypot(F.player.pos.x - w[0], F.player.pos.z - w[2]); }, tile);
let s3 = s2, last = await distTo(goal);
for (let k = 0; k < 40 && !/Build a rig/.test(s3); k++) {
  await face(goal); await p.keyboard.down('KeyW'); await wait(350); await p.keyboard.up('KeyW'); await wait(300);
  const now = await distTo(goal);
  if (now > last - 0.4) { const key = k % 2 ? 'KeyA' : 'KeyD'; await p.keyboard.down(key); await wait(500); await p.keyboard.up(key); await wait(200); }
  last = now;
  s3 = await step();
}

// 3. build a rig: press 1, TAB to the overhead, click the ringed seam where it is on screen
await p.keyboard.press('Digit1'); await wait(150);
await p.keyboard.press('Tab'); await wait(900);
const seam = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES;
  const m = window.__scene.getObjectByName('tutMark');
  // the ring sits on the tile it means: pick the seam nearest the ring, or,
  // if the ring is not up this frame, the free seam nearest the hub as the
  // foreman would choose it
  let ref = m && m.visible ? m.position : null;
  if (!ref) { for (let i = 0; i < F.N && !ref; i++) for (let j = 0; j < F.N && !ref; j++) if (F.cells[0][i][j].t === TY.HUB) { const w = F.tileWorld(0, i, j); ref = { x: w[0], y: w[1], z: w[2] }; } }
  let best = null, bd = 1e9;
  for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[0][i][j].t === TY.NODE) {
    const w = F.tileWorld(0, i, j); const d = Math.hypot(w[0] - ref.x, w[1] - ref.y, w[2] - ref.z);
    if (d < bd) { bd = d; best = { face: 0, i, j }; }
  }
  return best;
});
// zoom out until the seam is on the canvas, the way a player would wheel out
let sp = await screen(seam), onCanvas = false;
for (let k = 0; k < 8; k++) {
  onCanvas = await p.evaluate(s => { const el = document.elementFromPoint(s[0], s[1]); return !!el && el.tagName === 'CANVAS'; }, sp);
  if (onCanvas && sp[0] > 0 && sp[1] > 0 && sp[0] < 1280 && sp[1] < 760) break;
  await p.mouse.move(640, 380); await p.mouse.wheel({ deltaY: 120 }); await wait(250);
  sp = await screen(seam);
}
await p.mouse.click(sp[0], sp[1]); await wait(500);
const rigPlaced = await p.evaluate(t => window.__factory.cells[t.face][t.i][t.j].t === window.__factory.TYPES.MINER, seam);
const s4 = await step();

// 4. run a belt: press 2, hold the left button on the tile in front of the rig and drag two tiles;
//    then, as the card says, end it at a smelter (3) and run the smelter's output into the belt that
//    feeds the hub. Merging raw ore into the line before its smelter would not raise the rate, since
//    that smelter is already saturated; a new smelter is the whole lesson of the step.
await p.keyboard.press('Digit2'); await wait(150);
const plan = await p.evaluate(t => {
  const F = window.__factory, TY = F.TYPES;
  const rig = F.cells[t.face][t.i][t.j];
  const front = F.stepTile(t.face, t.i, t.j, rig.d);
  // two belts on from the front along the rig's heading; the smelter on the third tile
  const b1 = F.stepTile(front.face, front.i, front.j, rig.d), b2 = F.stepTile(b1.face, b1.i, b1.j, rig.d);
  const sm = F.stepTile(b2.face, b2.i, b2.j, rig.d);
  // the smelter is placed by a click and faces +i, so its output is the tile at +i
  const out = F.stepTile(sm.face, sm.i, sm.j, 0);
  // the belt that feeds the hub
  let hub = null; for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = { face: 0, i, j };
  let feed = null; for (let d = 0; d < 4 && !feed; d++) { const s = F.stepTile(hub.face, hub.i, hub.j, d); if (s && F.cells[s.face][s.i][s.j].t === TY.BELT) feed = s; }
  const dj = Math.sign(feed.j - out.j) || 1;
  const pts = [[out.i, out.j]];
  if (out.i !== feed.i) pts.push([feed.i, out.j]);
  if (Math.abs(feed.j - out.j) > 1) pts.push([feed.i, feed.j - dj]);
  return { front, b2, sm, out, feed, pts, clear: [b1, b2, sm, out].every(x => x && F.cells[x.face][x.i][x.j].t === TY.EMPTY) };
}, seam);
const A = await screen(plan.front), B = await screen(plan.b2);
await p.mouse.move(A[0], A[1]); await p.mouse.down(); await p.mouse.move(B[0], B[1], { steps: 20 }); await p.mouse.up(); await wait(400);
await p.keyboard.press('Digit3'); await wait(150);
const S = await screen(plan.sm); await p.mouse.click(S[0], S[1]); await wait(400);
await p.keyboard.press('Digit2'); await wait(150);
const way = [];
for (const [i, j] of plan.pts) way.push(await screen({ face: 0, i, j }));
await p.mouse.move(way[0][0], way[0][1]); await p.mouse.down();
for (const w of way.slice(1)) await p.mouse.move(w[0], w[1], { steps: 30 });
await p.mouse.up(); await wait(600);
const belts = await p.evaluate(() => { const F = window.__factory, TY = F.TYPES; let n = 0; F.cells.forEach(f => f.forEach(c => c.forEach(x => { if (x.t === TY.BELT) n++; }))); return n; });
// where does the new line lead? walk the belts from the rig's front, and from the new smelter's output
const chain = await p.evaluate(([t, sm]) => {
  const F = window.__factory, TY = F.TYPES, names = { [TY.EMPTY]: 'empty', [TY.BELT]: 'belt', [TY.SMELTER]: 'smelter', [TY.HUB]: 'hub', [TY.MINER]: 'miner', [TY.NODE]: 'seam' };
  const walk = (from) => { let cur = from, n = 0, seen = new Set();
    while (cur && n < 60) { const c = F.cells[cur.face][cur.i][cur.j]; const key = cur.face + ':' + cur.i + ':' + cur.j;
      if (c.t !== TY.BELT || seen.has(key)) return { steps: n, ends: names[c.t] || c.t };
      seen.add(key); n++; cur = F.stepTile(cur.face, cur.i, cur.j, c.d); }
    return { steps: n, ends: 'edge' }; };
  const smelterPlaced = F.cells[sm.face][sm.i][sm.j].t === TY.SMELTER;
  return { fromRig: walk(F.stepTile(t.face, t.i, t.j, F.cells[t.face][t.i][t.j].d)), fromSmelter: walk(F.stepTile(sm.face, sm.i, sm.j, 0)), smelterPlaced };
}, [seam, plan.sm]);
const s5 = await step();

// 5. the finish step clears on its own once the new ore sells: back to first person and wait
await p.keyboard.press('Tab'); await wait(300);
let s6 = s5, waited = 0;
while (waited < 40000 && !/Read the panel/.test(s6)) { await wait(2000); waited += 2000; s6 = await step(); }
const rate = await p.evaluate(() => window.__game.facts().rate_now);

// 6. Enter clears the last card; the foreman steps back
await p.keyboard.press('Enter'); await wait(400);
const done = await p.evaluate(() => ({ tutorial: window.__game.facts().tutorial, card: document.getElementById('tutor').classList.contains('on'),
                                       toast: document.getElementById('toast').textContent, machines: window.__game.facts().machines }));
// and "the guide" in the panel brings it back
await p.evaluate(() => document.getElementById('guide').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })));
await wait(400);
const again = await step();

console.log('steps     :', s1, '->', s2, '->', s3, '->', s4, '->', s5, '->', s6);
console.log('built     : seam on the canvas', onCanvas, 'at', sp.slice(0, 2).map(Math.round), '| rig placed by a click', rigPlaced, '| smelter placed', chain.smelterPlaced, '| belts', belts, '| rig -> ' + chain.fromRig.steps + ' belts -> ' + chain.fromRig.ends + ', smelter -> ' + chain.fromSmelter.steps + ' belts -> ' + chain.fromSmelter.ends, '| rate when the line paid', rate, '| waited', waited / 1000 + 's');
console.log('the end   : tutorial', JSON.stringify(done.tutorial), '| card up', done.card, '| machines', done.machines, '| said:', JSON.stringify(done.toast).slice(0, 70));
console.log('the guide : replays ->', again);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'play.png' });
await b.close();

const ok = /Look around/.test(s1) && /This is a line/.test(s2) && /Build a rig/.test(s3) && rigPlaced && /Run a belt/.test(s4)
  && /Finish the line|Read the panel/.test(s5) && belts >= 6 && /Read the panel/.test(s6)   // the line can pay before the harness looks
  && done.tutorial === null && !done.card && /steps back/.test(done.toast) && /Look around/.test(again)
  && errs.length === 0;
process.exit(ok ? 0 : 1);
