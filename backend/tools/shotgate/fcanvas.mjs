import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const c = window.__renderer.domElement;
  const r = c.getBoundingClientRect();
  return { win:[innerWidth,innerHeight], css:[+r.width.toFixed(0),+r.height.toFixed(0),+r.top.toFixed(0)],
           attr:[c.width,c.height], style: c.getAttribute('style'),
           bodyBg: getComputedStyle(document.body).backgroundColor,
           htmlBg: getComputedStyle(document.documentElement).backgroundColor,
           aspect: window.__camera.aspect };
}), null, 1));
await b.close();
