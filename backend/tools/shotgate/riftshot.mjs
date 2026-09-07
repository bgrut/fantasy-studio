import puppeteer from 'puppeteer-core';

const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const SHOT_URL = 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/';
await p.goto(SHOT_URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
// stand a rift and its outfeed right in front of the player
await p.evaluate(()=>{
  const F = window.__factory, TY = F.TYPES;
  const t = F.faceOfPoint ? null : null;
  // three tiles ahead of the spawn, on the top face
  const p0 = F.player.pos;
  const face = 0, i = Math.floor(p0.x / F.T + F.N / 2), j = Math.floor(-p0.z / F.T + F.N / 2) - 3;
  F.place(face, i, j, TY.RIFT, 0);
  const out = F.stepTile(face, i, j, 0);
  F.place(out.face, out.i, out.j, TY.BELT, out.d);
  const out2 = F.stepTile(out.face, out.i, out.j, out.d);
  F.place(out2.face, out2.i, out2.j, TY.BELT, out2.d);
  F.player.pitch = -0.22;
});
await new Promise(r=>setTimeout(r,2600));
console.log('rift:', JSON.stringify(await p.evaluate(()=>window.__game.facts().rift)));
await p.screenshot({ path: process.env.OUT });
await b.close();
