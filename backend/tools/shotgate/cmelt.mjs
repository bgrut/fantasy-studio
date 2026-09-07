import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
// back off a little and look at the line, so the collapse is in frame
await p.evaluate(()=>{ const F = window.__factory;
  F.player.pos.z += 6; F.player.pitch = -0.16;
  F.addValue(F.MELT_MIN + 400); });
await new Promise(r=>setTimeout(r,500));
await p.screenshot({ path: process.env.OUT + '_before.png' });
await p.evaluate(()=>window.__factory.meltdown());
for (const [ms, name] of [[260,'a'],[420,'b'],[700,'c']]) {
  await new Promise(r=>setTimeout(r,ms));
  await p.screenshot({ path: process.env.OUT + '_' + name + '.png' });
}
console.log('cores:', await p.evaluate(()=>window.__game.facts().cores),
            '| debris:', await p.evaluate(()=>window.__game.facts().debris));
await new Promise(r=>setTimeout(r,3000));
await p.screenshot({ path: process.env.OUT + '_after.png' });
console.log('after:', JSON.stringify(await p.evaluate(()=>window.__game.facts())));
await b.close();
