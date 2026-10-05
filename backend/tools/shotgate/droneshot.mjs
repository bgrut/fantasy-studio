// Cargo drones in the flagship: a miner and a belt feed a sender pad; a
// receiver pad across the face puts the cargo into a hub. Steps the sim,
// reports what flew and what sold, and shoots the craft in flight.
//   [URL=http://127.0.0.1:8790/] OUT=<dir> node droneshot.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'creative=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 8000));
await p.keyboard.press('Enter').catch(() => {}); await new Promise(r => setTimeout(r, 3500)); await p.keyboard.press('g').catch(() => {});
const setup = await p.evaluate(() => {
  const F = window.__factory, T = F.TYPES, N = F.N;
  // a seam on the home face with room for a rig, a belt and a pad beside it
  let seam = null;
  for (let i = 2; i < N - 4 && !seam; i++) for (let j = 2; j < N - 2 && !seam; j++) {
    const c = F.cells[0][i][j];
    if (c.t === T.NODE && F.cells[0][i + 1][j].t === T.EMPTY && F.cells[0][i + 2][j].t === T.EMPTY) seam = [i, j];
  }
  if (!seam) return { err: 'no seam with room' };
  const [i, j] = seam;
  F.place(0, i, j, T.MINER, 0);
  F.place(0, i + 1, j, T.BELT, 0);
  F.place(0, i + 2, j, F.DRONEPAD, 0);
  // the receiver: the far side of the face, its output into a hub
  let rc = null;
  for (let a = N - 3; a > 2 && !rc; a--) for (let bb = N - 3; bb > 2 && !rc; bb--) {
    if (Math.hypot(a - i, bb - j) < N * 0.5) continue;
    if (F.cells[0][a][bb].t === T.EMPTY && F.cells[0][a + 1] && F.cells[0][a + 1][bb].t === T.EMPTY) rc = [a, bb];
  }
  if (!rc) return { err: 'no room for the receiver' };
  F.place(0, rc[0], rc[1], F.DRONEPAD, 0);
  F.place(0, rc[0] + 1, rc[1], T.HUB, 0);
  return { seam, rc, padsAt: [[i + 2, j], rc] };
});
console.log('setup', JSON.stringify(setup));
// let it run in real time: the sim ticks and the craft flies
await new Promise(r => setTimeout(r, 9000));
const mid = await p.evaluate(() => window.__factory.drones());
console.log('after 9 s', JSON.stringify(mid));
// overhead to see the whole face, then a close look at a craft in the air
await p.keyboard.press('Tab'); await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/drone_overhead.jpg`, type: 'jpeg', quality: 88 });
await p.keyboard.press('Tab'); await new Promise(r => setTimeout(r, 800));
// wait for a craft in the air, then pin a camera beside it, looking at it
let fly = null;
for (let k = 0; k < 60 && !fly; k++) {
  fly = await p.evaluate(() => {
    const a = window.__factory.drones().air.find(x => x.loaded > 0) || null;
    if (!a) return null;
    const V = window.__scene.position.constructor;
    // follow it: the pin is re-read every frame
    window.__camPin = () => {
      const f = window.__factory.drones().air.find(x => x.loaded > 0) || window.__factory.drones().air[0];
      if (!f) return window.__lastPin;
      const pos = new V(...f.pos), up = pos.clone().normalize();
      const side = new V(1, 0, 0).cross(up).normalize();
      window.__lastPin = { pos: pos.clone().addScaledVector(side, 2.4).addScaledVector(up, 0.8).toArray(), look: pos.toArray(), up: up.toArray() };
      return window.__lastPin;
    };
    return a.pos.map(v => +v.toFixed(1));
  });
  if (!fly) await new Promise(r => setTimeout(r, 150));
}
await new Promise(r => setTimeout(r, 60));
await p.screenshot({ path: `${OUT}/drone_close.jpg`, type: 'jpeg', quality: 88 });
for (let k = 0; k < 40; k++) await p.evaluate(() => window.__factory.step());
const end = await p.evaluate(() => window.__factory.drones());
console.log('after 40 more ticks', JSON.stringify(end), 'craft', JSON.stringify(fly));
console.log('errors', JSON.stringify(errs.slice(0, 5)));
await b.close();
