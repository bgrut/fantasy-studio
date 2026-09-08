// Counts kerb instances that sit ON the carriageway. usage: node kerbcheck.mjs <jobid>
import puppeteer from 'puppeteer-core';
const job = process.argv[2];
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const s = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await s(5500); await p.click('#startbtn').catch(() => {}); await s(3000);
const spec = await (await fetch(`http://127.0.0.1:8789/games/job_${job}/dist/spec.json`)).json();
const segs = [];
for (const r of spec.world.level.osm.roads || [])
  for (let i = 0; i < r.pts.length - 1; i++)
    segs.push([r.pts[i][0], r.pts[i][1], r.pts[i + 1][0], r.pts[i + 1][1], (r.w || 7) / 2]);

const res = await p.evaluate((segs) => {
  const segD = (px, pz, x1, z1, x2, z2) => {
    const dx = x2 - x1, dz = z2 - z1, L = dx * dx + dz * dz;
    let t = L ? ((px - x1) * dx + (pz - z1) * dz) / L : 0;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + dx * t), pz - (z1 + dz * t));
  };
  // the kerb is the instanced mesh whose box is 0.15 tall
  let best = null;
  window.__scene.traverse(o => {
    if (!o.isInstancedMesh) return;
    o.geometry.computeBoundingBox();
    const h = o.geometry.boundingBox.max.y - o.geometry.boundingBox.min.y;
    if (Math.abs(h - 0.15) < 0.02 && (!best || o.count > best.count)) best = o;
  });
  if (!best) return { err: 'no kerb mesh' };
  const M = new (window.__scene.constructor === Object ? Object : Object)();
  let on = 0, tot = 0;
  const arr = best.instanceMatrix.array;
  for (let i = 0; i < best.count; i++) {
    const x = arr[i * 16 + 12], z = arr[i * 16 + 14];
    tot++;
    for (const sg of segs) if (segD(x, z, sg[0], sg[1], sg[2], sg[3]) < sg[4] - 0.35) { on++; break; }
  }
  return { total: tot, onRoad: on };
}, segs);
console.log(`job ${job}:`, JSON.stringify(res),
  res.total ? `-> ${(100 * res.onRoad / res.total).toFixed(1)}% of kerb pieces lie in the road` : '');
await b.close();
