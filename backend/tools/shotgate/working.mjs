// A working line, a few seconds in: the smelter cooking, the hub selling. Stand off the line's side and look along it.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 9000));
const r = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let sm = null;
  for (let i = 0; i < F.N && !sm; i++) for (let j = 0; j < F.N && !sm; j++) if (F.cells[0][i][j].t === TY.SMELTER) sm = [i, j];
  const w = F.tileWorld(0, sm[0], sm[1]);
  F.player.pos.set(w[0] - 1.0, F.HALF + 1.6, w[2] + 3.4);
  F.player.fwd.set(w[0] + 1.5 - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.22;
  document.getElementById('tutor')?.classList.remove('on');
  return { cook: F.cells[0][sm[0]][sm[1]].cook };
});
await new Promise(r => setTimeout(r, 1200));
const f = await p.evaluate(() => window.__game.facts().lights);
await p.screenshot({ path: process.env.OUT || 'working.png' });
console.log('cook', r.cook, '| lights', JSON.stringify(f), '| errors', errs.length ? errs.join(' | ') : 'none');
await b.close();
