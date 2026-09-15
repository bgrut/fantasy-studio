import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4000));
const r0 = await p.evaluate(() => ({ props: window.__game.facts().props }));
await p.screenshot({ path: 'outpost_spawn.png' });
const r = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let hub = null;
  for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const w = F.tileWorld(0, hub[0], hub[1] + 2);
  F.player.pos.set(w[0] - 3.2, F.HALF + 1.6, w[2] - 3.6);
  F.player.fwd.set(w[0] - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.18;
  document.getElementById('tutor')?.classList.remove('on');
  // erase and build on the habitat must both refuse
  const c = F.cells[0][hub[0]][hub[1] + 2];
  const before = c.t; F.removeAt(0, hub[0], hub[1] + 2); const afterErase = c.t;
  const placed = F.place(0, hub[0], hub[1] + 2, TY.SMELTER, 0);
  return { hub, habitatType: before, afterErase, placedOnIt: placed, prop: c.prop };
});
await new Promise(r => setTimeout(r, 900));
await p.screenshot({ path: 'outpost_close.png' });
const look = await p.evaluate(() => document.getElementById('look')?.textContent);
console.log(JSON.stringify({ ...r0, ...r, look }), '| errors:', errs.length ? errs.join(' | ') : 'none');
await b.close();
