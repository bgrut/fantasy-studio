import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000));
console.log(JSON.stringify(await p.evaluate(() => ({ hero: window.__game.pos().map(v => +v.toFixed(1)), cam: window.__camera.position.toArray().map(v => +v.toFixed(1)), goal: window.__spec.world.level.goal, village: window.__village, gc: null }))));
await b.close();
