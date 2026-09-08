import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const U = 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/';
await p.goto(U + '?fresh=1', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
await p.evaluate(()=>{ window.__factory.addCores(12); });
for (const [k, name] of [[0,'prompt'],[1,'ember'],[2,'frost'],[3,'verdant']]) {
  await p.evaluate((i)=>{ const F = window.__factory;
    if (i !== F.worldIdx) F.travelTo(i);
    window.__game.inspect(true); }, k);
  await new Promise(r=>setTimeout(r,1400));
  await p.screenshot({ path: process.env.OUT + '_' + k + '_' + name + '.png' });
  console.log(name, '->', await p.evaluate(()=>window.__game.facts().world_name));
}
await b.close();
