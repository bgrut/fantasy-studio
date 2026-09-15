// The drone mid-flight: set its clock to the middle of the outbound leg, stand by the hub, look up at it.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4000));
const r = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES; let hub = null;
  for (let i = 0; i < F.N && !hub; i++) for (let j = 0; j < F.N && !hub; j++) if (F.cells[0][i][j].t === TY.HUB) hub = [i, j];
  const w = F.tileWorld(0, hub[0], hub[1]);
  F.player.pos.set(w[0] - 4.5, F.HALF + 1.6, w[2] - 4.5);
  F.player.fwd.set(w[0] + 2 - F.player.pos.x, 0, w[2] - F.player.pos.z).normalize(); F.player.pitch = 0.12;
  document.getElementById('tutor')?.classList.remove('on');
  const at = window.__game.facts().drone;
  F.droneAt(29);                       // three seconds into the outbound leg
  await new Promise(r => setTimeout(r, 700));
  return { atRest: at, mid: window.__game.facts().drone };
});
await p.screenshot({ path: 'drone.png' });
console.log(JSON.stringify(r), '| errors', errs.length ? errs.join(' | ') : 'none');
await b.close();
