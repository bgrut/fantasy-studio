import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const T = window.__factory;
  const out = { factoryKeys: T ? Object.keys(T) : null,
                player: window.__game.pos().map(v=>+v.toFixed(2)) };
  // what colour is the material of the nearest big thing straight ahead?
  const s = window.__scene;
  const near = [];
  const pp = window.__camera.position;
  s.traverse(o => {
    if (!o.isMesh) return;
    const w = o.getWorldPosition(new pp.constructor());
    const d = w.distanceTo(pp);
    if (d < 14) near.push({ d:+d.toFixed(2),
      col: o.material && o.material.color ? '#'+o.material.color.getHexString() : '?',
      pos: [w.x,w.y,w.z].map(v=>+v.toFixed(1)),
      geo: o.geometry.type,
      sz: o.geometry.parameters ? Object.values(o.geometry.parameters).slice(0,3) : null });
  });
  near.sort((a,b)=>a.d-b.d);
  out.nearest = near.slice(0, 8);
  return out;
}), null, 1));
await b.close();
