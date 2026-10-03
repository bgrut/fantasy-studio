// CLIP MEASURE (2026-10-03). Numbers for a rigged character's baked clips, so
// a retarget is judged by measurement and not by eye:
//   kneeL/kneeR  knee flexion in degrees (0 = straight)
//   trunkTilt    hips-to-neck line from vertical, degrees
//   hipsY, footL/footR  heights in metres; the lowest foot should sit at the
//                rest foot height while a foot is planted
// Serve a job's dist root (BASE, default http://127.0.0.1:8791) with
// cliplab.html (this folder) copied in and the GLB in its assets/, then:
//   F=<file.glb> C=walk,run,idle K=48 SUMMARY=1 node clipmeasure.mjs
import puppeteer from 'puppeteer-core';
const BASE = process.env.BASE || 'http://127.0.0.1:8791';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('ERR', e.message));
await p.goto(BASE + '/cliplab.html?f=' + process.env.F + '&c=walk&n=1');
await p.waitForFunction(() => window.__info, { timeout: 30000 });
const r = await p.evaluate(async (F, CLIPS, KK) => {
  const THREE = await import('three');
  const { GLTFLoader } = await import('./vendor/jsm/loaders/GLTFLoader.js');
  const g = await new GLTFLoader().loadAsync('./assets/' + F);
  const o = g.scene; const mixer = new THREE.AnimationMixer(o);
  const B = {}; o.traverse(n => { if (n.isBone) B[n.name] = n; });
  const P = n => B[n].getWorldPosition(new THREE.Vector3());
  const ang = (a, b2, c) => { const u = P(a).sub(P(b2)), v = P(c).sub(P(b2)); return 180 - THREE.MathUtils.radToDeg(u.angleTo(v)); };
  const out = { bones: Object.keys(B).join(',') };
  if (!['hips', 'upleg_L', 'lowleg_L', 'foot_L', 'neck'].every(n => B[n])) return out;
  o.updateMatrixWorld(true);
  const leg = P('upleg_L').distanceTo(P('lowleg_L')) + P('lowleg_L').distanceTo(P('foot_L'));
  out.rest = { hipsY: +P('hips').y.toFixed(3), leg: +leg.toFixed(3), footY: +P('foot_L').y.toFixed(3) };
  for (const cn of CLIPS.split(',')) {
    const clip = g.animations.find(a => a.name === cn); if (!clip) continue;
    mixer.stopAllAction(); mixer.clipAction(clip).reset().play();
    const rows = [];
    for (let k = 0; k < KK; k++) {
      mixer.setTime(clip.duration * k / KK); o.updateMatrixWorld(true);
      const up = P('neck').sub(P('hips')).normalize();
      rows.push({ kneeL: +ang('upleg_L', 'lowleg_L', 'foot_L').toFixed(0), kneeR: +ang('upleg_R', 'lowleg_R', 'foot_R').toFixed(0),
        hipsY: +P('hips').y.toFixed(2), footL: +P('foot_L').y.toFixed(2), footR: +P('foot_R').y.toFixed(2),
        trunkTilt: +THREE.MathUtils.radToDeg(Math.acos(up.y)).toFixed(0) });
    }
    out[cn] = rows;
  }
  return out;
}, process.env.F, process.env.C || 'walk,idle', +(process.env.K || 6));
await b.close();
if (process.env.SUMMARY) {
  for (const [k, rows] of Object.entries(r)) {
    if (!Array.isArray(rows)) continue;
    const lows = rows.map(x => Math.min(x.footL, x.footR)), hy = rows.map(x => x.hipsY), tt = rows.map(x => x.trunkTilt);
    const kn = rows.flatMap(x => [x.kneeL, x.kneeR]);
    console.log(`${k}: lowest foot ${Math.min(...lows).toFixed(2)}-${Math.max(...lows).toFixed(2)} | hips ${Math.min(...hy).toFixed(2)}-${Math.max(...hy).toFixed(2)}`
      + ` | knees ${Math.min(...kn)}-${Math.max(...kn)} | trunk ${Math.min(...tt)}-${Math.max(...tt)} | rest foot ${r.rest.footY}, rest hips ${r.rest.hipsY}`);
  }
} else {
  console.log(JSON.stringify(r));
}
