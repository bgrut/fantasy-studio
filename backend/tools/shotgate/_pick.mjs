// What is that thing on screen? The opening's frame _c (as _open.mjs), then
// every mesh whose bounding box projects over pixel PX,PY (of 1600x900),
// nearest first.   J=job_N PX=1400 PY=250 node _pick.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(5400);
if (process.env.OUT) await p.screenshot({ path: process.env.OUT, type: 'jpeg', quality: 85 });
const rows = await p.evaluate((px, py) => {
  const cam = window.__camera, V = cam.position.constructor, nx = px / 1600 * 2 - 1, ny = -(py / 900 * 2 - 1), out = [];
  window.__scene.updateMatrixWorld(true);
  window.__scene.traverse(o => {
    if (!o.isMesh || !o.visible || !o.geometry) return;
    const g = o.geometry; if (!g.boundingBox) g.computeBoundingBox();
    const M4 = o.matrixWorld.constructor, mats = [];
    if (o.isInstancedMesh) { for (let i = 0; i < o.count; i++) { const m = new M4(); o.getMatrixAt(i, m); mats.push([i, m.premultiply(o.matrixWorld)]); } } else mats.push([-1, o.matrixWorld]);
    for (const [inst, MW] of mats) {
    const bb = g.boundingBox; let x0 = 9, x1 = -9, y0 = 9, y1 = -9, zmin = 9, ok = false;
    for (let k = 0; k < 8; k++) { const v = new V(k & 1 ? bb.max.x : bb.min.x, k & 2 ? bb.max.y : bb.min.y, k & 4 ? bb.max.z : bb.min.z).applyMatrix4(MW).project(cam);
      if (v.z < 1) ok = true; x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y); zmin = Math.min(zmin, v.z); }
    if (!ok || nx < x0 || nx > x1 || ny < y0 || ny > y1 || (x1 - x0) > 1.6) continue;
    const c = new V(); bb.getCenter(c); c.applyMatrix4(MW);
    let chain = [], q = o; while (q && chain.length < 5) { chain.push((q.name || (q.userData && q.userData.fsTag && q.userData.fsTag.name) || q.type) + (q.userData && q.userData.kind ? '[' + q.userData.kind + ']' : '')); q = q.parent; }
    out.push({ inst, chain: chain.join(' < '), geo: g.type, tris: (g.index ? g.index.count : g.attributes.position.count) / 3, dist: +c.distanceTo(cam.position).toFixed(1),
      mat: o.material && o.material.type, map: !!(o.material && o.material.map), flat: !!(o.material && o.material.flatShading), col: o.material && o.material.color && o.material.color.getHexString() });
    }
  });
  return out.sort((a, b) => a.dist - b.dist).slice(0, 12);
}, +process.env.PX, +process.env.PY);
for (const r of rows) console.log(JSON.stringify(r));
await b.close();
