// A city prompt gets a city, with or without a map. The build carries a
// district in the map's own shape (buildings with footprints and heights,
// roads with widths, a race route on the streets), the runtime draws it as
// a city, and a neon night prompt is not rendered as a quarter-res pixel
// filter from the top down.
//   A=<adventure job id built from a city prompt>
import puppeteer from 'puppeteer-core';
if (!process.env.A) { console.log('SKIPPED   : no adventure job given (factory_check --adv N)'); process.exit(0); }
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const URL = 'http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/';

const spec = await (await fetch(URL + 'spec.json')).json();
const osm = ((spec.world || {}).level || {}).osm || null;
const route = ((spec.world || {}).level || {}).path || null;
console.log('the spec  : style', spec.style, '| view', spec.view, '| world', JSON.stringify(spec.world.name), spec.world.size_m + ' m',
            '| district', osm ? osm.buildings.length + ' buildings, ' + osm.roads.length + ' roads' + (osm.procedural ? ' (procedural)' : ' (map)') : 'NONE',
            '| route', route ? route.length + ' pts' : 'none');

await p.goto(URL, { waitUntil:'domcontentloaded', timeout:120000 });
await wait(9000);
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await wait(1500);
await p.keyboard.down('KeyW'); await wait(3000); await p.keyboard.up('KeyW');
const live = await p.evaluate(() => {
  const sc = window.__scene, cv = document.querySelector('canvas');
  let meshes = 0, tris = 0;
  sc.traverse(o => { if (o.isMesh && o.visible) { meshes++; const g = o.geometry; if (g && g.index) tris += g.index.count / 3; else if (g && g.attributes.position) tris += g.attributes.position.count / 3; } });
  return { isCity: !!window.__isCity, meshes, tris: Math.round(tris), canvas: [cv.width, cv.height], style: document.body.className, camY: +window.__camera.position.y.toFixed(1) };
});
console.log('the scene : city', live.isCity, '| meshes', live.meshes, '| tris', live.tris, '| canvas', live.canvas.join('x'), '| body', live.style, '| camera y', live.camY);
await p.screenshot({ path: process.env.OUT || 'city.png' });
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();

const ok = osm && osm.buildings.length >= 60 && osm.roads.length >= 8 && route && route.length >= 20
  && spec.style !== 'pixel' && spec.view !== 'topdown'
  && live.isCity && live.canvas[0] >= 640 && live.tris > 100000
  && errs.length === 0;
process.exit(ok ? 0 : 1);
