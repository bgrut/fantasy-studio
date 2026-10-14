// Big meshes built from few triangles: what reads as blocky. J=<job> node _lowpoly.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 120000 });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500));
const out = await p.evaluate(() => {
  const V = window.__scene.position.constructor, pl = window.__game.pos(), rows = [];
  const B = new (Object.getPrototypeOf(new V()).constructor)();
  window.__scene.updateMatrixWorld(true);
  window.__scene.traverse(o => {
    if (!o.isMesh || !o.geometry || !o.visible) return;
    const g = o.geometry; if (!g.boundingBox) g.computeBoundingBox();
    const s = new V(); g.boundingBox.getSize(s); const sc = new V(); o.getWorldScale(sc);
    const size = Math.max(s.x * sc.x, s.y * sc.y, s.z * sc.z);
    const tris = (g.index ? g.index.count : g.attributes.position.count) / 3;
    const c = new V(); g.boundingBox.getCenter(c); c.applyMatrix4(o.matrixWorld);
    const d = Math.hypot(c.x - pl[0], c.z - pl[2]);
    const n = o.isInstancedMesh ? o.count : 1;
    if (size > 2.5 && tris / Math.max(1, size * size) < 4 && d < 120) {
      let chain = [], q = o; while (q && chain.length < 4) { chain.push(q.name || (q.userData && q.userData.fsTag && q.userData.fsTag.name) || q.type); q = q.parent; }
      rows.push({ chain: chain.join(' < '), size: +size.toFixed(1), tris, n, d: +d.toFixed(0), flat: !!(o.material && o.material.flatShading), mat: o.material && o.material.type, col: o.material && o.material.color && o.material.color.getHexString() });
    }
  });
  return rows.sort((a, b) => a.d - b.d).slice(0, 40);
});
for (const r of out) console.log(JSON.stringify(r));
await b.close();
