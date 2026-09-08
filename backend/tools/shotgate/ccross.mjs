import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_3/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const F = window.__factory, out = {};
  out.HALF = F.HALF;
  out.faceNormals = F.FACES.map(f => f.name + ':' + f.n.join(','));
  // put the player one metre PAST the top face's far edge and let a frame run
  F.player.pos.set(0, F.HALF + 1.68, -(F.HALF + 1));
  F.player.face = 0;
  out.before = { pos: F.player.pos.toArray().map(v=>+v.toFixed(2)), face: F.player.face };
  return out;
}), null, 1));
await new Promise(r=>setTimeout(r,500));
console.log('after a frame:', JSON.stringify(await p.evaluate(()=>({
  pos: window.__factory.player.pos.toArray().map(v=>+v.toFixed(2)),
  face: window.__factory.player.face,
  up: window.__factory.player.up.toArray(),
}))));
await b.close();
