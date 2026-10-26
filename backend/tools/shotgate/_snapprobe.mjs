// Step onto the first pickup and catch what happens: J=job_N OUT=prefix node _snapprobe.mjs
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
const q = await p.evaluate(() => window.__game.objectives().left[0]);
await p.evaluate((q) => window.__game.tp3(q[0] + 2.5, q[1], q[2] + 2.5), q); await wait(1500);
await p.screenshot({ path: `${process.env.OUT}_near.jpg`, type: 'jpeg', quality: 80 });
await p.evaluate((q) => window.__game.tp3(q[0], q[1], q[2]), q); await wait(150);
await p.screenshot({ path: `${process.env.OUT}_snap.jpg`, type: 'jpeg', quality: 80 });
await wait(700);
console.log(JSON.stringify(await p.evaluate(() => window.__game.objectives())).slice(0, 200), errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
