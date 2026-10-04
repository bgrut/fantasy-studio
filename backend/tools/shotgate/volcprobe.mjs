// Probe a volcano build: where the lava ribbons sit against the ground under
// them, and what draws the sky.   J=job_509 node volcprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J;
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1200,700'] });
const p = await b.newPage();
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
const out = await p.evaluate(() => {
  const S = window.__scene, L = window.__spec.world.level;
  const ribs = [], skies = [], big = [];
  S.traverse(o => {
    if (o.name === 'lavaRibbon') { o.geometry.computeBoundingBox(); ribs.push({ vis: o.visible, y: o.geometry.boundingBox.min.y, layers: o.layers.mask }); }
    if (o.name === 'ashSky') skies.push({ vis: o.visible, r: o.geometry.parameters.radius });
    if ((o.isPoints || o.isMesh) && o.geometry && o.geometry.boundingSphere && o.geometry.boundingSphere.radius > 800) big.push((o.name || o.type) + ':' + Math.round(o.geometry.boundingSphere.radius) + ':' + o.visible);
  });
  // the ground height under the first channel's middle points, by raycast
  const ray = new (window.__camera.position.constructor)();
  const g = L.lava.channels[1].pts.slice(5, 12);
  const Rc = new (Object.getPrototypeOf(window.__scene).constructor)();
  return { ribs, skies, big: big.slice(0, 20), lvl: L.lava.level, far: window.__camera.far, bg: S.background ? (S.background.isColor ? S.background.getHexString() : 'tex') : null,
           hs: g.map(([x, z]) => { const n = L.grid_n, sz = L.size_m; const j = Math.round((x / sz + 0.5) * (n - 1)), i = Math.round((z / sz + 0.5) * (n - 1));
                                    return (i >= 0 && j >= 0 && i < n && j < n) ? L.heights[i * n + j] : null; }) };
});
console.log(JSON.stringify(out, null, 1));
await b.close();
