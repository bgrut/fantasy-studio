// The foreman's first card over a new world, and the look label on the smelter. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.screenshot({ path: (process.env.OUT || 'foreman') + '_step1.png' });
await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  F.tutIdx = 1;                                      // the line step: ring on the hub
  // aim at the starter smelter from two tiles away
  let sm = null; for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[0][i][j].t === TY.SMELTER && !sm) sm = [i, j];
  const wp = F.tileWorld(0, sm[0], sm[1] + 2), look = F.tileWorld(0, sm[0], sm[1]);
  F.player.pos.set(wp[0], F.HALF + 1.6, wp[2]); F.player.face = 0;
  const dx = look[0] - wp[0], dz = look[2] - wp[2], d = Math.hypot(dx, dz);
  F.player.fwd.set(dx / d, 0, dz / d); F.player.pitch = -Math.atan2(1.6, d);
  await new Promise(r => setTimeout(r, 900));
});
await p.screenshot({ path: (process.env.OUT || 'foreman') + '_look.png' });
console.log(await p.evaluate(() => JSON.stringify({ look: window.__game.facts().look, tut: window.__game.facts().tutorial })));
await b.close();
