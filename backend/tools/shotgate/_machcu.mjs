// place a machine on an empty tile of the top face in creative and look at it. T=SPLITTER URL= OUT=
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.evaluateOnNewDocument((k) => { window.__COOK = k; }, !!process.env.COOK);
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1&nointro=1&creative=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4500));
console.log(JSON.stringify(await p.evaluate((T) => {
  const F = window.__factory, TY = F.TYPES; let t = null;
  for (let i = 6; i < F.N - 6 && !t; i++) for (let j = 6; j < F.N - 6 && !t; j++) {
    let ok = true; for (let a = -2; a <= 2 && ok; a++) for (let c = -2; c <= 2 && ok; c++) if (F.cells[0][i + a][j + c].t !== TY.EMPTY) ok = false;
    if (ok) t = [i, j]; }
  if (!t) return 'no space';
  const placed = F.place(0, t[0], t[1], TY[T], 0);
  const w = F.tileWorld(0, t[0], t[1]);
  F.player.pos.set(w[0] + 2.4, F.HALF + 1.7, w[2] + 2.4);
  const dx = w[0] - F.player.pos.x, dz = w[2] - F.player.pos.z; F.player.fwd.set(dx, 0, dz).normalize(); F.player.pitch = -0.32;
  document.getElementById('tutor')?.classList.remove('on');
  if (window.__COOK) { const cc = F.cells[0][t[0]][t[1]]; setInterval(() => { cc.cook = 2; }, 50); }
  return { placed, tile: t };
}, process.env.T)));
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: process.env.OUT });
await b.close();
