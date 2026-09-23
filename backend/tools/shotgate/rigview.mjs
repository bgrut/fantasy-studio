// A rig on its own: load a library rig with the runtime's three.js, play a
// clip, and shoot the figure from the front at four phases into one sheet.
// Serve the repo root first (python -m http.server 8791 from the repo root).
//   node rigview.mjs assets/library/scientist_anim.glb walk    -> renders/rig_<stem>_<clip>.png
import puppeteer from 'puppeteer-core';
import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.resolve(HERE, '../../..');
const rel = process.argv[2] || 'assets/library/scientist_anim.glb', clip = process.argv[3] || 'walk';
const vendor = fs.readdirSync(path.join(ROOT, 'backend/renders/game_jobs')).filter(d => d.startsWith('job_')).map(d => path.join(ROOT, 'backend/renders/game_jobs', d, 'dist/vendor/three.module.js')).find(f => fs.existsSync(f));
const vendorUrl = '/' + path.relative(ROOT, path.dirname(vendor)).split(path.sep).join('/') + '/';
const html = `<!doctype html><body style="margin:0;background:#8a8f99"><script type="importmap">{"imports":{"three":"${vendorUrl}three.module.js","three/addons/":"${vendorUrl}jsm/"}}</script>
<script type="module">
import * as THREE from 'three'; import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const W = 1200, H = 520; const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setSize(W, H); r.setClearColor(0x8a8f99, 1); document.body.appendChild(r.domElement);
const sc = new THREE.Scene(); sc.add(new THREE.HemisphereLight(0xdfe8ff, 0x33302c, 1.4)); const key = new THREE.DirectionalLight(0xfff2e0, 2.4); key.position.set(2, 5, 6); sc.add(key);
const g = await new GLTFLoader().loadAsync('/backend/${rel}'); const o = g.scene; sc.add(o);
const bb = new THREE.Box3().setFromObject(o); const h = bb.max.y - bb.min.y; o.position.y = -bb.min.y;
const span = Math.max(h, bb.max.x - bb.min.x, bb.max.z - bb.min.z);   // a long animal is framed by its length, not its height
const mixer = new THREE.AnimationMixer(o); const c = g.animations.find(a => a.name === '${clip}') || g.animations[0]; const act = mixer.clipAction(c); act.play();
const cam = new THREE.PerspectiveCamera(28, (W / 4) / H, 0.05, 100);
window.__shoot = () => {
  r.setScissorTest(true);
  for (let k = 0; k < 4; k++) {
    mixer.setTime(c.duration * (k / 4 + 0.05)); o.updateMatrixWorld(true);
    if (${process.env.SIDE ? 1 : 0}) cam.position.set(span * 3.4, h * 0.55, 0); else cam.position.set(0, h * 0.55, span * 2.6);   // SIDE=1 shoots the profile, the view that tells a gait
    cam.lookAt(0, h * 0.5, 0);
    r.setViewport(k * W / 4, 0, W / 4, H); r.setScissor(k * W / 4, 0, W / 4, H); r.render(sc, cam);
  }
  r.setScissorTest(false); return r.domElement.toDataURL('image/png');
};
window.__ready = true;
</script></body>`;
fs.writeFileSync(path.join(ROOT, '_rigview.html'), html, 'utf-8');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1200,520'] });
const p = await b.newPage(); await p.setViewport({ width: 1200, height: 520 }); const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.goto('http://127.0.0.1:8791/_rigview.html', { waitUntil: 'domcontentloaded', timeout: 60000 });
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!window.__ready)) break; await new Promise(r => setTimeout(r, 500)); }
const png = await p.evaluate(() => window.__shoot());
const out = path.join(HERE, 'renders', 'rig_' + path.basename(rel, '.glb') + '_' + clip + (process.env.SIDE ? '_side' : '') + '.png'); fs.writeFileSync(out, Buffer.from(png.split(',')[1], 'base64'));
console.log('wrote', out, errs.length ? '| errors: ' + errs.join(' | ') : '');
fs.unlinkSync(path.join(ROOT, '_rigview.html')); await b.close();
