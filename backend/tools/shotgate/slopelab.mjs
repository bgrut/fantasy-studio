// THE SLOPE LAB (2026-10-02): walks the hero across rolling ground and
// measures each planted foot's height over the terrain under it (the ankle
// should stay a few centimetres up: never buried, never hovering), with the
// gait engine on and off. Prints the spread; writes slope_*.jpg.
//   J=<job> OUT=<dir> [G=0] node slopelab.mjs
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const J = process.env.J, OUT = process.env.OUT || '.', G = process.env.G || '1';
fs.mkdirSync(OUT, { recursive: true });
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1&gait=${G}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
// find the steepest nearby line: sample the terrain around the spawn
const plan = await p.evaluate(() => {
  const h = window.__hAt, q = window.__game.pos(); let best = null;
  for (let a = 0; a < 16; a++) {
    const ang = a / 16 * Math.PI * 2, dx = Math.sin(ang), dz = Math.cos(ang);
    let rise = 0; for (let k = 1; k <= 12; k++) rise += Math.abs(h(q[0] + dx * k, q[2] + dz * k) - h(q[0] + dx * (k - 1), q[2] + dz * (k - 1)));
    if (!best || rise > best.rise) best = { ang, rise };
  }
  return best;
});
await p.evaluate(() => {
  let hero = null, best = 1e9; const pp = window.__game.pos();
  window.__scene.traverse(o => { if (!o.isSkinnedMesh || !o.skeleton.bones.some(bn => /^foot_l$/i.test(bn.name))) return; const w = o.getWorldPosition(new o.position.constructor()); const d = Math.hypot(w.x - pp[0], w.z - pp[2]); if (d < best) { best = d; hero = o; } });
  const B = {}; for (const bn of hero.skeleton.bones) B[bn.name.toLowerCase()] = bn;
  const V = hero.position.constructor, a = new V(), c = new V();
  window.__slopeRec = []; window.__slopeOn = true;
  window.__scene.traverse(o => { if (o.name === 'grassField' || o.name === 'flora') o.visible = false; });
  (function f() { if (window.__slopeOn) { B.foot_l.getWorldPosition(a); B.foot_r.getWorldPosition(c);
    window.__slopeRec.push({ l: a.y - window.__hAt(a.x, a.z), r: c.y - window.__hAt(c.x, c.z), g: window.__game.pos()[1] - window.__hAt(window.__game.pos()[0], window.__game.pos()[2]) });
    const q = window.__game.pos(), y0 = window.__game.heading ? window.__game.heading() : 0;
    window.__camPin = { pos: [q[0] + Math.cos(y0) * 3.6, q[1] + 0.8, q[2] - Math.sin(y0) * 3.6], look: [q[0], q[1] + 0.7, q[2]] }; }
    requestAnimationFrame(f); })();
});
// face the slope with the mouse yaw if the game exposes it; otherwise just walk
await p.evaluate(a => { if (window.__game.look) window.__game.look(a); }, plan.ang);
await p.keyboard.down('KeyW');
for (let i = 0; i < 10; i++) { await new Promise(r => setTimeout(r, 300)); await p.screenshot({ path: `${OUT}/slope_${i}.jpg`, type: 'jpeg', quality: 80 }); }
await p.keyboard.up('KeyW');
const rec = await p.evaluate(() => { window.__slopeOn = false; return window.__slopeRec; });
await b.close();
// the planted foot is the lower one each frame; how far is it from the ground?
const low = rec.map(r => Math.min(r.l, r.r));
low.sort((x, y) => x - y);
const q = f => +low[Math.floor(f * (low.length - 1))].toFixed(3);
const gs = rec.map(r => r.g).sort((x, y) => x - y);
console.log(JSON.stringify({ body_over_ground_p50: +gs[Math.floor(gs.length / 2)].toFixed(3), gait: G, slope_rise_12m: +plan.rise.toFixed(2), planted_foot_over_ground: { p5: q(0.05), p50: q(0.5), p95: q(0.95) }, frames: rec.length }));
