// A sale landing: stand by the hub after the line has run, catch a tag mid-rise.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 7000));
await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let hub = null;
  for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const w = F.tileWorld(0, hub[0], hub[1]);
  F.player.pos.set(w[0] - 2.6, F.HALF + 1.6, w[2] - 3.2);
  F.player.fwd.set(w[0] - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = -0.25;
  document.getElementById('tutor')?.classList.remove('on');
});
let best = null;
for (let k = 0; k < 40; k++) {
  await new Promise(r => setTimeout(r, 150));
  const n = await p.evaluate(() => document.querySelectorAll('#tags .tag').length);
  if (n > 0) { await new Promise(r => setTimeout(r, 120)); best = await p.evaluate(() => [...document.querySelectorAll('#tags .tag')].map(e => { const r = e.getBoundingClientRect(); return e.textContent + '@' + e.style.opacity + ' at ' + (r.x | 0) + ',' + (r.y | 0) + ' tf ' + e.style.transform; })); break; }
}
await p.screenshot({ path: 'tag.png' });
const f = await p.evaluate(() => { const f = window.__game.facts(); return { tagsSeen: f.tagsSeen, live: f.tagsLive, value: f.value }; });
console.log('tags:', JSON.stringify(best), '| facts', JSON.stringify(f), '| errors', errs.length ? errs.join(' | ') : 'none');
await b.close();
