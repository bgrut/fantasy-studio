import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_3/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const F = window.__factory;
  const pos = { x:0, y:F.HALF+1.68, z:-(F.HALF+1) };
  const f = F.FACES[0];
  const a = pos.x*f.u[0] + pos.y*f.u[1] + pos.z*f.u[2];
  const bb = pos.x*f.v[0] + pos.y*f.v[1] + pos.z*f.v[2];
  return { u:f.u, v:f.v, n:f.n, a, b:bb, HALF:F.HALF,
           wouldFire: (a > F.HALF) || (a < -F.HALF) || (bb > F.HALF) || (bb < -F.HALF) };
}), null, 1));
// and what does the SERVED source say the clamp order is?
const src = await p.evaluate(async ()=> (await (await fetch('./game.js')).text()));
const i = src.indexOf('function movePlayer');
console.log('--- served movePlayer tail ---');
console.log(src.slice(i, i + 2600).split('\n').slice(-26).join('\n'));
await b.close();
