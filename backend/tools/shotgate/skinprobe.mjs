// The skin in the engine: after a walk, find the hero's skinned mesh through the
// weapon's hand bone, select the vertices that sit along the left upper arm at
// bind time, skin them with the mesh's own boneTransform, and compare the
// centroid's direction from the shoulder joint with the bone's.   J=<job>
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
await wait(9000); const btn = await p.$('#startbtn'); if (btn) await btn.click(); await wait(3000);
await p.keyboard.down('KeyW'); await wait(2500);
const r = await p.evaluate(() => {
  const pp = window.__game.pos(); let sk = null, best = 1e9; const w = new (window.__camera.position.constructor)();
  window.__scene.traverse(o => { if (!o.isSkinnedMesh) return; o.getWorldPosition(w); const d = Math.hypot(w.x - pp[0], w.z - pp[2]); if (d < best) { best = d; sk = o; } });
  if (!sk) return { err: 'no skinned mesh' };
  const bones = sk.skeleton.bones, inv = sk.skeleton.boneInverses;
  const bi = bones.findIndex(x => /^uparm_L$/i.test(x.name)), ci = bones.findIndex(x => /^lowarm_L$/i.test(x.name));
  if (bi < 0 || ci < 0) return { err: 'no arm bones', names: bones.map(x => x.name) };
  const M = (i) => inv[i].clone().invert();                       // bind-pose bone matrix in mesh space
  const V = (m) => { const e = m.elements; return [e[12], e[13], e[14]]; };
  const a = V(M(bi)), c = V(M(ci));                                 // shoulder and elbow at bind
  const pos = sk.geometry.attributes.position, n = pos.count;
  const ab = [c[0]-a[0], c[1]-a[1], c[2]-a[2]], L2 = ab[0]*ab[0]+ab[1]*ab[1]+ab[2]*ab[2];
  const sel = [];
  for (let i = 0; i < n; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    const t = ((x-a[0])*ab[0]+(y-a[1])*ab[1]+(z-a[2])*ab[2]) / L2; if (t < 0.15 || t > 0.85) continue;
    const px = a[0]+t*ab[0], py = a[1]+t*ab[1], pz = a[2]+t*ab[2]; const d = Math.hypot(x-px, y-py, z-pz);
    if (d < 0.09 * Math.sqrt(L2) / Math.sqrt(L2) * 1.0 && d < 0.09) sel.push(i);
  }
  const tmp = new (sk.position.constructor)(); let cx = 0, cy = 0, cz = 0;
  sk.updateMatrixWorld(true); sk.skeleton.update();
  // the vertex shader's skinning, by hand (this three.js has no boneTransform):
  // world = matrixWorld * bindMatrixInverse * sum(w * boneMatrix[j]) * bindMatrix * p
  const app = (e, o, v) => [e[o]*v[0]+e[o+4]*v[1]+e[o+8]*v[2]+e[o+12], e[o+1]*v[0]+e[o+5]*v[1]+e[o+9]*v[2]+e[o+13], e[o+2]*v[0]+e[o+6]*v[1]+e[o+10]*v[2]+e[o+14]];
  const bm = sk.skeleton.boneMatrices, bind = sk.bindMatrix.elements, bindInv = sk.bindMatrixInverse.elements, mw = sk.matrixWorld.elements;
  const si = sk.geometry.attributes.skinIndex, swt = sk.geometry.attributes.skinWeight;
  for (const i of sel) {
    const pv = app(bind, 0, [pos.getX(i), pos.getY(i), pos.getZ(i)]);
    let sx = 0, sy = 0, sz = 0;
    for (let k = 0; k < 4; k++) { const wgt = swt.getComponent(i, k); if (!wgt) continue; const j = si.getComponent(i, k); const q = app(bm, j * 16, pv); sx += wgt * q[0]; sy += wgt * q[1]; sz += wgt * q[2]; }
    const wv = app(mw, 0, app(bindInv, 0, [sx, sy, sz])); cx += wv[0]; cy += wv[1]; cz += wv[2];
  }
  cx /= sel.length; cy /= sel.length; cz /= sel.length;
  const sw = bones[bi].getWorldPosition(tmp.clone()), ew = bones[ci].getWorldPosition(tmp.clone());
  const dv = [cx - sw.x, cy - sw.y, cz - sw.z], dl = Math.hypot(...dv); const bv = [ew.x - sw.x, ew.y - sw.y, ew.z - sw.z], bl = Math.hypot(...bv);
  const deg = (v, l) => (Math.acos(Math.max(-1, Math.min(1, -v[1] / l))) * 180 / Math.PI).toFixed(1);
  return { verts: sel.length, bone_from_down: deg(bv, bl), skin_from_down: deg(dv, dl), skin_lateral: (dv[0] / dl).toFixed(2), skin_fwd: (dv[2] / dl).toFixed(2), mesh: sk.name, scale: sk.matrixWorld.elements[0].toFixed(3) };
});
console.log('skin      :', JSON.stringify(r));
await p.keyboard.up('KeyW'); await b.close();
