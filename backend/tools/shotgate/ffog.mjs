import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>({
  fogType: window.__scene.fog.constructor.name,
  fogCol: '#'+window.__scene.fog.color.getHexString(),
  near: window.__scene.fog.near, far: window.__scene.fog.far,
  bg: '#'+window.__scene.background.getHexString(),
  HALF: window.__factory.N * window.__factory.T / 2,
}))));
await b.close();
