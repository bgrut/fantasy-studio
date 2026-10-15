// Where a tower-defence wave stalls: call a wave, trace each attacker. TD=<job>
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.TD}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 120000 });
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(1000); }
await (await p.$('#startbtn'))?.click(); await wait(1500);
console.log(JSON.stringify(await p.evaluate(() => { const q = window.__game.facts().defend; return { keep: q.keep_at, gate: q.gate_at, road_in: q.road_in }; })));
await p.evaluate(() => { const q = window.__game.facts().defend, [kx, kz] = q.keep_at, [rx, rz] = q.road_in;
  const L = Math.hypot(rx - kx, rz - kz) || 1, ux = (rx - kx) / L, uz = (rz - kz) / L; window.__game.tp(kx + uz * 28, kz - ux * 28); });
await wait(800); await p.evaluate(() => window.__defend.call());
for (let t = 0; t < 40; t += 3) { await wait(3000);
  console.log(t, JSON.stringify(await p.evaluate(() => window.__game.npcs().filter(n => n.behavior === 'hostile' && !n.dead && !n.dormant).map(n => [+n.pos[0].toFixed(1), +n.pos[2].toFixed(1), n.mode || n.state || '']))), JSON.stringify(await p.evaluate(() => { const q = window.__game.facts().defend; return [q.breaches, q.keep]; }))); }
await b.close();
