import puppeteer from 'puppeteer-core';
const J = process.env.J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
console.log(JSON.stringify(await p.evaluate(() => {
  const S = window.__scene, cam = window.__camera, V = cam.position.constructor;
  // find a Raycaster through any object's prototype chain is not possible; build one from three's module via a mesh
  const out = [];
  const x = 2.95, z = -10.83;
  S.updateMatrixWorld(true);
  S.traverse(o => {
    if (!o.isMesh || !o.visible || !o.geometry || !o.geometry.attributes.position) return;
    const pa = o.geometry.attributes.position, m = o.matrixWorld, v = new V();
    let near = null;
    const n = pa.count; if (n > 400000) return;
    for (let i = 0; i < n; i++) { v.fromBufferAttribute(pa, i).applyMatrix4(m);
      if (Math.abs(v.x - x) < 2 && Math.abs(v.z - z) < 2 && (!near || v.y > near)) near = v.y; }
    if (near !== null) out.push([o.name || o.type, o.material && o.material.type, +near.toFixed(2), o.isInstancedMesh ? 'inst' : '']);
  });
  return out;
})));
await b.close();
