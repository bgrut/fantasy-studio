// A close look at a machine: stand two tiles from it, look at it, shoot. T=type name, OUT
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.goto(process.env.URL + '?fresh=1&nointro=1' + (process.env.Q || ''), { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 3500));
const r = await p.evaluate((T) => {
  const F = window.__factory, TY = F.TYPES; let t = null;
  for (let i = 0; i < F.N && !t; i++) for (let j = 0; j < F.N && !t; j++) if (F.cells[0][i][j].t === TY[T]) t = [i, j];
  if (!t) return 'no ' + T;
  const w = F.tileWorld(0, t[0], t[1]);
  // stand south-west of it, look at it, from a little above
  F.player.pos.set(w[0] - 2.2, F.HALF + 1.5, w[2] + 2.6);
  const dx = w[0] - F.player.pos.x, dz = w[2] - F.player.pos.z;
  F.player.fwd.set(dx, 0, dz).normalize(); F.player.pitch = -0.28;
  document.getElementById('tutor')?.classList.remove('on');
  return { tile: t, world: w.map(v => +v.toFixed(1)) };
}, process.env.T || 'SMELTER');
await new Promise(r => setTimeout(r, 900));
await p.screenshot({ path: process.env.OUT || 'closeup.png' });
console.log(JSON.stringify(r));
await b.close();
