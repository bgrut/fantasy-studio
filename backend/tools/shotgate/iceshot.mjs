// A frozen seam on Frostline, up close, with the rig scraping at it. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4000));
const cold = await p.evaluate(() => window.__factory.WORLDS.findIndex(w => w.ice));
await p.goto(URL + '?fresh=1&nointro=1&world=' + cold, { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let seam = null;
  for (let i = 3; i < F.N - 3 && !seam; i++) for (let j = 4; j < F.N - 3 && !seam; j++) if (F.cells[0][i][j].t === TY.NODE) seam = [i, j];
  const c = F.cells[0][seam[0]][seam[1]];
  for (let k = 0; k < 40 && !(c.ice > 0); k++) F.iceStrike();
  F.place(0, seam[0], seam[1], TY.MINER, 0);
  const wp = F.tileWorld(0, seam[0], seam[1] - 3), look = F.tileWorld(0, seam[0], seam[1]);
  F.player.pos.set(wp[0], F.HALF + 1.5, wp[2]); F.player.face = 0;
  const dx = look[0] - wp[0], dz = look[2] - wp[2], d = Math.hypot(dx, dz);
  F.player.fwd.set(dx / d, 0, dz / d); F.player.pitch = -Math.atan2(1.2, d);
  if (F.setHolo) F.setHolo(null);
  await new Promise(r => setTimeout(r, 700));
});
await p.screenshot({ path: (process.env.OUT || 'ice') + '_seam.png' });
await b.close();
