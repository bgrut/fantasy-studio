// Any scene, four ways: as played, at eye height toward the goal, high over
// the field toward the goal, and (when the world has one) at the waterfall.
// Prints the facts a scene can be wrong about and any errors, and writes
// scene_<job>_<view>.jpg.     J=job_520 OUT=<dir> node sceneshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900 });
const errs = [];
p.on('pageerror', e => errs.push(e.message));
p.on('console', m => { if (m.type() === 'error' || /skipped/.test(m.text())) errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 2500));
await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 3000));
const info = await p.evaluate(() => {
  const f = window.__game && window.__game.facts ? window.__game.facts() : {};
  return { archetype: f.archetype, water: f.water_kind, water_level: f.water_level, mist: f.mist, waterfall: f.waterfall, lava: !!f.lava,
           hero: f.hero, light: f.light, calls: window.__frameCalls, tris: window.__frameTris };
});
console.log(JSON.stringify(info));
const tag = `${OUT}/scene_${J}`;
await p.screenshot({ path: `${tag}_play.jpg`, type: 'jpeg', quality: 88 });
const geo = await p.evaluate(() => {
  const L = window.__spec.world.level || {}, pp = window.__game.pos();
  const g = L.goal || [pp[0] + 50, pp[2]];
  const fs = window.__scene.getObjectByName('waterfall');
  return { pp, g, falls: fs ? [fs.position.x, fs.position.y, fs.position.z] : null };
});
const dx = geo.g[0] - geo.pp[0], dz = geo.g[1] - geo.pp[2], dl = Math.hypot(dx, dz) || 1;
const shots = {
  // a pace ahead of the hero: at the hero's own spot the camera sat inside
  // their head, and their hair filled the frame like a tiled boulder
  eye: { pos: [geo.pp[0] + dx / dl * 1.5, geo.pp[1] + 1.7, geo.pp[2] + dz / dl * 1.5], look: [geo.pp[0] + dx / dl * 60, geo.pp[1] + 3, geo.pp[2] + dz / dl * 60] },
  high: { pos: [geo.pp[0] - dx / dl * 20, geo.pp[1] + 40, geo.pp[2] - dz / dl * 20], look: [geo.g[0], 0, geo.g[1]] },
};
if (geo.falls) {
  const f = geo.falls, ex = geo.pp[0] - f[0], ez = geo.pp[2] - f[2], el = Math.hypot(ex, ez) || 1;
  shots.falls = { pos: [f[0] + ex / el * 26, f[1] + 3.5, f[2] + ez / el * 26], look: [f[0], f[1] + 6, f[2]] };
}
for (const [k, v] of Object.entries(shots)) {
  await p.evaluate(v => { window.__camPin = v; }, v);
  await new Promise(r => setTimeout(r, 1800));
  await p.screenshot({ path: `${tag}_${k}.jpg`, type: 'jpeg', quality: 88 });
}
console.log('errors', JSON.stringify(errs.slice(0, 12)));
await b.close();
