// The adventure fixtures: the drift race (A) and the haunted manor (B), shot
// from the same views on every check and held to their facts, so the
// adventure side keeps its standard as the factory side climbs. The pictures
// are written beside the gates and tracked, so a change shows in the diff.
//   A=<drift job id>   B=<manor job id>   (skips without both)
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
const A = process.env.A, B = process.env.B;
if (!A || !B) { console.log('skipped   : needs --adv (the drift race) and --bld (the manor)'); process.exit(0); }
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const OUT = path.join(HERE, 'fixtures');
const shot = (name) => p.screenshot({ path: path.join(OUT, name + '.jpg'), type: 'jpeg', quality: 82 });
const start = async (job) => {
  await p.goto('http://127.0.0.1:8789/games/job_' + job + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
  await wait(9000);
  const btn = await p.$('#startbtn'); if (btn) await btn.click();
  await wait(4000);
  return p.evaluate(async () => { const r = await fetch('spec.json'); return r.ok ? r.json() : {}; });
};
const rows = [];

// 1. the drift race: the street at spawn, then three seconds of driving
const specA = await start(A);
await shot('drift_spawn');
await p.keyboard.down('KeyW'); await wait(3000); await p.keyboard.up('KeyW'); await wait(500);
await shot('drift_street');
const drift = await p.evaluate(() => ({ city: !!window.__isCity, mode: (window.__game.facts && window.__game.facts().mode) || null, pos: window.__game.pos().map(v => +v.toFixed(1)) }));
const driftOk = drift.city && drift.mode === 'drive' && specA.world && specA.world.sky === 'night' && (specA.objectives || []).some(o => o.kind === 'race');
rows.push({ name: 'the drift race', prompt: specA.prompt, facts: 'city ' + drift.city + ', mode ' + drift.mode + ', sky ' + (specA.world && specA.world.sky) + ', race objective ' + (specA.objectives || []).some(o => o.kind === 'race'), pics: ['drift_spawn', 'drift_street'], ok: driftOk });
console.log('the drift : city', drift.city, '| mode', drift.mode, '| sky', specA.world && specA.world.sky, '| ok', driftOk);

// 2. the manor: the spawn faces the door; then the door up close
const specB = await start(B);
await shot('manor_spawn');
const manor = await p.evaluate(async () => {
  const L = window.__game.landmark(); if (!L) return { landmark: null };
  const dx = L.door[0], dz = L.door[1], nx = (0 - dx), nz = (0 - dz), nl = Math.hypot(nx, nz) || 1;
  window.__game.tp(dx + nx / nl * 9, dz + nz / nl * 9);
  window.__game.look(Math.atan2(dx - (dx + nx / nl * 9), dz - (dz + nz / nl * 9)) + Math.PI);
  await new Promise(r => setTimeout(r, 900));
  const n = window.__game.npcs();
  return { landmark: { kit: L.kit, w: L.w, d: L.d, h: L.h, lamps: L.lamps }, ghosts: n.filter(x => x.spectral).length, npcs: n.length };
});
await shot('manor_door');
const manorOk = !!manor.landmark && manor.landmark.w > 5 && manor.ghosts >= 1 && manor.ghosts <= 3 && specB.style === 'horror' && specB.world && specB.world.sky === 'night';
rows.push({ name: 'the haunted manor', prompt: specB.prompt, facts: 'landmark ' + (manor.landmark ? manor.landmark.kit : 'NONE') + ', ghosts ' + manor.ghosts + ', style ' + specB.style + ', sky ' + (specB.world && specB.world.sky), pics: ['manor_spawn', 'manor_door'], ok: manorOk });
console.log('the manor : landmark', manor.landmark ? manor.landmark.kit : 'NONE', '| ghosts', manor.ghosts, '| style', specB.style, '| sky', specB.world && specB.world.sky, '| ok', manorOk);

// the record beside the pictures
const md = ['# The adventure fixtures', '',
  'Shot by `ffixtures.mjs` on every check from the same views, held to the facts below. A change to the adventure side shows here as a picture, not only as a number.', '',
  'Last shot: ' + new Date().toISOString().slice(0, 10), '',
  '| fixture | the sentence | facts | pictures |', '|---|---|---|---|',
  ...rows.map(r => '| ' + r.name + ' | ' + r.prompt + ' | ' + r.facts + ' | ' + r.pics.map(n => '![' + n + '](' + n + '.jpg)').join(' ') + ' |'), ''];
fs.writeFileSync(path.join(OUT, 'README.md'), md.join('\n'), 'utf-8');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = rows.every(r => r.ok) && errs.length === 0;
if (!ok) console.log('FAIL: the adventure fixtures');
process.exit(ok ? 0 : 1);
