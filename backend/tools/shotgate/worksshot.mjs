import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4000));
await p.evaluate(async () => { const F = window.__factory; F.goalIdx = F.GOALS.length; F.addCores(3); F.lifetime.longestHold = 320; F.lifetime.contracts = 4; F.lifetime.value = 12840;
  await new Promise(r => setTimeout(r, 400)); F.visitedWorlds.add(1); F.visitedWorlds.add(2); await new Promise(r => setTimeout(r, 600)); F.endIntro(); });
await new Promise(r => setTimeout(r, 300));
await p.evaluate(() => { const e = document.getElementById('fs-end'); if (e) e.classList.remove('on');   // the card aside: the world itself
  const F = window.__factory, TY = F.TYPES; let hub = null;
  for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const w = F.tileWorld(0, hub[0], hub[1]);
  F.player.pos.set(w[0] - 5.5, F.HALF + 1.8, w[2] + 5.5);
  F.player.fwd.set(w[0] - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = 0.05;
  document.getElementById('tutor')?.classList.remove('on'); F.ageHints(); });
await new Promise(r => setTimeout(r, 1100));
await p.screenshot({ path: 'works_show.png' });
console.log(JSON.stringify(await p.evaluate(() => ({ show: window.__game.facts().worksShow }))));
await b.close();
