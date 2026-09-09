// Depletion. A seam has to thin while a rig works it, grow back when it does
// not, get visibly SMALLER as it thins, and remember all of that across a
// reload — a mechanic that resets when you close the tab is a mechanic that
// only exists for one sitting.
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
await p.goto(URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

// 1. the starter line's rig is on a seam: it should be thinning right now
const work = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let seam = null;
  F.cells.forEach((face, f) => face.forEach((col, i) => col.forEach((c, j) => {
    if (c.t === TY.MINER && c.mesh && !seam) seam = { f, i, j };
  })));
  if (!seam) return { skipped: 'no rig on a seam' };
  const c = F.cells[seam.f][seam.i][seam.j];
  const r0 = c.rich, s0 = c.mesh.scale.x, e0 = c.mesh.material.emissiveIntensity;
  const core = c.mesh.children[0], k0 = core ? core.scale.x : null;
  // speed the clock up rather than waiting a minute: every tick is a chance to
  // extract, so run the sim forward directly
  for (let k = 0; k < 90; k++) F.step();
  await new Promise(r => setTimeout(r, 400));
  return { seam, before: +r0.toFixed(3), after: +c.rich.toFixed(3),
           scaleBefore: +s0.toFixed(3), scaleAfter: +c.mesh.scale.x.toFixed(3),
           // a seam is a light: its glow, its core and its pool follow the richness
           glowBefore: +e0.toFixed(2), glowAfter: +c.mesh.material.emissiveIntensity.toFixed(2),
           coreBefore: k0 && +k0.toFixed(2), coreAfter: core && +core.scale.x.toFixed(2),
           pool: c.glow !== undefined, ownMaterial: c.mesh.material !== F.cells[seam.f][seam.i][seam.j].mesh.material || true };
});
console.log('worked    : rich', work.before, '->', work.after,
            '| seam scale', work.scaleBefore, '->', work.scaleAfter,
            '| glow', work.glowBefore, '->', work.glowAfter, '| core', work.coreBefore, '->', work.coreAfter,
            '| pool', work.pool);

// 2. take the rig away and it grows back
const regrow = await p.evaluate(async (seam) => {
  const F = window.__factory;
  const c = F.cells[seam.f][seam.i][seam.j];
  F.removeAt(seam.f, seam.i, seam.j);
  const r0 = c.rich;
  await new Promise(r => setTimeout(r, 2500));
  return { before: +r0.toFixed(3), after: +c.rich.toFixed(3),
           expected: +(r0 + 2.5 * F.SEAM_REGROW).toFixed(3) };
}, work.seam);
console.log('resting   : rich', regrow.before, '->', regrow.after,
            '(expected about', regrow.expected + ')');

// 3. the trickle never dies: a seam worked flat still yields sometimes
const floor = await p.evaluate(async (seam) => {
  const F = window.__factory, TY = F.TYPES;
  const c = F.cells[seam.f][seam.i][seam.j];
  c.rich = 0;
  F.place(seam.f, seam.i, seam.j, TY.MINER, F.cells[seam.f][seam.i][seam.j].d || 0);
  // count what the miner actually extracts over many ticks at zero richness
  const out = F.stepTile(seam.f, seam.i, seam.j, c.d);
  let got = 0;
  for (let k = 0; k < 200; k++) {
    const dst = F.cells[out.face][out.i][out.j];
    dst.item = 0;                    // keep the outlet clear
    F.step();
    if (dst.item) got++;
  }
  return { got, floor: F.SEAM_FLOOR };
}, work.seam);
console.log('at zero   :', floor.got, 'of 200 ticks yielded (floor', floor.floor + ')');

// 4. and it survives a reload
await p.evaluate(()=>window.__factory.save());
await p.goto(URL, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,5500));
const back = await p.evaluate((seam) => {
  const F = window.__factory;
  return { rich: +F.cells[seam.f][seam.i][seam.j].rich.toFixed(3),
           restored: window.__game.facts().restored };
}, work.seam);
console.log('reloaded  : restored', back.restored, '| that seam is at', back.rich);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'deplete.png' });
await b.close();
const ok = work.glowAfter < work.glowBefore && work.coreAfter < work.coreBefore && work.pool
  && !work.skipped
  && work.after < work.before - 0.2                 // 90 ticks took a real bite
  && work.scaleAfter < work.scaleBefore             // and it is visibly smaller
  && regrow.after > regrow.before                   // it grows back on its own
  && floor.got > 8 && floor.got < 60                // a trickle, not dead, not full
  && back.restored && back.rich < 0.6               // and the reload remembers it
  && errs.length === 0;
process.exit(ok ? 0 : 1);
