// side-view platformer: where are the camera, the hero, the water and the islands? J=job_N
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 4000));
if (process.env.TX) { await p.evaluate(x => window.__game.tp(+x, 0), process.env.TX); await new Promise(r => setTimeout(r, 2500)); }
console.log(JSON.stringify(await p.evaluate(() => {
  const c = window.__camera, s = window.__scene; const w = s.getObjectByName('islandSea') || null;
  let water = null; s.traverse(o => { if (!water && o.isMesh && o.material && o.material.userData && o.material.userData.waterKind) water = o; });
  return { cam: c.position.toArray().map(v => +v.toFixed(2)), pos: window.__game.pos().map(v => +v.toFixed(2)), water: water ? +water.position.y.toFixed(2) : null, waterKind: window.__waterKind,
    tops: (window.__platformTops || []).slice(0, 4), spec: { lvl: window.__spec && window.__spec.world.water_level, arch: window.__spec && window.__spec.world.archetype } };
})));
await p.screenshot({ path: process.env.OUT || 'side.jpg', type: 'jpeg', quality: 80 });
await b.close();
