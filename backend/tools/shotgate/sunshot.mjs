import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 6000));
await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let sm = null;
  for (let i = 0; i < F.N && !sm; i++) for (let j = 0; j < F.N && !sm; j++) if (F.cells[0][i][j].t === TY.SMELTER) sm = [i, j];
  const w = F.tileWorld(0, sm[0], sm[1]);
  F.player.pos.set(w[0] - 4.5, F.HALF + 2.2, w[2] + 4.5);
  F.player.fwd.set(w[0] + 2 - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.32;
  document.getElementById('tutor')?.classList.remove('on'); F.ageHints();
});
for (const [k, t] of [['a', 0], ['b', 105], ['c', 315]]) {
  await p.evaluate((t) => window.__factory.sunAt(t), t);
  await new Promise(r => setTimeout(r, 900));
  await p.screenshot({ path: 'sun_' + k + '.png' });
}
console.log('three phases shot');
await b.close();
