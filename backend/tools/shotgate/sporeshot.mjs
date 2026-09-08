// A look at the Verdant Fault under spores: a long unguarded belt, three clogs
// on it, a filter lattice keeping the other line clean. Not a gate — a picture.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width:1600, height:900 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1&debug=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, w = ms => new Promise(r => setTimeout(r, ms));
  F.goalIdx = F.GOALS.length; F.addCores(9);
  F.travelTo(F.WORLDS.findIndex(x => x.spores)); F.endIntro(); await w(500);
  const f = F.player.face;
  // an exposed line along j = 6, and a guarded one along j = 12 with filters beside it
  for (let i = 3; i < F.N - 3; i++) { if (F.cells[f][i][6].t === TY.EMPTY) F.place(f, i, 6, TY.BELT, 0); }
  for (let i = 3; i < F.N - 3; i++) { if (F.cells[f][i][12].t === TY.EMPTY) F.place(f, i, 12, TY.BELT, 0); }
  for (let i = 4; i < F.N - 3; i += 6) { if (F.cells[f][i][14].t === TY.EMPTY) F.place(f, i, 14, TY.FILTER, 0); }
  for (let i = 3; i < F.N - 3; i += 2) { const c = F.cells[f][i][6]; if (c.t === TY.BELT) c.item = TY.CRYSTAL; const d = F.cells[f][i][12]; if (d.t === TY.BELT) d.item = TY.CRYSTAL; }
  for (let k = 0; k < 4; k++) F.sporeStrike();
  await w(300);
});
await p.keyboard.press('Tab');                 // the overhead orbit, then wheel in on the lines
await new Promise(r=>setTimeout(r,600));
await p.mouse.move(800, 450);
for (let k = 0; k < 14; k++) { await p.mouse.wheel({ deltaY: -120 }); await new Promise(r=>setTimeout(r,40)); }
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({ path: process.env.OUT || 'spores_look.png' });
await b.close();
