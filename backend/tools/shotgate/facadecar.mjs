// Verification harness for the 2026-08-06 facade + car pass.
// Proves four things that are only visible in-game: the wall texture is at
// human texel density, the roofline has a parapet standing above it, props
// hang on real walls, and the parametric car is a car rather than a slab.
//
// The default follow-cam looks DOWN at the street, so every shot here aims
// the camera explicitly — a facade check that never contained the facade is
// how the last flat-building pass got signed off.
//
// Usage: node tools/shotgate/facadecar.mjs <jobId> [tag]
import puppeteer from 'puppeteer-core';

const JOB = process.argv[2];
const TAG = process.argv[3] || 'fc';
if (!JOB) { console.error('usage: facadecar.mjs <jobId> [tag]'); process.exit(1); }

const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
});
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 240)));
p.on('console', m => { if (m.type() === 'error') console.log('CONSOLE:', m.text().slice(0, 200)); });

await p.goto(`http://127.0.0.1:8789/games/job_${JOB}/dist/`,
             { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 4000));

const alive = await p.evaluate(() => typeof window.__game);
console.log('alive:', alive);
if (alive !== 'object') { await b.close(); process.exit(2); }
console.log('stats:', JSON.stringify(await p.evaluate(() => window.__game.stats())));
console.log('cars:', await p.evaluate(() => (window.__cars || []).length));

const shot = async (name, x, z, yaw, pitch) => {
  if (x !== undefined) await p.evaluate((a, c) => window.__game.tp(a, c), x, z);
  await new Promise(r => setTimeout(r, 900));
  if (yaw !== undefined) await p.evaluate((y, q) => window.__game.aim(y, q), yaw, pitch);
  await new Promise(r => setTimeout(r, 1200));
  await p.screenshot({ path: `${TAG}_${name}.jpg`, quality: 84, type: 'jpeg' });
  console.log('shot:', `${TAG}_${name}.jpg`, JSON.stringify(await p.evaluate(() => window.__game.pos())));
};

// spawn, camera raised to street-level-looking-up: the texel density check
await shot('1_spawn', undefined, undefined, 0, 0.34);
// out into the block, neighbours side by side (the "do these read as
// different buildings" test the handoff insists on)
await shot('2_block', 34, 30, 1.1, 0.30);
await shot('3_block2', -36, 26, 2.4, 0.28);
// straight up a wall: parapet + roofline silhouette
await shot('4_roof', 34, 30, 1.1, 0.95);
// the car
const car = await p.evaluate(() => {
  const c = (window.__cars || [])[0];
  return c ? { x: c.x, z: c.z, yaw: c.yaw } : null;
});
if (car) {
  await p.evaluate((c) => window.__game.tp(c.x + 6.5, c.z + 6.5), car);
  await shot('5_car', undefined, undefined, Math.PI * 1.25, 0.12);
  await p.evaluate((c) => window.__game.tp(c.x, c.z + 8), car);
  await shot('6_car_side', undefined, undefined, Math.PI, 0.10);
}
await b.close();
