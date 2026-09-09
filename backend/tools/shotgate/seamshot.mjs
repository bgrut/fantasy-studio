// A seam up close, fresh and worked: the glow, the core, the pool on the ground.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, w = ms => new Promise(r => setTimeout(r, ms));
  // two seams on the top face: leave one fresh, work the other down
  const seams = [];
  for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[0][i][j].t === TY.NODE) seams.push([i, j]);
  const [a, bb] = seams;
  F.cells[0][bb[0]][bb[1]].rich = 0.12;
  // stand two tiles south of the fresh one, looking at it
  const wp = F.tileWorld(0, a[0], Math.max(1, a[1] - 3));
  F.player.pos.set(wp[0], F.HALF + 1.6, wp[2]);
  F.player.face = 0; if (F.setHolo) F.setHolo(null); document.querySelectorAll('.tool.on').forEach(o => o.classList.remove('on'));
  const look = F.tileWorld(0, a[0], a[1]);
  window.__camera.position.copy(F.player.pos);
  window.__camera.lookAt(look[0], look[1] + 0.3, look[2]);
  await w(600);
});
await p.screenshot({ path: (process.env.OUT || 'seam') + '_fresh.png' });
await b.close();
