// Every character's face on one sheet: OUT=png [KINDS=a,b] node _faces.mjs
// Serve the repo root first: python -m http.server 8791 (from the repo root).
// Each *_anim.glb in the library is loaded as shipped (no runtime detail layer), its head
// found as the top band of its rest pose, and rendered head-on from -Z (a biped's front)
// in a tile with its name, so a blurry or smeared face shows beside the sharp ones.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const LIB = path.resolve(HERE, '../../assets/library');
let kinds = process.env.KINDS ? process.env.KINDS.split(',') : fs.readdirSync(LIB).filter(f => f.endsWith('_anim.glb')).map(f => f.replace(/_anim\.glb$/, ''));
kinds = kinds.filter(k => fs.existsSync(path.join(LIB, k + '_anim.glb')) && fs.statSync(path.join(LIB, k + '_anim.glb')).size > 1000);
const COLS = 8, T = 220, ROWS = Math.ceil(kinds.length / COLS);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: COLS * T, height: ROWS * (T + 18) });
p.on('pageerror', e => console.log('ERR', e.message));
await p.goto('http://127.0.0.1:8791/backend/tools/shotgate/fixtures/README.md');
await p.setContent(`<!doctype html><html><head><style>body{margin:0;background:#202024;font:11px sans-serif;color:#ddd}
  #g{display:grid;grid-template-columns:repeat(${COLS},${T}px)} .t{width:${T}px;height:${T + 18}px} .t img{width:${T}px;height:${T}px;display:block}</style>
  <script type="importmap">{"imports":{"three":"http://127.0.0.1:8791/backend/app/game_export/runtime/vendor/three.module.js"}}</script></head>
  <body><div id="g"></div><script type="module">
  import * as THREE from 'three';
  import { GLTFLoader } from 'http://127.0.0.1:8791/backend/app/game_export/runtime/vendor/jsm/loaders/GLTFLoader.js';
  const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setSize(${T * 2}, ${T * 2}); r.outputColorSpace = THREE.SRGBColorSpace;
  r.toneMapping = THREE.ACESFilmicToneMapping;
  const L = new GLTFLoader();
  window.shoot = async (kind) => {
    const sc = new THREE.Scene(); sc.background = new THREE.Color(0x3a3a40);
    sc.add(new THREE.HemisphereLight(0xffffff, 0x404040, 1.6));
    const d = new THREE.DirectionalLight(0xffffff, 2.2); d.position.set(1, 2, -3); sc.add(d);
    const gl = await L.loadAsync('http://127.0.0.1:8791/backend/assets/library/' + kind + '_anim.glb');
    const root = gl.scene; sc.add(root); root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(root), H = box.max.y - box.min.y, top = box.max.y - H * 0.14;
    const hb = new THREE.Box3(), v = new THREE.Vector3();
    root.traverse(o => { if (!o.isMesh) return; const ps = o.geometry.attributes.position;
      for (let i = 0; i < ps.count; i += 3) { v.fromBufferAttribute(ps, i).applyMatrix4(o.matrixWorld); if (v.y > top) hb.expandByPoint(v); } });
    const c = hb.getCenter(new THREE.Vector3()), hh = Math.max(0.05, hb.max.y - hb.min.y);
    const cam = new THREE.PerspectiveCamera(30, 1, 0.01, 50); cam.position.set(c.x, c.y, c.z - hh * 3.6); cam.lookAt(c);
    r.render(sc, cam);
    return r.domElement.toDataURL('image/jpeg', 0.9);
  };
  window.ready = true;
  </script></body></html>`);
for (let i = 0; i < 40 && !(await p.evaluate(() => window.ready)); i++) await new Promise(r => setTimeout(r, 250));
for (const k of kinds) {
  let url = null;
  try { url = await p.evaluate(k => window.shoot(k), k); } catch (e) { console.log('fail', k, e.message.slice(0, 80)); }
  await p.evaluate((k, url) => { const d = document.createElement('div'); d.className = 't'; d.innerHTML = (url ? '<img src="' + url + '">' : '<div style="height:${T}px"></div>') + k; document.getElementById('g').appendChild(d); }, k, url);
}
await new Promise(r => setTimeout(r, 500));
await p.screenshot({ path: process.env.OUT || 'faces.png', fullPage: true });
console.log(kinds.length, 'faces ->', process.env.OUT || 'faces.png');
await b.close();
