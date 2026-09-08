import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1&nointro=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6500));
console.log(JSON.stringify(await p.evaluate(()=>{
  const F = window.__factory, TY = F.TYPES;
  // FIND the hub rather than guessing where the line put it
  let hub = null;
  F.cells.forEach((face, f) => face.forEach((col, i) => col.forEach((c, j) => {
    if (c.t === TY.HUB && !hub) hub = { f, i, j, d: c.d };
  })));
  if (!hub) return { hub: null };
  // stand two and a half tiles in front of the board (it faces the hub's +X,
  // which is its heading), looking back at it
  const w = F.tileWorld(hub.f, hub.i, hub.j);
  const dv = F.FACES[hub.f].u;                          // heading 0 is +u
  const fwd = [dv[0], dv[1], dv[2]];
  F.player.face = hub.f;
  F.player.pos.set(w[0] + fwd[0] * F.T * 2.6, F.HALF + 1.68, w[2] + fwd[2] * F.T * 2.6);
  F.player.fwd.set(-fwd[0], -fwd[1], -fwd[2]);
  F.player.pitch = -0.02;
  return { hub, stood: F.player.pos.toArray().map(v => +v.toFixed(1)) };
})));
await new Promise(r=>setTimeout(r,700));
await p.screenshot({ path: process.env.OUT });
await b.close();
