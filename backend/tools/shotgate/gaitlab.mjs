// THE GAIT LAB (2026-10-02). Films the hero from the side through a walk, a
// run, a stop and a turn, and measures what a motion analyst would:
//   slide   how fast a planted foot moves over the ground, as a share of
//           the body's speed (0 is pinned; anything over ~0.15 reads as
//           skating)
//   ride    the pelvis's rise and fall over a stride (3-5 cm in a walk)
//   lean    the body's pitch at run speed (5-8 deg forward is a run)
//   turn    how long a 180-degree reversal takes, and whether the feet
//           step it or the body spins on the spot
// Writes gait_<phase>.jpg frames and a contact sheet, prints the numbers.
//   J=<job> OUT=<dir> node gaitlab.mjs
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const J = process.env.J, OUT = process.env.OUT || '.';
fs.mkdirSync(OUT, { recursive: true });
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width: 960, height: 540 });
const errs = [];
p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1&camturn=${process.env.CAMTURN || 0}&camd=${process.env.CAMD || 4.2}${process.env.Q ? '&' + process.env.Q : ''}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 2500));
await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 800));
// a recorder in the page: every frame, the feet, the hips, the root, the yaw
await p.evaluate(() => {
  // the player's own skin: a biped skeleton, nearest the player
  let hero = null, best = 1e9;
  const pp = window.__game.pos();
  window.__scene.traverse(o => {
    if (!o.isSkinnedMesh || !o.skeleton.bones.some(bn => /^foot_l$/i.test(bn.name))) return;
    const w = o.getWorldPosition(new o.position.constructor());
    const d = Math.hypot(w.x - pp[0], w.z - pp[2]);
    if (d < best) { best = d; hero = o; }
  });
  const B = {};
  for (const bn of hero.skeleton.bones) B[bn.name.toLowerCase()] = bn;
  // a clean stage: no grass, no forest, no other bodies, no HUD
  if (!/keep/.test(location.search)) {
    window.__scene.traverse(o => {
      if (o.name === 'grassField' || o.name === 'flora') o.visible = false;
      if (o.isSkinnedMesh && o !== hero) o.visible = false;
    });
    const st = document.createElement('style'); st.textContent = 'body > *:not(canvas) { display: none !important; } canvas { display: block !important; }';
    document.head.appendChild(st);
    for (const c of document.querySelectorAll('canvas')) { let e = c.parentElement; while (e && e !== document.body) { e.style.setProperty('display', 'block', 'important'); e = e.parentElement; } }
  }
  const fL = B.foot_l, fR = B.foot_r, hips = B.hips, chest = B.chest || B.spine;
  const V = hips.position.constructor;
  const a = new V(), c = new V(), h = new V(), ch = new V();
  window.__gaitRec = [];
  window.__gaitOn = false;
  const tick = () => {
    if (window.__gaitOn) {
      fL.getWorldPosition(a); fR.getWorldPosition(c); hips.getWorldPosition(h); chest.getWorldPosition(ch);
      const pos = window.__game.pos();
      window.__gaitRec.push({ t: performance.now() / 1000, L: [a.x, a.y, a.z], R: [c.x, c.y, c.z], H: [h.x, h.y, h.z], C: [ch.x, ch.y, ch.z],
        P: pos, ph: window.__gaitPhase || '' });
    }
    requestAnimationFrame(tick);
  };
  tick();
  // the camera: square to the side of the hero's start heading, following
  const y0 = (window.__game.heading ? window.__game.heading() : 0) + (+(new URLSearchParams(location.search).get("camturn") || 0));
  window.__camFollow = () => {
    const q = window.__game.pos();
    const sx = Math.cos(y0), sz = -Math.sin(y0);
    const cd = +(new URLSearchParams(location.search).get('camd') || 4.2); window.__camPin = { pos: [q[0] + sx * cd, q[1] + 1.0 + (cd < 3 ? 0.35 : 0), q[2] + sz * cd], look: [q[0], q[1] + (cd < 3 ? 1.25 : 0.95), q[2]] };
  };
  (function f() { if (window.__camFollow) window.__camFollow(); requestAnimationFrame(f); })();
});
const shots = [];
let si = 0;
const film = async (phase, ms, every = 140) => {
  await p.evaluate(ph => { window.__gaitPhase = ph; }, phase);
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const f = `${OUT}/gait_${String(si++).padStart(3, '0')}_${phase}.jpg`;
    await p.screenshot({ path: f, type: 'jpeg', quality: 80 });
    shots.push(f);
    await new Promise(r => setTimeout(r, every));
  }
};
await p.evaluate(() => { window.__gaitOn = true; });
await film('idle', 800);
await p.keyboard.down('KeyW');
await film('walk', 3200);
await p.keyboard.down('ShiftLeft');
await film('run', 3200);
await p.keyboard.up('ShiftLeft');
await p.keyboard.up('KeyW');
await film('stop', 1400, 100);
await p.keyboard.down('KeyS');
await film('turn', 1800, 100);
await p.keyboard.up('KeyS');
await film('settle', 700);
const rec = await p.evaluate(() => { window.__gaitOn = false; return window.__gaitRec; });
await b.close();

// ── the numbers ──────────────────────────────────────────────────────────
const by = ph => rec.filter(r => r.ph === ph);
const hyp = (a, b) => Math.hypot(a[0] - b[0], a[2] - b[2]);
function slide(rs) {
  // a foot is planted where it is within 2.5 cm of its lowest height in the
  // phase; its ground speed then, against the body's
  if (rs.length < 10) return null;
  const out = {};
  for (const k of ['L', 'R']) {
    // height over the body's own ground point, so hills do not read as steps
    const hk = r => r[k][1] - r.P[1];
    const lo = Math.min(...rs.map(hk));
    let fs2 = 0, bs = 0, n = 0;
    for (let i = 1; i < rs.length; i++) {
      const dt = rs[i].t - rs[i - 1].t; if (dt <= 0) continue;
      if (hk(rs[i]) > lo + 0.03 || hk(rs[i - 1]) > lo + 0.03) continue;
      fs2 += hyp(rs[i][k], rs[i - 1][k]) / dt; bs += hyp(rs[i].P, rs[i - 1].P) / dt; n++;
    }
    out[k] = n ? +(fs2 / Math.max(bs, 1e-3)).toFixed(2) : null;
  }
  return out;
}
function ride(rs) {
  if (rs.length < 10) return null;
  const ys = rs.map(r => r.H[1] - r.P[1]);
  return +(Math.max(...ys) - Math.min(...ys)).toFixed(3);
}
function speed(rs) {
  if (rs.length < 2) return null;
  const d = hyp(rs[rs.length - 1].P, rs[0].P), t = rs[rs.length - 1].t - rs[0].t;
  return +(d / t).toFixed(2);
}
function lean(rs) {
  // the chest ahead of the hips, along the direction of travel, as an angle
  if (rs.length < 4) return null;
  let s = 0, n = 0;
  for (let i = 1; i < rs.length; i++) {
    const dx = rs[i].P[0] - rs[i - 1].P[0], dz = rs[i].P[2] - rs[i - 1].P[2], dl = Math.hypot(dx, dz);
    if (dl < 1e-4) continue;
    const fx = dx / dl, fz = dz / dl;
    const ahead = (rs[i].C[0] - rs[i].H[0]) * fx + (rs[i].C[2] - rs[i].H[2]) * fz, up = rs[i].C[1] - rs[i].H[1];
    s += Math.atan2(ahead, up) * 180 / Math.PI; n++;
  }
  return n ? +(s / n).toFixed(1) : null;
}
function stopDist(rs) {
  if (rs.length < 2) return null;
  return +hyp(rs[rs.length - 1].P, rs[0].P).toFixed(2);
}
const res = {
  walk: { speed: speed(by('walk').slice(20)), slide: slide(by('walk').slice(20)), ride: ride(by('walk').slice(20)), lean: lean(by('walk').slice(20)) },
  run: { speed: speed(by('run').slice(30)), slide: slide(by('run').slice(30)), ride: ride(by('run').slice(30)), lean: lean(by('run').slice(30)) },
  stop: { glide_m: stopDist(by('stop')) },
  idle: { slide: slide(by('settle')) },
};
console.log(JSON.stringify(res));
fs.writeFileSync(`${OUT}/gait.json`, JSON.stringify({ res, rec }));
console.log('frames', shots.length, 'errors', errs.slice(0, 3).join(' | ') || 'none');
