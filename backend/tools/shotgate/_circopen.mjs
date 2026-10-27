// Walk the ringmaster onto the star and watch the show open: J=job_N OUT=prefix node _circopen.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(3000); await p.click('#startbtn').catch(() => {}); await wait(4000);
const B = await p.evaluate(() => ({ x: window.__bigtop.x, z: window.__bigtop.z, y: window.__bigtop.y }));
// in through the entrance, through the curb's gap, onto the star
const a = Math.atan2(-B.z, -B.x);
await p.evaluate((q) => { window.__game.tp3(q.x + Math.cos(q.a) * 8, q.y + 1.0, q.z + Math.sin(q.a) * 8); window.__game.look(Math.atan2(Math.cos(q.a), Math.sin(q.a))); }, { ...B, a }); await wait(1200);
await p.evaluate((q) => { window.__game.tp3(q.x + Math.cos(q.a) * 0.6, q.y + 1.0, q.z + Math.sin(q.a) * 0.6); }, { ...B, a }); await wait(800);
console.log('at', JSON.stringify(await p.evaluate(() => window.__game.bpos().map(v => +v.toFixed(2)))), 'holding', await p.evaluate(() => window.__bigtop.holding()));
await wait(1500); await p.screenshot({ path: `${process.env.OUT}_1.jpg`, type: 'jpeg', quality: 85 });
await wait(2500); await p.screenshot({ path: `${process.env.OUT}_2.jpg`, type: 'jpeg', quality: 85 });
await wait(3000); console.log('facts', JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return f; })));
await p.screenshot({ path: `${process.env.OUT}_3.jpg`, type: 'jpeg', quality: 85 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
