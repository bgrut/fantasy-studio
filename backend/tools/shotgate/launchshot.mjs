// The launcher in the flagship: a payload of mostly ember ingots goes to the
// world that wants them; the capsule is filmed on the pad, climbing, and on
// its way to the far cube; the landing's pay is reported.
//   [URL=http://127.0.0.1:8790/] OUT=<dir> node launchshot.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'creative=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
await sleep(8000); await p.keyboard.press('Enter').catch(() => {}); await sleep(3500); await p.keyboard.press('g').catch(() => {}); await sleep(600);
const setup = await p.evaluate(() => {
  const F = window.__factory, T = F.TYPES, N = F.N, f = F.player.face;
  let at = null;
  for (let i = 4; i < N - 4 && !at; i++) for (let j = 4; j < N - 4 && !at; j++) if (F.cells[f][i][j].t === T.EMPTY && !F.cells[f][i][j].mesh) at = [i, j];
  F.place(f, at[0], at[1], F.LAUNCHER, 0);
  const c = F.cells[f][at[0]][at[1]];
  c.pq = [T.INGOT_E, T.INGOT_E, T.INGOT_E, T.INGOT_E, T.INGOT_E, T.INGOT_E, T.INGOT_E, T.INGOT, T.INGOT, T.ALLOY];
  const w = F.tileWorld(f, at[0], at[1]), n = F.FACES[f].n, u = F.FACES[f].u;
  window.__padCam = { pos: [0, 1, 2].map(k => w[k] + n[k] * 2.6 + u[k] * 5.5), look: [0, 1, 2].map(k => w[k] + n[k] * 1.2), up: n };
  window.__camPin = window.__padCam;
  return { f, at, ore0: Math.round(F.ore) };
});
await sleep(800);
await p.screenshot({ path: `${OUT}/launch_1_pad.jpg`, type: 'jpeg', quality: 90 });
await p.evaluate(() => { window.__factory.step(); });
// follow the capsule from behind and below
await p.evaluate(() => {
  window.__camPin = () => {
    const g = window.__scene.getObjectByName('capsuleFlight');
    if (!g) return window.__padCam;
    const P = g.position, V = P.clone().normalize();
    return { pos: [P.x - V.x * 0 + 14, P.y - 10, P.z + 14].map((v, k) => k === 1 ? v : v), look: P.toArray(), up: [0, 1, 0] };
  };
});
await sleep(1000);
await p.screenshot({ path: `${OUT}/launch_2_climb.jpg`, type: 'jpeg', quality: 90 });
await sleep(1600);
await p.screenshot({ path: `${OUT}/launch_3_away.jpg`, type: 'jpeg', quality: 90 });
await sleep(2600);
const end = await p.evaluate((ore0) => { const F = window.__factory; return Object.assign(F.launches(), { ore: Math.round(F.ore), gained: Math.round(F.ore) - ore0 }); }, setup.ore0);
console.log('setup', JSON.stringify(setup), 'end', JSON.stringify(end));
console.log('errors', JSON.stringify(errs.slice(0, 4)));
await b.close();
