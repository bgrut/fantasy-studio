import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 300))); p.on('console', m => { if (m.type() === 'error') errs.push('c: ' + m.text().slice(0, 200)); });
const t0 = Date.now(); await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
let ok = false; for (let i = 0; i < 180; i++) { ok = await p.evaluate(() => !!(window.__game && window.__game.facts)); if (ok) break; await new Promise(r => setTimeout(r, 500)); }
console.log('ready', ok, (Date.now() - t0) / 1000, 's'); console.log(errs.slice(0, 6).join('\n')); await b.close();
