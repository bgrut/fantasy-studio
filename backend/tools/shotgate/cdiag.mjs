import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_3/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
const rd = () => p.evaluate(()=>{
  const F = window.__factory, d = window.__camera.getWorldDirection(new window.__camera.up.constructor());
  return { pos: F.player.pos.toArray().map(v=>+v.toFixed(2)),
           fwd: F.player.fwd.toArray().map(v=>+v.toFixed(2)),
           up: F.player.up.toArray().map(v=>+v.toFixed(2)),
           face: F.player.face, h: +F.player.h.toFixed(2),
           camDir: [d.x,d.y,d.z].map(v=>+v.toFixed(2)),
           calls: window.__renderer.info.render.calls };
});
console.log('rest  :', JSON.stringify(await rd()));
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,1200));
console.log('W 1.2s:', JSON.stringify(await rd()));
await p.keyboard.up('KeyW');
console.log('keys  :', await p.evaluate(()=>{
  const o = {}; ['KeyW'].forEach(k=>o[k]=true); return 'n/a'; }));
await b.close();
