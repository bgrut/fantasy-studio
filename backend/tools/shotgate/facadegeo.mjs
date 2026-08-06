// Street-level facade judgement, the way the handoff insists on it: stand on
// the pavement, look at a building CORNER, with its neighbours in frame.
// Corners are read out of the level's own OSM footprints (fetched from the
// dist's spec.json) rather than guessed, so the shot is always pointed at a
// wall instead of at whatever happened to be ahead.
//
// Usage: node tools/shotgate/facadegeo.mjs <jobId> [tag]
import puppeteer from 'puppeteer-core';

const JOB = process.argv[2], TAG = process.argv[3] || 'fg';
if (!JOB) { console.error('usage: facadegeo.mjs <jobId> [tag]'); process.exit(1); }

const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
});
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 240)));

await p.goto(`http://127.0.0.1:8789/games/job_${JOB}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 4000));
if (await p.evaluate(() => typeof window.__game) !== 'object') {
  console.log('DEAD'); await b.close(); process.exit(2);
}
console.log('stats:', JSON.stringify(await p.evaluate(() => window.__game.stats())));
// instanced census: a trim pass that emitted zero instances must not be able
// to pass as shipped
console.log('census:', JSON.stringify(await p.evaluate(() => {
  const rig = (window.__cars || [])[0] && window.__cars[0].rig;
  if (!rig || !rig.parent) return 'no handle';
  const o = [];
  rig.parent.traverse(m => { if (m.isInstancedMesh && m.count) o.push(m.count); });
  return o;
})));

// building footprints from the level spec
const blds = await p.evaluate(async () => {
  const s = await (await fetch('spec.json')).json();
  const osm = s.world && s.world.level && s.world.level.osm;
  return osm && osm.buildings ? osm.buildings.map(x => ({ pts: x.pts, h: x.h })) : [];
});
console.log('buildings:', blds.length);

const shot = async (n) => {
  await new Promise(r => setTimeout(r, 1500));
  await p.screenshot({ path: `${TAG}_${n}.jpg`, quality: 90, type: 'jpeg' });
  console.log('shot', `${TAG}_${n}.jpg`);
};

// pick the corners furthest from the map centre-line so the shot has a real
// street in front of it, then stand back along the corner's outward bisector
const cands = [];
for (const bl of blds) {
  const c = bl.pts.reduce((a, q) => [a[0] + q[0] / bl.pts.length, a[1] + q[1] / bl.pts.length], [0, 0]);
  for (const q of bl.pts) {
    const d = Math.hypot(q[0] - c[0], q[1] - c[1]);
    if (d > 6) cands.push({ q, c, d });
  }
}
cands.sort((a, z) => z.d - a.d);
let taken = 0;
for (const k of cands) {
  if (taken >= 5) break;
  const ox = (k.q[0] - k.c[0]) / k.d, oz = (k.q[1] - k.c[1]) / k.d;   // outward
  const D = 17;
  const px = k.q[0] + ox * D, pz = k.q[1] + oz * D;
  if (Math.abs(px) > 150 || Math.abs(pz) > 150) continue;
  await p.evaluate((v) => window.__game.tp(v[0], v[1]), [px, pz]);
  await new Promise(r => setTimeout(r, 800));
  // face back at the corner; pitch floored at 0.02 = as far up as the
  // follow-cam is allowed to look
  await p.evaluate((y) => window.__game.aim(y, 0.02), Math.atan2(-ox, -oz));
  await shot('corner' + taken);
  taken++;
}
await b.close();
