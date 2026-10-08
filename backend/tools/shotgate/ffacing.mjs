// GATE: every body faces the way it goes (2026-10-07). Every moving NPC and
// every pedestrian walked backwards for weeks (bodies are built facing -Z;
// only the hero's holder took the half turn). A knee bends forward, so the
// knee's offset from the hip-ankle line is a body's front whatever the rig's
// axes; for a four-legged body, its head ahead of its hips. The hero walks;
// each moving body's mean cosine between that front and its travel must be
// positive. Runs on the building fixture (B: ghosts that move) and the city
// fixture (A: pedestrians).   A=<job> B=<job> node ffacing.mjs
import puppeteer from 'puppeteer-core';
const jobs = [process.env.B, process.env.A].filter(Boolean);
if (!jobs.length) { console.log('ffacing: needs B=<job> and/or A=<job>; FAIL'); process.exit(1); }
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
let bad = 0, measured = 0;
for (const J of jobs) {
  const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
  await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g').catch(() => {});
  await p.evaluate(() => {
    const V = window.__scene.position.constructor, bodies = [];
    const add = (obj, name) => { let sk = null; obj.traverse(o => { if (!sk && o.isSkinnedMesh && o.skeleton) sk = o.skeleton; }); if (!sk) return;
      const B = {}; for (const bn of sk.bones) B[bn.name.toLowerCase()] = bn;
      const biped = !!(B.upleg_l && B.lowleg_l && B.foot_l && B.upleg_r && B.lowleg_r && B.foot_r);
      // the quadruped bake labels its ends swapped: its "tail" bone is at the head and its "neck" at the rump
      const swapped = !!(B.tail && B.neck && Object.keys(B).some(k => /^thigh_/.test(k)));
      const hk = swapped ? 'tail' : (Object.keys(B).find(k => /head/.test(k)) || Object.keys(B).find(k => /neck/.test(k))),
            pk = swapped ? 'neck' : Object.keys(B).find(k => /^(hips|pelvis|root|spine)/.test(k));
      if (!biped && !(hk && pk)) return;
      bodies.push({ name, obj, B, biped, hk, pk, last: null, sum: 0, n: 0 }); };
    let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
    if (pl) add(pl, 'hero');
    for (const n of (window.__game.npcRefs ? window.__game.npcRefs() : [])) if (n && n.obj && !n.dormant) add(n.obj, (n.name || 'npc') + ':' + n.behavior);
    for (const pd of (window.__peds || []).slice(0, 10)) if (pd && pd.obj) add(pd.obj, 'pedestrian');
    const a = new V(), k = new V(), f = new V(), w = new V(), mid = new V();
    window.__ffacing = bodies;
    const tick = () => { for (const bd of bodies) { bd.obj.getWorldPosition(w);
        if (bd.last) { const vx = w.x - bd.last.x, vz = w.z - bd.last.z, sp = Math.hypot(vx, vz);
          if (sp > 0.012) { let fx = 0, fz = 0;
            if (bd.biped) for (const s of ['l', 'r']) { bd.B['upleg_' + s].getWorldPosition(a); bd.B['lowleg_' + s].getWorldPosition(k); bd.B['foot_' + s].getWorldPosition(f);
              mid.copy(a).add(f).multiplyScalar(0.5); fx += k.x - mid.x; fz += k.z - mid.z; }
            else { bd.B[bd.hk].getWorldPosition(k); bd.B[bd.pk].getWorldPosition(a); fx = k.x - a.x; fz = k.z - a.z; }
            const fl = Math.hypot(fx, fz); if (fl > 0.01) { bd.sum += (fx * vx + fz * vz) / (fl * sp); bd.n++; } } }
        bd.last = w.clone(); }
      requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
  await p.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, 3000));
  await p.keyboard.down('KeyA'); await new Promise(r => setTimeout(r, 500)); await p.keyboard.up('KeyA');
  await new Promise(r => setTimeout(r, 3000)); await p.keyboard.up('KeyW');
  const r = await p.evaluate(() => window.__ffacing.filter(b => b.n >= 20).map(b => [b.name, +(b.sum / b.n).toFixed(2)]));
  const wrong = r.filter(([, c]) => c < 0.3);
  measured += r.length; bad += wrong.length;
  console.log(`job ${J}: ${r.length} moving bodies measured, ${wrong.length} facing against their travel`, wrong.length ? JSON.stringify(wrong.slice(0, 4)) : '');
  await p.close();
}
await b.close();
const ok = measured >= 2 && bad === 0;
console.log(ok ? 'PASS' : 'FAIL', `ffacing: ${measured} bodies, ${bad} backwards or sideways`);
process.exit(ok ? 0 : 1);
