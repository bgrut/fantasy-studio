import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 10000));
console.log(JSON.stringify(await p.evaluate(() => {
  const L = window.__spec.world.level; const path = L.path;
  const sd = (px, pz, ax, az, bx, bz) => { const dx = bx - ax, dz = bz - az, t = Math.max(0, Math.min(1, ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz || 1))); return Math.hypot(px - ax - dx * t, pz - az - dz * t); };
  const near = (x, z) => Math.min(...path.slice(0, -1).map((a, k) => sd(x, z, a[0], a[1], path[k + 1][0], path[k + 1][1])));
  let flora = 0, floraOn = 0, ent = 0, entOn = 0; const M = new (window.__camera.matrix.constructor)();
  window.__scene.traverse(o => {
    if (o.isInstancedMesh && /flora|tree|pine/i.test((o.name || '') + (o.parent && o.parent.name || ''))) for (let i = 0; i < o.count; i++) { o.getMatrixAt(i, M); const x = M.elements[12], z = M.elements[14]; flora++; if (near(x, z) < 8) { floraOn++; if (!window.__ex) window.__ex = [x, z, near(x, z), o.parent && o.parent.name]; } }
  });
  return { ex: window.__ex, path, slalom: window.__slalom, pathPts: path.length, flora, floraOn, floraInfo: window.__flora && { on: window.__flora.on, total: window.__flora.total } };
})));
await b.close();
