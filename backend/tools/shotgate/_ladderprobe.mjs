// The tower ladder rescue end to end: stand in the basket, hold E, ride up, the cat comes
// over the sill, ride down, the reach step completes. Shots on the way up and at the top.
//   J=job_N OUT=prefix node _ladderprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await p.click('#startbtn').catch(() => {}); await wait(3000);
const R = await p.evaluate(() => window.__fireRescue);
if (!R) { console.log('no tower ladder'); await b.close(); process.exit(1); }
await p.evaluate(a => window.__game.tp(a[0], a[1]), R.rest); await wait(1200);
const st = () => p.evaluate(() => ({ L: window.__ladderState, pos: window.__game.pos().map(x => +x.toFixed(2)), won: window.__game.facts().won, step: window.__game.facts().step }));
console.log('in basket', JSON.stringify(await st()));
await p.keyboard.down('KeyE');
for (let i = 0; i < 9; i++) { await wait(1000); const s = await st(); console.log('t', i + 1, JSON.stringify(s));
  if (i === 3 || (s.L && s.L.phase === 'cat')) await p.screenshot({ path: `${process.env.OUT}_${i}.jpg`, type: 'jpeg', quality: 85 }); }
await p.keyboard.up('KeyE');
for (let i = 0; i < 9; i++) { await wait(1000); const s = await st(); console.log('d', i + 1, JSON.stringify(s)); if (s.L && s.L.phase === 'done') break; }
await wait(1500); await p.screenshot({ path: `${process.env.OUT}_end.jpg`, type: 'jpeg', quality: 85 });
console.log(JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return Object.fromEntries(Object.entries(f).filter(([k, v]) => typeof v !== 'object' || v === null)); })));
console.log(JSON.stringify(await st()), errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
