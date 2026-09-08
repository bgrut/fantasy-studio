import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_3/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
const pos = () => p.evaluate(()=>window.__factory.player.pos.toArray().map(v=>+v.toFixed(2)));
console.log('before        :', JSON.stringify(await pos()));
// dispatch the event ourselves, bypassing focus entirely
await p.evaluate(()=>dispatchEvent(new KeyboardEvent('keydown', {code:'KeyW'})));
await new Promise(r=>setTimeout(r,1000));
console.log('after dispatch:', JSON.stringify(await pos()));
await p.evaluate(()=>dispatchEvent(new KeyboardEvent('keyup', {code:'KeyW'})));
// now move the player to the middle of the top face and try again
await p.evaluate(()=>{ const F=window.__factory;
  F.player.pos.set(0, F.HALF + 1.68, 0); F.player.face = 0;
  F.player.fwd.set(0,0,-1); });
await p.evaluate(()=>dispatchEvent(new KeyboardEvent('keydown', {code:'KeyW'})));
await new Promise(r=>setTimeout(r,1500));
console.log('mid-face +1.5s:', JSON.stringify(await pos()),
            'face', await p.evaluate(()=>window.__factory.player.face));
await new Promise(r=>setTimeout(r,7000));
console.log('mid-face +8.5s:', JSON.stringify(await pos()),
            'face', await p.evaluate(()=>window.__factory.player.face),
            'up', JSON.stringify(await p.evaluate(()=>window.__factory.player.up.toArray().map(v=>+v.toFixed(2)))));
await b.close();
