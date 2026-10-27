// Collect the sonde's parts and launch the balloon: J=job_N OUT=prefix node _polarrun.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(3000); await p.click('#startbtn').catch(() => {}); await wait(3000);
const pts = await p.evaluate(() => window.__spec.world.level.collect_points);
for (const q of pts) { await p.evaluate((q) => window.__game.tp3(q[0], window.__game.bpos()[1] + 0.5, q[1]), q); await wait(1500); }
const L = await p.evaluate(() => { const L = window.__balloonLaunch; return [L.x, L.y, L.z]; });
await p.evaluate((L) => { window.__game.tp3(L[0] + 1.2, L[1] + 1.0, L[2] + 1.2); window.__game.look(Math.atan2(1.2, 1.2)); }, L); await wait(1200);
console.log('step', await p.evaluate(() => document.querySelector('#hud') ? document.querySelector('#hud').innerText.slice(0, 120) : ''));
await p.keyboard.down('KeyE'); await wait(1600); await p.screenshot({ path: `${process.env.OUT}_fill.jpg`, type: 'jpeg', quality: 85 }); await wait(1800); await p.keyboard.up('KeyE');
await wait(2500); await p.evaluate(() => window.__game.look(Math.atan2(1.2, 1.2))); await p.screenshot({ path: `${process.env.OUT}_rise.jpg`, type: 'jpeg', quality: 85 });
await wait(5000); await p.screenshot({ path: `${process.env.OUT}_end.jpg`, type: 'jpeg', quality: 85 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
