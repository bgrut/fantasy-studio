import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_3/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
await p.evaluate(()=>{ const F=window.__factory;
  F.player.pos.set(0, F.HALF + 1.68, -(F.HALF + 1)); F.player.face = 0; });
await new Promise(r=>setTimeout(r,400));
console.log('dbg:', JSON.stringify(await p.evaluate(()=>window.__hits || 'never near an edge')));
await b.close();
