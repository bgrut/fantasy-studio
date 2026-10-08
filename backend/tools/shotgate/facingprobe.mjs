// FACING (2026-10-07): does every walking body face the way it goes? A knee
// bends forward, so the knee's offset from the hip-ankle line points where
// the body faces, whatever the rig's axes. Sampled while the hero walks and
// the cast moves; each body reports the mean cosine between that front and
// its travel (1 = facing its way, -1 = walking backwards, 0 = sideways).
//   J=<bare job number> [SECS=6] node facingprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, SECS = +(process.env.SECS || 6);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await p.evaluate(() => {
  const V = window.__scene.position.constructor;
  const bodies = [];
  const add = (obj, name) => { let sk = null; obj.traverse(o => { if (!sk && o.isSkinnedMesh && o.skeleton) sk = o.skeleton; }); if (!sk) return;
    const B = {}; for (const bn of sk.bones) B[bn.name.toLowerCase()] = bn;
    const biped = !!(B.upleg_l && B.lowleg_l && B.foot_l && B.upleg_r && B.lowleg_r && B.foot_r);
    // a four-legged body: its head is ahead of its hips
    // the quadruped bake labels its ends swapped: its "tail" bone is at the head and its "neck" at the rump
      const swapped = !!(B.tail && B.neck && Object.keys(B).some(k => /^thigh_/.test(k)));
      const hk = swapped ? 'tail' : (Object.keys(B).find(k => /head/.test(k)) || Object.keys(B).find(k => /neck/.test(k))),
            pk = swapped ? 'neck' : Object.keys(B).find(k => /^(hips|pelvis|root|spine)/.test(k));
    if (!biped && !(hk && pk)) return;
    bodies.push({ name: name + (biped ? '' : ' (quad)'), obj, B, biped, hk, pk, last: null, sum: 0, n: 0 }); };
  let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
  if (pl) add(pl, 'HERO');
  for (const n of (window.__game.npcRefs ? window.__game.npcRefs() : [])) if (n && n.obj && !n.dormant) add(n.obj, (n.name || 'npc') + ':' + n.behavior);
  for (const pd of (window.__peds || []).slice(0, 12)) if (pd && pd.obj) add(pd.obj, 'pedestrian');
  const a = new V(), k = new V(), f = new V(), w = new V(), mid = new V();
  window.__facing = bodies;
  const tick = () => {
    for (const bd of bodies) {
      bd.obj.getWorldPosition(w);
      if (bd.last) {
        const vx = w.x - bd.last.x, vz = w.z - bd.last.z, sp = Math.hypot(vx, vz);
        if (sp > 0.012) {                      // moving this frame
          let fx = 0, fz = 0;
          if (bd.biped) for (const s of ['l', 'r']) { bd.B['upleg_' + s].getWorldPosition(a); bd.B['lowleg_' + s].getWorldPosition(k); bd.B['foot_' + s].getWorldPosition(f);
            mid.copy(a).add(f).multiplyScalar(0.5); fx += k.x - mid.x; fz += k.z - mid.z; }
          else { bd.B[bd.hk].getWorldPosition(k); bd.B[bd.pk].getWorldPosition(a); fx = k.x - a.x; fz = k.z - a.z; }
          const fl = Math.hypot(fx, fz);
          if (fl > 0.01) { bd.sum += (fx * vx + fz * vz) / (fl * sp); bd.n++; }
        }
      }
      bd.last = w.clone();
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
await p.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, SECS * 500));
await p.keyboard.down('KeyA'); await new Promise(r => setTimeout(r, 600)); await p.keyboard.up('KeyA');
await new Promise(r => setTimeout(r, SECS * 500)); await p.keyboard.up('KeyW');
const r = await p.evaluate(() => window.__facing.map(b => [b.name, b.n, b.n ? +(b.sum / b.n).toFixed(2) : null]));
let bad = 0;
for (const [name, n, c] of r) { const verdict = c === null ? 'still' : c > 0.3 ? 'ok' : c < -0.3 ? 'BACKWARDS' : 'SIDEWAYS?'; if (verdict === 'BACKWARDS' || verdict === 'SIDEWAYS?') bad++;
  console.log(String(name).padEnd(28), String(n).padStart(5), 'samples', String(c).padStart(6), verdict); }
console.log(`job ${J}: ${r.length} bodies, ${bad} facing wrong`, errs.length ? 'errors ' + JSON.stringify(errs.slice(0, 2)) : '');
await b.close();
