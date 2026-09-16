import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4500));
await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let sm = null;
  for (let i = 0; i < F.N && !sm; i++) for (let j = 0; j < F.N && !sm; j++) if (F.cells[0][i][j].t === TY.SMELTER) sm = [i, j];
  const w = F.tileWorld(0, sm[0], sm[1] + 3);
  F.player.pos.set(w[0] - 2.4, F.HALF + 1.6, w[2] + 3.0);
  F.player.fwd.set(w[0] - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.3;
  document.getElementById('tutor')?.classList.remove('on'); F.ageHints();
  F.addValue(500); F.place(0, sm[0], sm[1] + 3, TY.SMELTER, 0);
});
await new Promise(r => setTimeout(r, 30));
await p.screenshot({ path: 'land.png' });
console.log(JSON.stringify(await p.evaluate(() => ({ landing: window.__game.facts().landing }))));
await b.close();
