import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1&nointro=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6500));
// the hub's board, up close
await p.evaluate(()=>{ const F = window.__factory;
  F.player.pos.x += 9; F.player.pitch = -0.05; F.player.fwd.set(1, 0, 0); });
await new Promise(r=>setTimeout(r,500));
await p.screenshot({ path: process.env.OUT + '_board.png' });
// the meltdown, mid pull-back
await p.evaluate(()=>{ const F = window.__factory; F.addValue(600); F.meltdown(); });
await new Promise(r=>setTimeout(r,1100));
await p.screenshot({ path: process.env.OUT + '_melt.png' });
await new Promise(r=>setTimeout(r,2500));
// each world's ground, from standing height
for (const [k, name] of [[1,'ember'],[2,'frost'],[3,'verdant']]) {
  await p.evaluate((i)=>{ const F = window.__factory; F.addCores(20); F.travelTo(i); F.endIntro();
    F.player.pitch = -0.55; }, k);
  await new Promise(r=>setTimeout(r,1400));
  await p.screenshot({ path: process.env.OUT + '_' + name + '.png' });
}
console.log('shots done');
await b.close();
