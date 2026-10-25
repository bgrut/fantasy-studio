// Stand at a spot and hold E, then read the HUD objective line: J=job_N AT=x,z HOLD=ms node _holdprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(4000); await p.click('#startbtn').catch(() => {}); await wait(3500);
for (let i = 0; i < 30; i++) { if (await p.evaluate(() => { const f = window.__game.facts(); return !f.intro && !f.paused; })) break; await wait(500); }
const [x, z] = process.env.AT.split(',').map(Number);
const hud = () => p.evaluate(() => ((document.body.innerText.match(/\b\w+ \d+ [a-z ]+ · \d+\/\d+/) || [''])[0]) + ' | at ' + window.__game.pos().map(v => +v.toFixed(1)).join(','));
await p.evaluate((x, z) => window.__game.tp(x, z), x, z); await wait(1200);
console.log('before', await hud());
await p.keyboard.down('KeyE'); await wait(+(process.env.HOLD || 3500)); await p.keyboard.up('KeyE'); await wait(800);
console.log('after ', await hud(), errs.length ? 'ERR ' + errs[0] : '');
await b.close();
