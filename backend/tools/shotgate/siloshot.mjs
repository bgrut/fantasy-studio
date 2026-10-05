// The silo in the flagship: a rig and a belt fill a silo that is HOLDING,
// nothing reaches the hub beyond it; F releases it and the stock drains into
// the hub two a tick. Reports the counts and shoots the silo full and draining.
//   [URL=http://127.0.0.1:8790/] OUT=<dir> node siloshot.mjs
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
  const F = window.__factory, T = F.TYPES, N = F.N;
  let at = null;
  for (let f = 0; f < 6 && !at; f++) for (let i = 2; i < N - 5 && !at; i++) for (let j = 2; j < N - 2 && !at; j++) {
    if (F.cells[f][i][j].t !== T.NODE) continue;
    let ok = true;
    for (let a = 1; a <= 3; a++) if (F.cells[f][i + a][j].t !== T.EMPTY) ok = false;
    if (ok) at = [f, i, j];
  }
  if (!at) return { err: 'no seam with room' };
  const [f, i, j] = at;
  F.place(f, i, j, T.MINER, 0); F.place(f, i + 1, j, T.BELT, 0); F.place(f, i + 2, j, F.SILO, 0); F.place(f, i + 3, j, T.HUB, 0);
  F.toggleSilo(f, i + 2, j);                 // hold it
  const w = F.tileWorld(f, i + 2, j), n = F.FACES[f].n, u = F.FACES[f].u, v = F.FACES[f].v;
  window.__camPin = { pos: [0, 1, 2].map(k => w[k] + n[k] * 3.2 - v[k] * 6.5 - u[k] * 2.5), look: [0, 1, 2].map(k => w[k] + n[k] * 1.0), up: n };
  return { at, silo: [f, i + 2, j] };
});
console.log('setup', JSON.stringify(setup));
if (setup.err) { await b.close(); process.exit(1); }
const run = (k) => p.evaluate((k) => { const F = window.__factory; for (let q = 0; q < k; q++) F.step(); return { silo: F.silos()[0], ore: Math.round(F.ore ?? 0) }; }, k);
const held = await run(70);
console.log('held 70 ticks', JSON.stringify(held));
await sleep(600);
await p.screenshot({ path: `${OUT}/silo_1_full.jpg`, type: 'jpeg', quality: 88 });
const [f, i, j] = setup.silo;
await p.evaluate((f, i, j) => window.__factory.toggleSilo(f, i, j), f, i, j);
const r1 = await run(10);
console.log('released 10 ticks', JSON.stringify(r1));
await sleep(600);
await p.screenshot({ path: `${OUT}/silo_2_draining.jpg`, type: 'jpeg', quality: 88 });
const r2 = await run(40);
console.log('released 50 ticks', JSON.stringify(r2));
const look = await p.evaluate(() => { const s = window.__factory.saveState(); return s.m.filter(r => r[3] === window.__factory.SILO); });
console.log('saved', JSON.stringify(look));
console.log('errors', JSON.stringify(errs.slice(0, 5)));
await b.close();
