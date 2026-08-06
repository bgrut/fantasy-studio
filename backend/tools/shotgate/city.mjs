// City-look gate: street-level shots + draw-call/program budget.
// usage: node city.mjs <jobid> <outdir>
import puppeteer from 'puppeteer-core';
import fs from 'fs';

const job = process.argv[2], out = process.argv[3] || ('city_' + job);
fs.mkdirSync(out, { recursive: true });

const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
});
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 220)));
p.on('console', m => { const t = m.text(); if (/error|warn|skipped|budget|LIGHT/i.test(t)) console.log('LOG:', t.slice(0, 200)); });

await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 60000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 4000));

console.log('alive:', await p.evaluate(() => typeof window.__game));

const stats = await p.evaluate(() => {
  const r = window.__renderer || (window.__game && window.__game.renderer);
  return r ? { calls: r.info.render.calls, tris: r.info.render.triangles, programs: r.info.programs.length } : null;
});
console.log('STATS:', JSON.stringify(stats));
console.log('cars:', JSON.stringify(await p.evaluate(() => (window.__game.cars ? window.__game.cars() : []).length)));
console.log('peds:', await p.evaluate(() => (window.__peds || []).length));
console.log('traffic:', await p.evaluate(() => (window.__traffic || []).length));

// street-level tour: teleport to a few spots and look around
const spec = await (await fetch(`http://127.0.0.1:8789/games/job_${job}/dist/spec.json`)).json();
const O = spec.world.level.osm || {};
const spots = [];
for (let i = 0; i < (O.roads || []).length && spots.length < 5; i += Math.max(1, Math.floor(O.roads.length / 7))) {
  const m = O.roads[i].pts[Math.floor(O.roads[i].pts.length / 2)];
  if (m && Math.hypot(m[0], m[1]) < 220) spots.push([m[0], m[1]]);
}

let n = 0;
for (const s of [[0, 0], ...spots]) {
  await p.evaluate(([x, z]) => window.__game.tp(x, z), s);
  await new Promise(r => setTimeout(r, 1400));
  await p.screenshot({ path: `${out}/s${n}_${s[0].toFixed(0)}_${s[1].toFixed(0)}.jpg`, type: 'jpeg', quality: 85 });
  n++;
}

// fps over 3s
const fps = await p.evaluate(() => new Promise(res => {
  let f = 0; const t0 = performance.now();
  const tick = () => { f++; if (performance.now() - t0 < 3000) requestAnimationFrame(tick); else res(Math.round(f / ((performance.now() - t0) / 1000))); };
  requestAnimationFrame(tick);
}));
console.log('fps:', fps);
const stats2 = await p.evaluate(() => {
  const r = window.__renderer || (window.__game && window.__game.renderer);
  return r ? { calls: r.info.render.calls, tris: r.info.render.triangles, programs: r.info.programs.length } : null;
});
console.log('STATS_END:', JSON.stringify(stats2));
await b.close();
