import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log('spawn dir:', JSON.stringify(await p.evaluate(()=>{
  const v = new (window.__scene.constructor === Object ? Object : Object)();
  const d = window.__camera.getWorldDirection(new (window.__camera.up.constructor)());
  return { dir: [d.x,d.y,d.z].map(v=>+v.toFixed(2)),
           pos: window.__camera.position.toArray().map(v=>+v.toFixed(1)),
           tris: window.__game.stats().tris };
})));
// force the camera to look at the middle of the island and re-measure
await p.evaluate(()=>{ window.__factory && (window.__factory.player.yaw = Math.PI); });
await new Promise(r=>setTimeout(r,1500));
console.log('after facing -Z:', JSON.stringify(await p.evaluate(()=>{
  const d = window.__camera.getWorldDirection(new (window.__camera.up.constructor)());
  return { dir:[d.x,d.y,d.z].map(v=>+v.toFixed(2)), tris: window.__game.stats().tris,
           calls: window.__game.stats().calls };
})));
await p.screenshot({ path: process.env.OUT });
await b.close();
