// Items up close — an ore chunk, an ingot bar and an alloy bar held on three
// belts that lead nowhere — and the starter rig throwing sparks. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
const aim = async (fromTile, atTile, h) => p.evaluate(([ft, at, hh]) => {
  const F = window.__factory;
  const wp = F.tileWorld(0, ft[0], ft[1]), look = F.tileWorld(0, at[0], at[1]);
  F.player.pos.set(wp[0], F.HALF + hh, wp[2]); F.player.face = 0;
  // the camera follows the player's heading and pitch every frame, so those
  // are what to set: heading toward the target in the face plane, pitch down
  const dx = look[0] - wp[0], dz = look[2] - wp[2], dist = Math.hypot(dx, dz);
  F.player.fwd.set(dx / dist, 0, dz / dist);
  F.player.pitch = -Math.atan2(hh - 0.3, dist);
  if (F.setHolo) F.setHolo(null);
}, [fromTile, atTile, h]);

// three belts in a clear row, each holding one kind, pointing into empty tiles
const spot = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES;
  let s = null;
  for (let i = 3; i < F.N - 5 && !s; i++) for (let j = 3; j < F.N - 4 && !s; j++)
    if ([0, 1, 2, 3].every(k => F.cells[0][i][j + k].t === TY.EMPTY) && F.cells[0][i + 1][j].t === TY.EMPTY
        && F.cells[0][i + 1][j + 1].t === TY.EMPTY && F.cells[0][i + 1][j + 2].t === TY.EMPTY) s = [i, j];
  const [i, j] = s;
  F.place(0, i, j, TY.BELT, 0); F.place(0, i, j + 1, TY.BELT, 0); F.place(0, i, j + 2, TY.BELT, 0);
  F.cells[0][i][j].item = TY.CRYSTAL; F.cells[0][i][j + 1].item = TY.INGOT; F.cells[0][i][j + 2].item = TY.ALLOY;
  return s;
});
await aim([spot[0] - 2, spot[1] + 1], [spot[0], spot[1] + 1], 1.5);
await new Promise(r=>setTimeout(r,700));
await p.screenshot({ path: (process.env.OUT || 'items') + '_items.png' });

// the rig, close, mid-extraction
const rig = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES;
  for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[0][i][j].t === TY.MINER) return [i, j];
  return null;
});
if (rig) {
  await aim([rig[0] - 2, rig[1] + 1], rig, 1.4);
  await new Promise(r=>setTimeout(r,400));
  await p.screenshot({ path: (process.env.OUT || 'items') + '_rig.png' });
}
await b.close();
