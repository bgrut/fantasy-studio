// THE RENDER CHECK (2026-09-24). What geometry alone cannot tell, a render
// can: a mangled generation is a cloud of flipped shards, so it loses most of
// its silhouette when back faces are culled, its silhouette is full of holes,
// and its outline is a sawtooth. Each kind is rendered from a three-quarter
// view with the runtime's own three.js; three numbers come back per kind:
//   cull_loss  share of the double-sided silhouette lost with back-face culling
//   solidity   share of the silhouette's row-hull that is filled (holes lower it)
//   edges      outline pixels per silhouette pixel (a sawtooth raises it)
// Serve the repo root first:  python -m http.server 8791   (from the repo root)
//   node assetview.mjs car,corvette,ferrari        renders these kinds, prints the numbers
//   node assetview.mjs --all                        every kind in library.json, writes library_render.json
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../../..');
const lib = JSON.parse(fs.readFileSync(path.join(ROOT, 'backend/assets/library.json'), 'utf-8'));
const arg = process.argv[2] || 'car,corvette,ferrari';
const kinds = arg === '--all' ? Object.keys(lib).filter(k => typeof lib[k] === 'string' && lib[k].endsWith('.glb')) : arg.split(',');
const OUTDIR = path.join(HERE, 'renders'); fs.mkdirSync(OUTDIR, { recursive: true });
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=640,480'] });
const p = await b.newPage(); await p.setViewport({ width: 640, height: 480 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
const vendor = fs.readdirSync(path.join(ROOT, 'backend/renders/game_jobs')).filter(d => d.startsWith('job_')).map(d => path.join(ROOT, 'backend/renders/game_jobs', d, 'dist/vendor/three.module.js')).find(f => fs.existsSync(f));
const vendorUrl = '/' + path.relative(ROOT, path.dirname(vendor)).replace(/\\/g, '/') + '/';
const html = `<!doctype html><body style="margin:0;background:#000"><script type="importmap">{"imports":{"three":"${vendorUrl}three.module.js","three/addons/":"${vendorUrl}jsm/"}}</script>
<script type="module">
import * as THREE from 'three'; import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const W = 640, H = 480;
const r = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true }); r.setSize(W, H); r.setClearColor(0x000000, 1); document.body.appendChild(r.domElement);
const cam = new THREE.PerspectiveCamera(30, W / H, 0.05, 100);
const L = new GLTFLoader();
window.__render = async (url) => {
  const sc = new THREE.Scene(); sc.add(new THREE.AmbientLight(0xffffff, 3.0));
  const g = await L.loadAsync(url); const o = g.scene;
  // a flat white material: we measure shape, not shading; two passes, back faces culled and not
  const white = (side) => new THREE.MeshBasicMaterial({ color: 0xffffff, side });
  const bb = new THREE.Box3().setFromObject(o); const size = bb.getSize(new THREE.Vector3()); const s = 2.0 / Math.max(size.x, size.y, size.z);
  o.scale.setScalar(s); const bb2 = new THREE.Box3().setFromObject(o); const c = bb2.getCenter(new THREE.Vector3()); o.position.sub(c); sc.add(o);
  const long = size.x >= size.z ? 'x' : 'z';
  cam.position.set(long === 'x' ? 3.2 : 2.2, 1.6, long === 'x' ? 2.2 : 3.2); cam.lookAt(0, 0, 0);
  const shot = (side) => { o.traverse(m => { if (m.isMesh) m.material = white(side); }); r.render(sc, cam); const gl = r.getContext(); const px = new Uint8Array(W * H * 4); gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px); const mask = new Uint8Array(W * H); for (let i = 0; i < W * H; i++) mask[i] = px[i * 4] > 40 ? 1 : 0; return mask; };
  // the shaded view first, with the model's own materials under a soft key: this is what a judge sees
  const keep = new Map(); o.traverse(m => { if (m.isMesh) keep.set(m, m.material); });
  const key = new THREE.DirectionalLight(0xfff2e0, 2.6); key.position.set(3, 5, 4); sc.add(key);
  const hemi = new THREE.HemisphereLight(0xdfe8ff, 0x33302c, 1.2); sc.add(hemi);
  sc.background = new THREE.Color(0x8a8f99);
  r.render(sc, cam); const shaded = r.domElement.toDataURL('image/png');
  // DARK SHARE: torn generations show black where faces point inward or the
  // texture never landed; under this key a healthy model has almost none
  const spx = new Uint8Array(W * H * 4); r.getContext().readPixels(0, 0, W, H, r.getContext().RGBA, r.getContext().UNSIGNED_BYTE, spx);
  sc.background = null; sc.remove(key); sc.remove(hemi);
  // THE ALBEDO PASS: the same view unlit, with the model's own colour and map.
  // A pixel bright here and black when lit is a shading failure (a face
  // pointing inward, a normal gone wrong); a pixel dark in both is a dark
  // material and no fault. Only the first kind counts as damage.
  o.traverse(m => { if (m.isMesh) { const src = Array.isArray(m.material) ? m.material[0] : m.material; m.material = new THREE.MeshBasicMaterial({ color: (src && src.color) ? src.color.clone() : 0xffffff, map: src && src.map ? src.map : null, side: THREE.DoubleSide }); } });
  r.render(sc, cam);
  const apx = new Uint8Array(W * H * 4); r.getContext().readPixels(0, 0, W, H, r.getContext().RGBA, r.getContext().UNSIGNED_BYTE, apx);
  const front = shot(THREE.FrontSide), both = shot(THREE.DoubleSide);
  let nf = 0, nb = 0, hull = 0, edges = 0, dark = 0, damage = 0;
  for (let i = 0; i < W * H; i++) {
    if (!both[i]) continue;
    const lit = 0.2126 * spx[i * 4] + 0.7152 * spx[i * 4 + 1] + 0.0722 * spx[i * 4 + 2];
    const alb = 0.2126 * apx[i * 4] + 0.7152 * apx[i * 4 + 1] + 0.0722 * apx[i * 4 + 2];
    if (lit < 22) dark++;
    if (lit < 22 && alb > 70) damage++;
  }
  for (let y = 0; y < H; y++) { let l = -1, rr = -1; for (let x = 0; x < W; x++) { const i = y * W + x; nf += front[i]; if (both[i]) { nb++; if (l < 0) l = x; rr = x; } } if (l >= 0) hull += rr - l + 1; }
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) { const i = y * W + x; if (both[i] && (!both[i - 1] || !both[i + 1] || !both[i - W] || !both[i + W])) edges++; }
  const dataUrl = r.domElement.toDataURL('image/png');
  sc.remove(o);
  return { cull_loss: +(1 - nf / Math.max(nb, 1)).toFixed(3), solidity: +(nb / Math.max(hull, 1)).toFixed(3), edges: +(edges / Math.max(nb, 1)).toFixed(4), coverage: +(nb / (W * H)).toFixed(3), dark_share: +(dark / Math.max(nb, 1)).toFixed(3), damage_share: +(damage / Math.max(nb, 1)).toFixed(3), png: dataUrl, shaded };
};
window.__ready = true;
</script></body>`;
fs.writeFileSync(path.join(ROOT, '_assetview.html'), html, 'utf-8');
await p.goto('http://127.0.0.1:8791/_assetview.html', { waitUntil: 'domcontentloaded', timeout: 60000 });
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!window.__ready)) break; await new Promise(r => setTimeout(r, 500)); }
const out = {};
for (const k of kinds) {
  const rel = lib[k]; if (typeof rel !== 'string') continue;
  const url = '/backend/' + rel.replace(/\\/g, '/');
  try {
    const res = await p.evaluate(async (u) => { const r = await window.__render(u); return r; }, url);
    const png = res.png; delete res.png; const shaded = res.shaded; delete res.shaded;
    const stem = k.replace(/[^a-z0-9]+/gi, '_');
    fs.writeFileSync(path.join(OUTDIR, stem + '.png'), Buffer.from(png.split(',')[1], 'base64'));
    fs.writeFileSync(path.join(OUTDIR, stem + '_shaded.png'), Buffer.from(shaded.split(',')[1], 'base64'));
    res.shaded_png = 'backend/tools/shotgate/renders/' + stem + '_shaded.png'; res.kind = k;
    out[path.basename(rel).toLowerCase()] = res;
    console.log(k.padEnd(20), 'damage', String(res.damage_share).padStart(6), '| dark', String(res.dark_share).padStart(6), '| cull_loss', String(res.cull_loss).padStart(6), '| solidity', String(res.solidity).padStart(6), '| edges', String(res.edges).padStart(7), '| coverage', res.coverage);
  } catch (e) { console.log(k.padEnd(20), 'FAILED', e.message.slice(0, 120)); out[path.basename(rel).toLowerCase()] = { error: e.message.slice(0, 120) }; }
}
if (arg === '--all') { fs.writeFileSync(path.join(ROOT, 'backend/assets/library_render.json'), JSON.stringify(out, null, 1), 'utf-8'); console.log('written backend/assets/library_render.json for', Object.keys(out).length, 'files'); }
if (errs.length) console.log('errors:', errs.slice(0, 3).join(' | '));
fs.unlinkSync(path.join(ROOT, '_assetview.html'));
await b.close();
