// Look straight at a deep lava point, once with the lava shader and once flat red.
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1200,700'] });
const p = await b.newPage(); await p.setViewport({ width: 1200, height: 700 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.text().slice(0, 300)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
const pt = await p.evaluate(() => {
  const L = window.__spec.world.level, n = L.grid_n, sz = L.size_m;
  let best = null;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const h = L.heights[i * n + j]; const x = (j / (n - 1) - 0.5) * sz, z = (i / (n - 1) - 0.5) * sz;
    if (h < -1.3 && Math.abs(x) < sz * 0.4 && Math.abs(z) < sz * 0.4) { const d = Math.hypot(x, z); if (!best || d < best.d) best = { x, z, d }; }
  }
  window.__camPin = { pos: [best.x + 6, 5, best.z + 6], look: [best.x, -0.5, best.z] };
  return best;
});
console.log(JSON.stringify(pt));
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/probe_lava.jpg`, type: 'jpeg', quality: 85 });
await p.evaluate(() => { window.__scene.traverse(o => { if (o.name === 'lavaRibbon') o.material = new o.material.constructor.prototype.constructor === Object ? null : o.material; }); });
await p.evaluate(() => { const M = window.__scene.children.find(o => o.isMesh && o.material && o.material.isMeshStandardMaterial).material.constructor;
  window.__scene.traverse(o => { if (o.name === 'lavaRibbon') { o.material = new M({ color: 0xff0000, emissive: 0xff0000 }); } }); });
await new Promise(r => setTimeout(r, 1200));
await p.screenshot({ path: `${OUT}/probe_red.jpg`, type: 'jpeg', quality: 85 });
console.log('errors', JSON.stringify(errs.slice(0, 10)));
await b.close();
