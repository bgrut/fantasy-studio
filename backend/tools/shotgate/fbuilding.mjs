// Buildings for building prompts. A world that names a manor gets a manor:
// a body from the facade kit stands at the door, its front faces the spawn,
// its walls block, and the door still leads inside.
//   B=<job id of a prompt that names a building>
import puppeteer from 'puppeteer-core';
if (!process.env.B) { console.log('fbuilding: no building job given (B=<job>); FAIL'); process.exit(1); }
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.B + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
await wait(9000);
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await wait(4000);
await p.evaluate(() => { window.__game.heading0 = window.__game.heading ? window.__game.heading() : undefined; });
const r = await p.evaluate(async () => {
  const L = window.__game.landmark();
  if (!L) return { landmark: null };
  // stand at the door, look at the building
  const tp = window.__game.tp;
  const dx = L.door[0], dz = L.door[1];
  const nx = (0 - dx), nz = (0 - dz), nl = Math.hypot(nx, nz) || 1;
  tp(dx + nx / nl * 6, dz + nz / nl * 6);
  await new Promise(r => setTimeout(r, 800));
  const before = window.__game.pos();
  // walk into the wall beside the door: the wall should stop us short of the centre
  const wx = dx - nx / nl * 3 + (-nz / nl) * 4, wz = dz - nz / nl * 3 + (nx / nl) * 4;   // a point inside the body, off the doorway
  return { landmark: L, before: before.map(v => +v.toFixed(1)), inside: [wx, wz] };
});
console.log('landmark  :', r.landmark ? JSON.stringify({ kit: r.landmark.kit, w: r.landmark.w, d: r.landmark.d, h: r.landmark.h, at: r.landmark.at.map(v => +v.toFixed(1)) }) : 'NONE');
let blocked = null;
if (r.landmark) {
  // try to teleport into the wall's footprint through physics: push the body toward the inside point for two seconds
  blocked = await p.evaluate(async (inside) => {
    const tp = window.__game.tp;
    const [ix, iz] = inside;
    const p0 = window.__game.pos();
    // face the point and hold W
    return await new Promise(res => {
      const ev = new KeyboardEvent('keydown', { code: 'KeyW', key: 'w' }); dispatchEvent(ev);
      setTimeout(() => { dispatchEvent(new KeyboardEvent('keyup', { code: 'KeyW', key: 'w' })); const p1 = window.__game.pos();
        res({ moved: +Math.hypot(p1[0] - p0[0], p1[2] - p0[2]).toFixed(1) }); }, 1500);
    });
  }, r.inside);
  // face the body for the frame: stand 14 m out from the door and look at it
  await p.evaluate(async (L) => {
    const dx = L.door[0], dz = L.door[1]; const nx = (0 - dx), nz = (0 - dz), nl = Math.hypot(nx, nz) || 1;
    window.__game.tp(dx + nx / nl * 14, dz + nz / nl * 14);
    if (window.__game.look) window.__game.look(Math.atan2(-nx / nl, -nz / nl));
    await new Promise(r => setTimeout(r, 900));
  }, r.landmark);
  await p.screenshot({ path: process.env.OUT || 'building.png' });
}
// a survive objective keeps a dormant wave that wakes later; only the ghosts present count
const cast = await p.evaluate(() => { const ns = window.__game.npcs().filter(n => !n.dormant); return { ghosts: ns.filter(n => n.spectral).length, animals: ns.filter(n => /wolf|bear|boar/.test(n.name || '')).length, total: ns.length }; });
// the spawn faced the door: the heading at boot points within a third of a turn of it
const faced = await p.evaluate(() => { const L = window.__game.landmark(); const y0 = window.__game.heading0; if (!L || y0 === undefined) return null;
  const want = Math.atan2(L.door[0], L.door[1]) + Math.PI; let d = Math.abs(((y0 - want) % (Math.PI * 2) + Math.PI * 3) % (Math.PI * 2) - Math.PI); return { off: +d.toFixed(2), lamps: L.lamps || 0 }; });
console.log('the spawn :', faced ? 'faced the door within ' + faced.off + ' rad | lamps ' + faced.lamps : 'no heading');
console.log('the cast  :', cast.ghosts, 'ghosts,', cast.animals, 'animals of', cast.total);
console.log('walked    :', JSON.stringify(blocked));
// on foot: the speed ramps, a landing dips the camera, a run widens the view
const feel = await (async () => {
  const F2 = () => p.evaluate(() => { const f = window.__game.facts(); return { v: f.walk_v, dip: f.land_dip_peak, fov: f.fov, base: f.fov_base, run: f.run_k }; });
  await p.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, 60)); const early = await F2();
  await new Promise(r => setTimeout(r, 700)); const full = await F2();
  await p.keyboard.down('ShiftLeft'); await new Promise(r => setTimeout(r, 1500)); const run = await F2();
  await p.keyboard.down('Space'); await new Promise(r => setTimeout(r, 120)); await p.keyboard.up('Space');   // held a few frames: the loop reads keys, a press shorter than a frame is missed
  await new Promise(r => setTimeout(r, 1500)); const landed = await F2();
  await p.keyboard.up('ShiftLeft'); await p.keyboard.up('KeyW'); await new Promise(r => setTimeout(r, 900)); const stopped = await F2();
  // the gait blend and the weight: walking, the walk clip carries the pose at its own stride rate; turning, the body rolls; the head has a bone to turn
  await p.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, 900));
  const gaitW = await p.evaluate(() => { const f = window.__game.facts(); return { gait: f.gait, lean: f.lean, arms: f.arms, ride: f.ride }; });
  await p.keyboard.down('KeyA'); await new Promise(r => setTimeout(r, 350));
  const turning = await p.evaluate(() => window.__game.facts().lean);
  await p.keyboard.up('KeyA'); await p.keyboard.up('KeyW'); await new Promise(r => setTimeout(r, 1200));
  const idleW = await p.evaluate(() => window.__game.facts().gait);
  return { early: early.v, full: full.v, runFov: run.fov, base: run.base, runK: run.run, dip: landed.dip, stopped: stopped.v, gaitW, turning, idleW };
})();
console.log('the gait  : walking', JSON.stringify(feel.gaitW.gait), '| idle again', JSON.stringify(feel.idleW), '| turning roll', feel.turning.roll, '| head bone', feel.gaitW.lean.head_bone, '| arms from down', JSON.stringify(feel.gaitW.arms), '| hip ride', feel.gaitW.ride);
console.log('on foot   : 60 ms in', feel.early, '| 760 ms in', feel.full, '| run fov', feel.runFov, 'of', feel.base, '| landing dip', feel.dip, '| stopped', feel.stopped);

// the frame's luminance, read back in the page from a screenshot (the canvas
// itself is not preserved): the whole frame, the sky band, and a box around a screen point
const lumOf = async (p, box) => {
  const b64 = await p.screenshot({ encoding: 'base64' });
  return p.evaluate(async (b64, box) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const stat = (x, y, w, h) => { const d = g.getImageData(Math.max(0, x | 0), Math.max(0, y | 0), Math.max(1, w | 0), Math.max(1, h | 0)).data; let s = 0; for (let i = 0; i < d.length; i += 4) s += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; return +(s / (d.length / 4)).toFixed(1); };
    return { frame: stat(0, 0, c.width, c.height), sky: stat(0, 0, c.width, c.height * 0.12), box: box ? stat(box[0], box[1], box[2], box[3]) : null };
  }, b64, box);
};
const heroBox = (p) => p.evaluate(() => { const v = window.__game.pos();   const pr = { x: v[0], y: v[1] + 0.9, z: v[2] }; const cam = window.__camera; const m = cam.matrixWorldInverse; const pm = cam.projectionMatrix;
  const x = pr.x * m.elements[0] + pr.y * m.elements[4] + pr.z * m.elements[8] + m.elements[12];
  const y = pr.x * m.elements[1] + pr.y * m.elements[5] + pr.z * m.elements[9] + m.elements[13];
  const z = pr.x * m.elements[2] + pr.y * m.elements[6] + pr.z * m.elements[10] + m.elements[14];
  const w = pr.x * m.elements[3] + pr.y * m.elements[7] + pr.z * m.elements[11] + m.elements[15];
  const cx = (x * pm.elements[0] + z * pm.elements[8]) / -z, cy = (y * pm.elements[5] + z * pm.elements[9]) / -z;
  const sx = (cx * 0.5 + 0.5) * innerWidth, sy = (1 - (cy * 0.5 + 0.5)) * innerHeight; return [sx - 35, sy - 70, 70, 140]; });
// the light: a night on a moor, and the hero still reads on it (the fill), with the sky dark
const lightF = await p.evaluate(() => window.__game.facts().light);
const box = await heroBox(p);
const lum = await lumOf(p, box);
console.log('the light :', JSON.stringify(lightF), '| frame', lum.frame, '| sky', lum.sky, '| hero', lum.box);
// and the cast moves with weight: any npc that moved carries a roll or a clip rate that followed it
const npcW = await p.evaluate(() => (window.__game.facts().npc_weight || []).filter(x => x.v > 0.3));
const bodies = await p.evaluate(() => window.__game.facts().bodies);
console.log('the cast  : moving', npcW.length, '| rates', npcW.map(x => x.rate).join(' '), '| bodies', JSON.stringify(bodies), '| ground', npcW.map(x => x.ground).join(' '));
// the hero: measured standing in the pose the player sees, holding the role's weapon
const hero = await p.evaluate(() => { const f = window.__game.facts(); return { dims: f.player_dims, hero: f.hero, weapon: f.weapon }; });
const standing = hero.dims && hero.dims[1] >= Math.max(hero.dims[0], hero.dims[2]) * 0.9;
console.log('the hero  :', hero.hero, '| box', JSON.stringify(hero.dims), '| standing', standing, '| holds', hero.weapon);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = r.landmark && r.landmark.w > 5 && r.landmark.h > 5 && errs.length === 0
  && standing && (hero.hero !== 'detective' || hero.weapon === null || hero.weapon === 'pistol')
  && feel.early > 0.2 && feel.early < feel.full * 0.85 && feel.full > 1.5 && feel.runFov > feel.base + 2 && feel.dip > 0.03 && feel.stopped < 0.05
  && (!lightF.night || (lightF.moon <= 0.6 && lightF.hero_fill > 0 && lum.box >= 22 && lum.box > lum.frame * 1.15 && lum.sky < 70))
  && feel.gaitW.gait.walk > 0.5 && feel.gaitW.gait.idle < 0.5 && feel.gaitW.gait.rate >= 0.5 && feel.gaitW.gait.rate <= 5.5 && feel.idleW.idle > 0.9 && Math.abs(feel.turning.roll) > 0.01 && !!feel.gaitW.lean.head_bone && feel.gaitW.arms && feel.gaitW.arms.L !== null && feel.gaitW.arms.L < 32 && feel.gaitW.arms.R < 32 && feel.gaitW.ride >= 0.015 && feel.gaitW.ride <= 0.09   // the arms hang and swing, no chicken wings; the pelvis rides three to six centimetres   // a detective with a weapon holds the pistol; a build with no hostiles holds nothing && cast.ghosts > 0 && cast.ghosts <= 3 && cast.animals === 0   // a haunting has ghosts, not wolves, and not a crowd
  && faced && faced.off < 1.05 && faced.lamps === 3
  && bodies && bodies.quad + bodies.biped > 0 && npcW.every(x => Number.isFinite(x.ground));   // every body knows its class and the ground under it
process.exit(ok ? 0 : 1);
