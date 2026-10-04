// The heaviest things in a scene: triangles per object (instances counted).
//   J=job_533 node triprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 10000));
console.log(JSON.stringify(await p.evaluate(() => {
  const out = [];
  window.__scene.traverse(o => {
    if (!o.isMesh || !o.visible || !o.geometry) return;
    const g = o.geometry, tri = (g.index ? g.index.count : g.attributes.position.count) / 3;
    const n = o.isInstancedMesh ? o.count : 1;
    out.push([o.name || o.type, Math.round(tri * n), n, o.castShadow]);
  });
  out.sort((a, b) => b[1] - a[1]);
  return { calls: window.__frameCalls, tris: window.__frameTris, top: out.slice(0, 14) };
})));
await b.close();
