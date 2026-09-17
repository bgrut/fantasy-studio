import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 7000));
await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let rig = null;
  for (let i = 0; i < F.N && !rig; i++) for (let j = 0; j < F.N && !rig; j++) if (F.cells[0][i][j].t === TY.MINER) rig = [i, j];
  const w = F.tileWorld(0, rig[0] + 1, rig[1]);           // the first belt after the rig
  F.player.pos.set(w[0] - 0.4, F.HALF + 1.25, w[2] + 1.6);
  F.player.fwd.set(w[0] + 0.6 - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.55;
  document.getElementById('tutor')?.classList.remove('on'); F.ageHints();
});
await new Promise(r => setTimeout(r, 700));
await p.screenshot({ path: 'belt_items.png' });
await b.close();
