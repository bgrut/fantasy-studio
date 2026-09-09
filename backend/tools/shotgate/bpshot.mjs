// A line copied and stamped twice, once turned, seen from the overhead. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  F.goalIdx = F.GOALS.length;
  const i = 6, j = 6;
  F.place(0, i, j, TY.SMELTER, 0); for (let k = 1; k < 5; k++) F.place(0, i + k, j, TY.BELT, 0); F.place(0, i + 5, j, TY.HUB, 0);
  F.place(0, i + 2, j - 1, TY.FILTER, 1); F.cells[0][i + 2][j - 1].filt = TY.EMBER;
  F.captureBlueprint(0, i, j - 1, i + 5, j);
  F.stampBlueprint(0, i, j + 3);
  F.bpRot = 1; F.stampBlueprint(0, i + 8, j - 1);
  await new Promise(r => setTimeout(r, 300));
});
await p.keyboard.press('Tab');
await new Promise(r=>setTimeout(r,900));
await p.screenshot({ path: (process.env.OUT || 'bp') + '_overhead.png' });
await b.close();
