// The lava hazard: inLava is true in a channel, false at the spawn and on a
// bridge; walking the hero into a channel costs a heart and puts them back.
import puppeteer from 'puppeteer-core';
const J = process.env.J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1000, height: 600 });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1500));
const r = await p.evaluate(() => {
  const L = window.__spec.world.level, n = L.grid_n, sz = L.size_m, V = window.__volc;
  let deep = null;
  const pp = window.__game.pos();
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const h = L.heights[i * n + j]; const x = (j / (n - 1) - 0.5) * sz, z = (i / (n - 1) - 0.5) * sz;
    if (h < -1.3) { const d = Math.hypot(x - pp[0], z - pp[2]); if (!deep || d < deep.d) deep = { x, z, d }; }
  }
  return { deep, inDeep: V.inLava(deep.x, deep.z), inSpawn: V.inLava(pp[0], pp[2]), edgeSpawn: +V.edgeDist(pp[0], pp[2]).toFixed(1), pp };
});
console.log(JSON.stringify(r));
// walk the hero toward the deep point: face it with the camera yaw and hold W
const hearts0 = await p.evaluate(() => document.querySelectorAll('#hearts .full, #hearts span').length);
await p.evaluate((d) => { const pp = window.__game.pos(); window.__aimAt = Math.atan2(d.x - pp[0], d.z - pp[2]); }, r.deep);
const before = await p.evaluate(() => window.__game.pos());
await p.keyboard.down('KeyW');
for (let k = 0; k < 40; k++) {
  await p.evaluate((d) => { const g = window.__game; if (g.setYaw) { const pp = g.pos(); g.setYaw(Math.atan2(-(d.x - pp[0]), -(d.z - pp[2]))); } }, r.deep);
  await new Promise(r2 => setTimeout(r2, 250));
}
await p.keyboard.up('KeyW');
const after = await p.evaluate(() => ({ pos: window.__game.pos(), facts: window.__game.facts ? window.__game.facts().hp : null }));
console.log('walk', JSON.stringify({ before, after }));
await b.close();
