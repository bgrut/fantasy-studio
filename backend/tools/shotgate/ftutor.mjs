// The foreman and the look label. A new survival world has to open on step
// one with no tool in hand; each step has to clear on the thing it asks for
// and put the next tool in your hand; the ring has to sit on the tile the
// step means; skipping and finishing have to stick across a reload; creative
// and shared worlds have no foreman; and pointing at a machine has to name it.
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

// 1. opens on step one, no tool in hand, no ghost; walking clears it
const s1 = await p.evaluate(async () => {
  const F = window.__factory, f = window.__game.facts();
  const card = document.getElementById('tutor');
  const before = { step: f.tutorial && f.tutorial.step, title: f.tutorial && f.tutorial.title, on: card.classList.contains('on'),
                   tool: F.tool, ghost: F.ghostVisible(), toolOn: !!document.querySelector('.tool.on') };
  // walk: four metres along the face
  const u = F.FACES[F.player.face].u;
  F.player.pos.x += u[0] * 4.2; F.player.pos.y += u[1] * 4.2; F.player.pos.z += u[2] * 4.2;
  await new Promise(r => setTimeout(r, 600));
  const g = window.__game.facts();
  return { before, after: { step: g.tutorial && g.tutorial.step, title: g.tutorial && g.tutorial.title, marker: g.tutorial && g.tutorial.marker } };
});
console.log('step 1    :', JSON.stringify(s1.before));
console.log('walked    :', JSON.stringify(s1.after));

// 2. the line step: ring on the hub; standing by it clears; step 3 hands you the rig
const s3 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let hub = null; for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const mark = window.__scene.getObjectByName('tutMark');
  const hw = F.tileWorld(0, hub[0], hub[1]);
  const ringOnHub = mark && mark.visible && Math.hypot(mark.position.x - hw[0], mark.position.z - hw[2]) < 1.0;
  const w = F.tileWorld(0, hub[0], hub[1] - 1);
  F.player.pos.set(w[0], F.HALF + 1.6, w[2]);
  await new Promise(r => setTimeout(r, 3200));          // the step is read before it clears
  const g = window.__game.facts();
  return { ringOnHub, step: g.tutorial && g.tutorial.step, title: g.tutorial && g.tutorial.title, tool: F.tool,
           hint: !!document.querySelector('.tool.hint[data-tool="miner"]') };
});
console.log('the line  : ring on the hub', s3.ringOnHub, '| by the hub -> step', s3.step, JSON.stringify(s3.title), '| tool in hand', s3.tool, '| miner chip pulsing', s3.hint);

// 3. build the rig on the marked seam -> step 4, belt in hand; run the belt -> step 5
const s5 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const mark = window.__scene.getObjectByName('tutMark');
  // the seam under the ring
  let seam = null, bd = 1e9;
  for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) { const c = F.cells[0][i][j]; if (c.t !== TY.NODE) continue;
    const w = F.tileWorld(0, i, j); const d = Math.hypot(mark.position.x - w[0], mark.position.z - w[2]); if (d < bd) { bd = d; seam = [i, j]; } }
  if (!seam) return { onSeam: false, s4: { step: null, tool: F.tool, hint: false }, step: null, title: 'no free seam on the top face' };
  const onSeam = bd < 1.0;
  F.place(0, seam[0], seam[1], TY.MINER, 0);
  await new Promise(r => setTimeout(r, 600));
  const g4 = window.__game.facts();
  const s4 = { step: g4.tutorial && g4.tutorial.step, tool: F.tool, hint: !!document.querySelector('.tool.hint[data-tool="belt"]') };
  // the belt from the rig's front, two tiles
  const front = F.stepTile(0, seam[0], seam[1], 0);
  F.place(front.face, front.i, front.j, TY.BELT, 0);
  const next = F.stepTile(front.face, front.i, front.j, 0);
  if (next && F.cells[next.face][next.i][next.j].t === TY.EMPTY) F.place(next.face, next.i, next.j, TY.BELT, 0);
  await new Promise(r => setTimeout(r, 600));
  const g5 = window.__game.facts();
  return { onSeam, s4, step: g5.tutorial && g5.tutorial.step, title: g5.tutorial && g5.tutorial.title };
});
console.log('the rig   : ring was on a seam', s5.onSeam, '| rig built -> step', s5.s4.step, '| belt in hand', s5.s4.tool, '| belt chip pulsing', s5.s4.hint);
console.log('the belt  : run from the rig -> step', s5.step, JSON.stringify(s5.title));

// 4. the rate rising clears the line step; got it ends the guide; a reload keeps it ended
const done = await p.evaluate(async () => {
  const F = window.__factory;
  F.rateNow = 500; await new Promise(r => setTimeout(r, 700)); F.rateNow = null;
  const g6 = window.__game.facts();
  const gotit = document.querySelector('#tutor .skip').textContent;
  document.querySelector('#tutor .skip').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 300));
  const g = window.__game.facts();
  return { step6: g6.tutorial && g6.tutorial.step, gotit, after: g.tutorial, cardOn: document.getElementById('tutor').classList.contains('on'),
           tool: F.tool, toast: document.getElementById('toast').textContent };
});
console.log('the rate  : rising -> step', done.step6, '| button reads', JSON.stringify(done.gotit), '| after: tutorial', JSON.stringify(done.after),
            '| card on', done.cardOn, '| tool', done.tool, '| said:', JSON.stringify(done.toast).slice(0, 70));
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4000);
const back = await p.evaluate(() => ({ tutorial: window.__game.facts().tutorial, cardOn: document.getElementById('tutor').classList.contains('on') }));
console.log('reloaded  : tutorial', JSON.stringify(back.tutorial), '| card on', back.cardOn);

// 5. creative has no foreman; the look label names what you point at
await p.goto(URL + q + 'creative=1&fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4000);
const look = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const none = window.__game.facts().tutorial;
  let sm = null; for (let i = 0; i < F.N && !sm; i++) for (let j = 0; j < F.N && !sm; j++) if (F.cells[0][i][j].t === TY.SMELTER) sm = [i, j];
  const wp = F.tileWorld(0, sm[0], sm[1] + 2), lk = F.tileWorld(0, sm[0], sm[1]);
  F.player.pos.set(wp[0], F.HALF + 1.6, wp[2]); F.player.face = 0;
  const dx = lk[0] - wp[0], dz = lk[2] - wp[2], d = Math.hypot(dx, dz);
  F.player.fwd.set(dx / d, 0, dz / d); F.player.pitch = -Math.atan2(1.6, d);
  await new Promise(r => setTimeout(r, 700));
  const smelter = window.__game.facts().look;
  // and a seam: one with two clear tiles to stand on beside it, tried in turn
  let seamLabel = null;
  const cands = [];
  for (let i = 1; i < F.N - 1; i++) for (let j = 1; j < F.N - 3; j++)
    if (F.cells[0][i][j].t === TY.NODE && F.cells[0][i][j + 1].t === TY.EMPTY && F.cells[0][i][j + 2].t === TY.EMPTY) cands.push([i, j]);
  for (const seam of cands.slice(0, 5)) {
    const sw = F.tileWorld(0, seam[0], seam[1] + 2), sl = F.tileWorld(0, seam[0], seam[1]);
    F.player.pos.set(sw[0], F.HALF + 1.6, sw[2]);
    const ex = sl[0] - sw[0], ez = sl[2] - sw[2], e = Math.hypot(ex, ez);
    F.player.fwd.set(ex / e, 0, ez / e); F.player.pitch = -Math.atan2(1.6, e);
    await new Promise(r => setTimeout(r, 600));
    seamLabel = window.__game.facts().look;
    if (seamLabel && /SEAM/.test(seamLabel)) break;
  }
  return { none, smelter, seam: seamLabel, creative: window.__game.facts().creative };
});
console.log('creative  : tutorial', JSON.stringify(look.none), '| creative', look.creative);
console.log('the look  : smelter ->', JSON.stringify(look.smelter), '| seam ->', JSON.stringify(look.seam));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'tutor.png' });
await b.close();

const ok = s1.before.step === 1 && s1.before.on && s1.before.tool === null && !s1.before.ghost && !s1.before.toolOn
  && s1.after.step === 2 && s1.after.marker
  && s3.ringOnHub && s3.step === 3 && s3.tool === 'miner' && s3.hint
  && s5.onSeam && s5.s4.step === 4 && s5.s4.tool === 'belt' && s5.s4.hint && s5.step === 5
  && done.step6 === 6 && done.gotit === 'got it' && done.after === null && !done.cardOn && !!done.tool && /foreman steps back/.test(done.toast)
  && back.tutorial === null && !back.cardOn
  && look.none === null && look.creative && /^SMELTER/.test(look.smelter || '') && /SEAM/.test(look.seam || '') && /rich/.test(look.seam || '')
  && errs.length === 0;
process.exit(ok ? 0 : 1);
