// Stand on a tread of the lighthouse stair and walk: J=job_N K=tread node _lhstep.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(3000); await p.click('#startbtn').catch(() => {}); await wait(3000);
for (let i = 0; i < 120; i++) { if (await p.evaluate(() => { const f = window.__game.facts(); return !f.intro && !f.paused; })) break; await wait(500); }
await wait(1500);
const door = await p.evaluate(() => window.__doors[0].out);
await p.evaluate((d) => window.__game.tp(d[0], d[1]), door); await wait(2000);
const K = +(process.env.K || 30);
const at = await p.evaluate((K) => { const L = window.__lhClimb; const a = Math.PI / 2 + 0.5 + K * 0.27, r = (0.85 + 2.9) / 2; return [L.x + Math.cos(a) * r, (K + 1) * 0.24 + 1.0, Math.sin(a) * r]; }, K);
await p.evaluate((q) => window.__game.tp3(q[0], q[1], q[2]), at); await wait(3000);
const y0 = await p.evaluate(() => window.__game.bpos()[1]);
console.log('on tread', K, 'expect top', ((K + 1) * 0.24).toFixed(2), 'y', y0.toFixed(2));
const ys = [];
await p.keyboard.down('KeyW'); for (let k = 0; k < 24; k++) { await wait(250); ys.push(+(await p.evaluate(() => window.__game.bpos()[1])).toFixed(2)); } await p.keyboard.up('KeyW');
console.log('walking y', ys.join(' '));
console.log('facts', JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return { intro: f.intro, paused: f.paused, won: f.won, lost: f.lost, mode: f.mode }; })), 'drawn', JSON.stringify(await p.evaluate(() => window.__game.pos().map(v => +v.toFixed(2)))), 'body', JSON.stringify(await p.evaluate(() => window.__game.bpos().map(v => +v.toFixed(2)))));
await p.screenshot({ path: process.env.OUT || 'lhstep.jpg', type: 'jpeg', quality: 80 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
