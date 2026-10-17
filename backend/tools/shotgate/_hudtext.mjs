import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); const start = await p.evaluate(() => document.body.innerText.match(/Collect[^\n]*/g));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000));
console.log(JSON.stringify({ start, play: await p.evaluate(() => document.body.innerText.match(/(Collect|Fix)[^\n]*/g)), errs }));
await b.close();
