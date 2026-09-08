import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,2200));
await p.screenshot({ path: process.env.OUT + '_intro.png' });
// and Ember's ash, from the ground
await new Promise(r=>setTimeout(r,3000));
await p.evaluate(async ()=>{ const F = window.__factory; F.addCores(20); F.travelTo(1); F.endIntro();
  F.player.pitch = 0.18; });
await new Promise(r=>setTimeout(r,3200));
await p.screenshot({ path: process.env.OUT + '_ash.png' });
await b.close();
