import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.PF}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(1000); }
await (await p.$('#startbtn'))?.click(); await wait(1500);
const sp = await p.evaluate(() => window.__platformSpans);
console.log('spans', JSON.stringify(sp.map(s => s.map(v => +(+v).toFixed(2)))));
const s = sp[2], mx = (s[0] + s[1]) / 2;
await p.evaluate((x, y) => window.__game.tpy(x, y, 0), mx, s[2] + 3);
for (let t = 0; t < 10; t++) { await wait(300); console.log(t, JSON.stringify(await p.evaluate(() => window.__game.pos().map(v => +v.toFixed(2))))); }
await b.close();
