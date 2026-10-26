// Crystal Works as a player first sees it, and a little later: OUT=prefix node _flagview.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 120 && !(await p.evaluate(() => !!(window.__factory && window.__game)).catch(() => false)); i++) await wait(500);
await wait(3000); await p.screenshot({ path: `${process.env.OUT}_reveal.jpg`, type: 'jpeg', quality: 85 });
await p.keyboard.press('Space'); await wait(5000);
await p.screenshot({ path: `${process.env.OUT}_play.jpg`, type: 'jpeg', quality: 85 });
await p.keyboard.down('KeyW'); await wait(+(process.env.WALK || 2500)); await p.keyboard.up('KeyW'); await wait(1500);
console.log(JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return { face: f.face, sun: f.sun, light: f.light }; })));
await p.screenshot({ path: `${process.env.OUT}_walk.jpg`, type: 'jpeg', quality: 85 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
