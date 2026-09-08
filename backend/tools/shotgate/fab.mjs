import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
await p.screenshot({ path: process.env.OUT + '_a.png' });
const before = await p.evaluate(()=>({ fog: !!window.__scene.fog }));
await p.evaluate(()=>{ window.__scene.fog = null;
  window.__scene.traverse(o=>{ if(o.isMesh) o.material.needsUpdate = true; }); });
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({ path: process.env.OUT + '_b.png' });
console.log('same load, fog on then off;', JSON.stringify(before));
await b.close();
