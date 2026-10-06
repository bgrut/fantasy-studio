// Every kind of animal in a level, one close look each: side-on from about
// three metres at its own height, in the level's light.
//   J=job_N OUT=<dir> TAG=<name> node animalshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1200, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 11000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1000));
const kinds = await p.evaluate(() => {
  const refs = window.__game.npcRefs ? window.__game.npcRefs() : [];
  const seen = {};
  for (const r of refs) { const n = r.name || r.kind; if (!n || seen[n] !== undefined) continue; seen[n] = refs.indexOf(r); }
  return Object.entries(seen).slice(0, 5);
});
const shot = [];
for (const [name, idx] of kinds) {
  const ok = await p.evaluate((idx) => {
    const r = window.__game.npcRefs()[idx], o = r.obj;
    if (!o) return false;
    const q = o.position, yaw = o.rotation.y;
    // its side: perpendicular to the way it faces
    const sx = Math.cos(yaw), sz = -Math.sin(yaw);
    // its size from its meshes' bounding spheres (THREE is not on the window)
    let rad = 0.4;
    o.updateMatrixWorld(true);
    o.traverse(m => { if (m.isMesh && m.geometry) { m.geometry.computeBoundingSphere();
      rad = Math.max(rad, m.geometry.boundingSphere.radius * m.matrixWorld.getMaxScaleOnAxis()); } });
    const h = Math.min(3, rad * 1.1);
    const d = Math.max(2.2, h * 2.2);
    window.__camPin = { pos: [q.x + sx * d, q.y + h * 0.75, q.z + sz * d], look: [q.x, q.y + h * 0.5, q.z] };
    return true;
  }, idx);
  if (!ok) continue;
  await new Promise(r => setTimeout(r, 700));
  const f = `${OUT}/${TAG}_${name.replace(/\W+/g, '_')}.jpg`;
  await p.screenshot({ path: f, type: 'jpeg', quality: 92 });
  shot.push(name);
}
console.log(TAG, JSON.stringify(shot), JSON.stringify(errs.slice(0, 3)));
await b.close();
