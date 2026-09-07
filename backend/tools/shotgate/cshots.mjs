import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,7000));
const OUT = process.env.OUT;
const face = () => p.evaluate(()=>window.__game.facts().player_face);
await p.screenshot({ path: OUT + '_1_top.png' });
console.log('1 top face   :', await face());

// walk to the edge and over it
await p.keyboard.down('KeyW');
let shot = false;
for (let k = 0; k < 30 && !shot; k++) {
  await new Promise(r=>setTimeout(r,250));
  if (await face() !== 'top') { shot = true; }
}
await p.keyboard.up('KeyW');
await new Promise(r=>setTimeout(r,250));
await p.screenshot({ path: OUT + '_2_crossing.png' });
console.log('2 just over  :', await face());

// keep going down the side, then look back up
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,2200));
await p.keyboard.up('KeyW');
await p.evaluate(()=>{ window.__factory.player.pitch = 0.55; });   // look up the wall
await new Promise(r=>setTimeout(r,600));
await p.screenshot({ path: OUT + '_3_wall.png' });
console.log('3 on the side:', await face(), '| pos',
  JSON.stringify((await p.evaluate(()=>window.__game.pos())).map(v=>+v.toFixed(1))));

// and an orbit view of the whole worldlet
await p.keyboard.press('Tab');
await new Promise(r=>setTimeout(r,900));
await p.screenshot({ path: OUT + '_4_orbit.png' });
console.log('4 overhead   : done');
await b.close();
