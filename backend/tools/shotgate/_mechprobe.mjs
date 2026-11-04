// Do the designer's new mechanics work when played? J=job_N [OUT=shot.jpg] node _mechprobe.mjs
// Reads window.__design(), then drives the one this game has and prints what changed:
//   watch      stand in a sweeping light: seen rises, you are caught and sent back
//   breath     walk the climb: breath falls; stop by a cairn: it comes back
//   load       take a thing: the basket fills and the stride shortens; go home: it empties
//   resonance  walk to the thing sought: the distance falls and the pulse quickens
//   trouble    wait for the smoke; stand at it: seen to
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await w(500); }
await w(4000); await p.click('#startbtn').catch(() => {});
// (the opening freeze can last 20 s: play only once frames flow)
const t0 = Date.now();
await p.evaluate(() => new Promise(res => { let n = 0, last = performance.now(); const f = () => { const t = performance.now(); n = t - last < 100 ? n + 1 : 0; last = t; if (n >= 20) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); }));
const flowMs = Date.now() - t0; await w(1500);
const D = () => p.evaluate(() => window.__design());
const pos = () => p.evaluate(() => window.__game.pos());
const d0 = await D(); const out = { mechanic: d0.mechanic, flowMs, start: d0 };
// (a teleport lands on the next step the hero takes: stood still, the body stays put, so tap forward)
const tp = async (x, z) => { await p.evaluate((x, z) => window.__game.tp(x, z), x, z); await p.keyboard.down('KeyW'); await w(400); await p.keyboard.up('KeyW'); };
const M = d0.mechanic;
if (M === 'watch') {
  const home = await pos();
  // stand on a light's line and let it sweep over: the middle of the way, then every light in turn
  const path = await p.evaluate(() => window.__spec.world.level.path);
  const pools = await p.evaluate(() => { const r = []; window.__scene.traverse(o => { if (o.isMesh && o.geometry.type === 'CircleGeometry' && o.renderOrder === 3) r.push([o.position.x, o.position.z]); }); return r; });
  out.pools = pools.length; out.seenPeak = 0;
  for (let t = 0; t < 40; t++) {
    const q = await p.evaluate(() => { let c = null; window.__scene.traverse(o => { if (!c && o.isMesh && o.geometry.type === 'CircleGeometry' && o.renderOrder === 3) c = [o.position.x, o.position.z]; }); return c; });
    if (q) await tp(q[0], q[1]);
    await w(250);
    const s = await D(); out.seenPeak = Math.max(out.seenPeak, s.watch.seen);
    if (s.watch.caught) { out.caught = s.watch.caught; out.after = await pos(); break; }
  }
  out.home = home; void path;
} else if (M === 'breath') {
  const path = await p.evaluate(() => window.__spec.world.level.path);
  const k = Math.min(path.length - 1, Math.floor(path.length / 2));
  out.heightMid = await p.evaluate((a, b) => window.__hAt(a, b), path[k][0], path[k][1]);
  // walk up the way a stretch at a time
  await p.keyboard.down('ShiftLeft');
  for (let i = 1; i <= k; i++) { await tp(path[i][0], path[i][1]); await w(350); }
  await p.keyboard.up('ShiftLeft');
  const a = await D(); out.breathAfterClimb = a.breath.breath;
  const c = await p.evaluate(() => { const r = []; window.__scene.traverse(o => { if (o.name === 'designCairns') { const M4 = new o.matrixWorld.constructor(); o.getMatrixAt(0, M4); r.push(M4.elements[12], M4.elements[14]); } }); return r; });
  if (c.length) { await tp(c[0], c[1]); await w(3500); const e = await D(); out.breathAtCairn = e.breath.breath; }
  out.cairns = a.breath.cairns;
} else if (M === 'load') {
  const pts = await p.evaluate(() => window.__spec.world.level.collect_points);
  out.points = pts.length;
  for (const q of pts.slice(0, 2)) { await tp(q[0], q[1]); await w(1600); }
  const a = await D(); out.loadAfter = a.load;
  const home = await p.evaluate(() => [0, 0]);
  await tp(home[0], home[1]); await w(1200);
  const e = await D(); out.loadHome = e.load;
} else if (M === 'resonance') {
  const a = await D(); out.dFar = a.resonance.d;
  const t = await p.evaluate(() => { const L = window.__spec.world.level; return (L.collect_points && L.collect_points[0]) || L.goal; });
  await tp(t[0] + 6, t[1] + 3); await w(1500);
  const e = await D(); out.dNear = e.resonance.d;
  out.word = await p.evaluate(() => { const s = document.querySelector('.fs-reson span'); return s && s.textContent; });
} else if (M === 'trouble') {
  for (let i = 0; i < 60; i++) { const s = await D(); if (s.trouble.live) { out.live = s.trouble.live; break; } await w(1000); }
  if (out.live) { await tp(out.live.at[0], out.live.at[1]); await w(1200); out.after = (await D()).trouble; }
} else if (M === 'lantern') {
  const a = await D(); out.lantern = a.lantern;
  const l = await p.evaluate(() => window.__spec.world.level.path);
  for (let i = 1; i < l.length - 1; i++) { await tp((l[i - 1][0] + l[i][0]) / 2 + 1.8, (l[i - 1][1] + l[i][1]) / 2 + 1.2); await w(500); }
  out.after = (await D()).lantern;
}
if (process.env.OUT) await p.screenshot({ path: process.env.OUT, type: 'jpeg', quality: 85 });
out.errors = errs;
console.log(JSON.stringify(out));
await b.close();
