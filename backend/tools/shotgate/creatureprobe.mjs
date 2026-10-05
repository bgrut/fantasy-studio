// How the creatures move: for every live, moving NPC over four seconds, the
// angle between where its body points and where it travels, its speed, its
// clip's play rate, and how far its lowest bone sits off the ground.
// A quadruped's body points from tail bone to neck bone; a biped's from its
// heels to its toes is not measurable here, so bipeds report travel only.
//   J=job_N [OUT=<dir>] node creatureprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1400,800'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await p.evaluate(() => { window.__cbt.iframes = 1e9; });
const sample = () => p.evaluate(() => {
  const V = window.__scene.position.constructor;
  return window.__game.npcRefs().filter(n => !n.dead && !n.dormant && !n.gone).map((n, i) => {
    const bones = {};
    n.obj.traverse(o => { if (o.isBone && !bones[o.name]) bones[o.name] = o; });
    let face = null;
    if (bones.neck && bones.tail) {
      const a = bones.neck.getWorldPosition(new V()), t = bones.tail.getWorldPosition(new V());
      face = Math.atan2(a.x - t.x, a.z - t.z);
    }
    let low = 1e9;
    for (const k in bones) low = Math.min(low, bones[k].getWorldPosition(new V()).y);
    return { i, name: n.name, beh: n.behavior, quad: !!n.quad, x: n.obj.position.x, y: n.obj.position.y, z: n.obj.position.z,
             yaw: n.obj.rotation.y, face, low: low === 1e9 ? null : low, rate: n.anim && n.anim.cur ? n.anim.cur.timeScale : null,
             clip: n.anim && n.anim.cur ? n.anim.cur.getClip().name : null, h: n.h || null };
  });
});
const a = await sample();
await new Promise(r => setTimeout(r, 2000));
const c = await sample();
const rows = [];
for (const s1 of c) {
  const s0 = a.find(q => q.i === s1.i && q.name === s1.name);
  if (!s0) continue;
  const dx = s1.x - s0.x, dz = s1.z - s0.z, sp = Math.hypot(dx, dz) / 2;
  const travel = Math.atan2(dx, dz);
  const off = (ang) => { let d = ang - travel; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI; return Math.round(Math.abs(d) * 180 / Math.PI); };
  rows.push({ name: s1.name, beh: s1.beh, quad: s1.quad, speed: +sp.toFixed(2), clip: s1.clip, rate: s1.rate && +s1.rate.toFixed(2),
              bodyOff: s1.face === null || sp < 0.25 ? null : off(s1.face), yawOff: sp < 0.25 ? null : off(s1.yaw),
              lowAboveFeet: s1.low === null ? null : +(s1.low - s1.y).toFixed(2), h: s1.h && +s1.h.toFixed(2) });
}
console.log(JSON.stringify(rows));
if (OUT) {
  // frame the nearest moving quadruped from the side
  const q = rows.findIndex(r => r.quad && r.speed > 0.3);
  if (q >= 0) {
    await p.evaluate((nm) => {
      const n = window.__game.npcRefs().find(x => x.name === nm && !x.dead);
      const o = n.obj.position, yaw = n.obj.rotation.y;
      window.__camPin = { pos: [o.x + Math.cos(yaw) * 5, o.y + 1.6, o.z - Math.sin(yaw) * 5], look: [o.x, o.y + 0.6, o.z] };
      window.__pinFollow = nm;
    }, rows[q].name);
    for (let k = 0; k < 3; k++) {
      await new Promise(r => setTimeout(r, 120));
      await p.evaluate(() => { const n = window.__game.npcRefs().find(x => x.name === window.__pinFollow && !x.dead); const o = n.obj.position, yaw = n.obj.rotation.y;
        window.__camPin = { pos: [o.x + Math.cos(yaw) * 5, o.y + 1.6, o.z - Math.sin(yaw) * 5], look: [o.x, o.y + 0.6, o.z] }; });
      await p.screenshot({ path: `${OUT}/creature_${J}_${k}.jpg`, type: 'jpeg', quality: 85 });
    }
  }
}
console.log('errs', JSON.stringify(errs.slice(0, 4)));
await b.close();
