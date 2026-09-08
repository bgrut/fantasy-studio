import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
await p.screenshot({ path: process.env.OUT + '_1_start.png' });
// trip the first unlock so the toast is on screen
await p.evaluate(()=>window.__factory.addValue(60));
await new Promise(r=>setTimeout(r,700));
await p.screenshot({ path: process.env.OUT + '_2_unlock.png' });
console.log('goal now:', await p.evaluate(()=>window.__game.facts().goal));
await b.close();
