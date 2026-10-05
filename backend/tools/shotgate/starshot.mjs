// Starfall in the flagship: drops a star on an empty tile of the player's
// face, films the closing ring, the fall, the strike and the crater, then
// puts a rig on the fallen star with a belt to a hub and steps the sim until
// it is spent, reporting the loads and the shard it paid.
//   [URL=http://127.0.0.1:8790/] OUT=<dir> node starshot.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'creative=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 8000));
await p.keyboard.press('Enter').catch(() => {}); await new Promise(r => setTimeout(r, 3500)); await p.keyboard.press('g').catch(() => {});
const sleep = ms => new Promise(r => setTimeout(r, ms));
const setup = await p.evaluate(() => {
  const F = window.__factory, T = F.TYPES, N = F.N, f = F.player.face;
  // an empty 3x5 patch: the crater, a rig's belt and a hub beyond
  let at = null;
  for (let i = 3; i < N - 6 && !at; i++) for (let j = 3; j < N - 3 && !at; j++) {
    let ok = true;
    for (let a = -1; a <= 4 && ok; a++) for (let bb = -1; bb <= 1 && ok; bb++) if (F.cells[f][i + a][j + bb].t !== T.EMPTY || F.cells[f][i + a][j + bb].mesh) ok = false;
    if (ok) at = [i, j];
  }
  if (!at) return { err: 'no room' };
  window.__starStart = F.starfall().fell;
  const r = F.dropStar(f, at[0], at[1]);
  // a camera off to the side of the crater, looking at it and up the sky
  const w = F.tileWorld(f, at[0], at[1]), n = F.FACES[f].n, u = F.FACES[f].u, v = F.FACES[f].v;
  window.__starCam = (back, h, lookUp) => ({ pos: [w[0] + n[0] * h - v[0] * back + u[0] * back * 0.4, w[1] + n[1] * h - v[1] * back + u[1] * back * 0.4, w[2] + n[2] * h - v[2] * back + u[2] * back * 0.4],
    look: [w[0] + n[0] * lookUp, w[1] + n[1] * lookUp, w[2] + n[2] * lookUp], up: n });
  // while it is in the sky: well back on the far side, looking between the
  // crater and the star so both are in the frame
  window.__camPin = () => {
    const fl = F.starfall().falling;
    if (!fl) return window.__starCam(13, 6, 4);
    const sp = fl.pos, back = 30;
    const pos = [w[0] + n[0] * 7 - u[0] * back * (fl.from[0] - w[0]) / 70 - v[0] * back, 0, 0];
    const at = [0, 1, 2].map(k => w[k] + n[k] * 7 - v[k] * back - (sp[k] - w[k]) * 0.25);
    const look = [0, 1, 2].map(k => w[k] * 0.55 + sp[k] * 0.45);
    return { pos: at, look, up: n };
  };
  return { f, at, r };
});
console.log('setup', JSON.stringify(setup));
if (setup.err) { await b.close(); process.exit(1); }
await sleep(4300);
await p.screenshot({ path: `${OUT}/star_1_ring.jpg`, type: 'jpeg', quality: 88 });
// wait into the fall
for (let k = 0; k < 80; k++) { const s = await p.evaluate(() => window.__factory.starfall().falling); if (s && s.phase === 'fall' && s.t > 1.1) break; await sleep(40); }
await p.screenshot({ path: `${OUT}/star_2_fall.jpg`, type: 'jpeg', quality: 88 });
for (let k = 0; k < 60; k++) { const s = await p.evaluate(() => window.__factory.starfall().falling); if (!s) break; await sleep(20); }
await sleep(90);
await p.screenshot({ path: `${OUT}/star_3_strike.jpg`, type: 'jpeg', quality: 88 });
await sleep(3500);
await p.evaluate(() => { window.__camPin = window.__starCam(6.5, 3.2, 0.6); });
await sleep(500);
await p.screenshot({ path: `${OUT}/star_4_crater.jpg`, type: 'jpeg', quality: 88 });
const down = await p.evaluate(() => window.__factory.starfall());
console.log('down', JSON.stringify(down));
// a rig on it, a belt, a hub; then mine it out
const mined = await p.evaluate((setup) => {
  const F = window.__factory, T = F.TYPES, [i, j] = setup.at, f = setup.f;
  const s0 = F.shards;
  F.place(f, i, j, T.MINER, 0); F.place(f, i + 1, j, T.BELT, 0); F.place(f, i + 2, j, T.BELT, 0); F.place(f, i + 3, j, T.HUB, 0);
  const left = [];
  for (let k = 0; k < 160; k++) { F.step(); if (k % 25 === 0) left.push((F.starfall().stars[0] || { left: 0 }).left); }
  return { left, shardsBefore: s0, shardsAfter: F.shards, spent: F.starfall().spent, cell: F.cells[f][i][j].t, star: F.cells[f][i][j].star };
}, setup);
console.log('mined', JSON.stringify(mined));
await sleep(800);
await p.evaluate(() => { window.__camPin = window.__starCam(7, 4, 0.6); });
await sleep(500);
await p.screenshot({ path: `${OUT}/star_5_rig.jpg`, type: 'jpeg', quality: 88 });
// a save and a load bring the spent star back as a seam with its rig on it
const reload = await p.evaluate(() => { const F = window.__factory; const st = F.saveState(); return { ss: st.ss, rigs: st.m.filter(r => r[3] === F.TYPES.MINER).length }; });
console.log('save', JSON.stringify(reload));
console.log('errors', JSON.stringify(errs.slice(0, 5)));
await b.close();
