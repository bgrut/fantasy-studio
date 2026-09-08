import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('response', r => { if (r.status() >= 400) console.log(r.status(), r.url()); });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
p.on('console', m => console.log(m.type()+':', m.text().slice(0,300)));
await p.goto('http://127.0.0.1:8789/games/1/dist/', { waitUntil:'networkidle2', timeout:60000 });
await new Promise(r=>setTimeout(r,4000));
console.log('__game:', await p.evaluate(()=>typeof window.__game));
await b.close();
