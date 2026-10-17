import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.goto(`http://127.0.0.1:8789/games/job_${process.env.B}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500));
await p.evaluate(() => window.__game.tp(0, 0)); await new Promise(r => setTimeout(r, 700));
await p.keyboard.down('KeyW');
for (let i = 0; i < 6; i++) { await new Promise(r => setTimeout(r, 200)); console.log(JSON.stringify(await p.evaluate(() => ({ v: window.__game.facts().walk_v, pos: window.__game.pos().map(x => +x.toFixed(2)), hero: window.__game.facts().hero })))); }
await b.close();
