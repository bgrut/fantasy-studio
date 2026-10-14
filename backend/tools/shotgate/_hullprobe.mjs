// Where the hero's hull sits against the water. J=job_1393 node _hullprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 120000 });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000));
console.log(JSON.stringify(await p.evaluate(() => {
  let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
  const B3 = new (window.__scene.position.constructor.prototype.constructor)();
  const box = { min: [1e9, 1e9, 1e9], max: [-1e9, -1e9, -1e9] };
  pl.updateMatrixWorld(true);
  const V = window.__scene.position.constructor, v = new V();
  pl.traverse(o => { if (o.isMesh && o.geometry && o.geometry.attributes.position) { const pa = o.geometry.attributes.position;
    for (let i = 0; i < pa.count; i += 7) { v.fromBufferAttribute(pa, i).applyMatrix4(o.matrixWorld); for (let k = 0; k < 3; k++) { box.min[k] = Math.min(box.min[k], v.getComponent(k)); box.max[k] = Math.max(box.max[k], v.getComponent(k)); } } } });
  let water = null; window.__scene.traverse(o => { if (o.isMesh && o.material && o.material.userData && o.material.userData.waterKind && water === null) water = [o.name, o.position.y]; });
  const ships = []; pl.traverse(o => { if (o.userData && o.userData.ship) ships.push([o.position.y, o.scale.x, o.parent && o.parent.position.y]); });
  return { pos: window.__game.pos(), holderY: pl.position.y, box, water, ships, facts: (window.__game.facts().hero || null) };
})));
await b.close();
