import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,400)));
p.on('console', m => { if (m.type()==='error') console.log('CONSOLE:', m.text().slice(0,300)); });
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log('game:', await p.evaluate(()=>typeof window.__game));
await b.close();
