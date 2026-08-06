// Close-up pass: the car from three angles, a roofline from far enough back
// that the near-horizontal follow-cam contains it, and a scene census that
// counts the parapet/bulkhead instances directly (the scene is reachable
// through any parked car's rig.parent — no debug hook shipped to players).
//
// Usage: node tools/shotgate/facadecar2.mjs <jobId> [tag]
import puppeteer from 'puppeteer-core';

const JOB = process.argv[2], TAG = process.argv[3] || 'cc';
if (!JOB) { console.error('usage: facadecar2.mjs <jobId> [tag]'); process.exit(1); }

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

// scene census — instanced meshes by count, so a parapet that produced zero
// instances cannot pass as "shipped"
console.log('census:', JSON.stringify(await p.evaluate(() => {
  const rig = (window.__cars || [])[0] && window.__cars[0].rig;
  if (!rig || !rig.parent) return 'no scene handle';
  const out = [];
  rig.parent.traverse(o => {
    if (o.isInstancedMesh) {
      const g = o.geometry.type, pm = o.geometry.parameters || {};
      out.push(`${g}(${Math.round((pm.width || pm.radiusTop || 0) * 100) / 100})x${o.count}`);
    }
  });
  return out;
})));

const shot = async (name) => {
  await new Promise(r => setTimeout(r, 1300));
  await p.screenshot({ path: `${TAG}_${name}.jpg`, quality: 88, type: 'jpeg' });
  console.log('shot:', `${TAG}_${name}.jpg`);
};
// put the player d metres SHORT of a target and face it, so the follow-cam
// (which sits behind the player) frames the target head-on
const look = async (tx, tz, d, ang) => {
  await p.evaluate((a) => window.__game.tp(a[0], a[1]),
    [tx - Math.sin(ang) * d, tz - Math.cos(ang) * d]);
  await new Promise(r => setTimeout(r, 700));
  await p.evaluate((a) => window.__game.aim(a[0], a[1]), [ang, 0.02]);
};

const car = await p.evaluate(() => {
  const c = (window.__cars || [])[0];
  return c ? [c.x, c.z, c.yaw] : null;
});
if (car) {
  for (const [i, ang] of [0, Math.PI / 2, Math.PI * 0.75].entries()) {
    await look(car[0], car[1], 5.5, ang);
    await shot('car' + i);
  }
}
// roofline: stand well back from the tallest thing near the spawn
for (const [i, tgt] of [[40, 40], [-45, 35], [55, -30]].entries()) {
  await look(tgt[0], tgt[1], 46, Math.atan2(tgt[0], tgt[1]));
  await shot('roof' + i);
}
await b.close();
