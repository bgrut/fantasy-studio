import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
// paint the background red: if the purple band turns red, nothing is drawn there
await p.evaluate(()=>{ window.__scene.background.setHex(0xff0000);
  window.__scene.fog = null; });
await new Promise(r=>setTimeout(r,800));
await p.screenshot({ path: process.env.OUT });
console.log('done');
await b.close();
