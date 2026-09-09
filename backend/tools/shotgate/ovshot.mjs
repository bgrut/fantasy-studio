// The overhead as it opens: over the face you stand on, heading up the screen,
// the factory as a city at night. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES;
  // a second line and a few machines so there is a layout to read
  const f = 0; let placed = 0;
  for (let i = 4; i < F.N - 4 && placed < 12; i++) for (let j = 4; j < F.N - 4 && placed < 12; j++) {
    const c = F.cells[f][i][j];
    if (c.t === TY.NODE) { F.place(f, i, j, TY.MINER, 0); placed++; }
  }
  for (let i = 3; i < F.N - 3; i++) if (F.cells[f][i][8].t === TY.EMPTY) F.place(f, i, 8, TY.BELT, 0);
  for (let j = 3; j < F.N - 3; j++) if (F.cells[f][12][j].t === TY.EMPTY) F.place(f, 12, j, TY.BELT, 1);
  F.goalIdx = F.GOALS.length;
  for (const [i, j, t] of [[6, 10, TY.SMELTER], [8, 10, TY.FORGE], [10, 10, TY.SPLITTER], [14, 10, TY.FILTER], [16, 10, TY.HUB]])
    if (F.cells[f][i][j] && F.cells[f][i][j].t === TY.EMPTY) F.place(f, i, j, t, 0);
});
await p.keyboard.press('Tab');
await new Promise(r=>setTimeout(r,900));
await p.screenshot({ path: (process.env.OUT || 'overhead') + '_open.png' });
await b.close();
