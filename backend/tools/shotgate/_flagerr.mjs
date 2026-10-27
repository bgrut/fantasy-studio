// Boot Crystal Works and print the page's errors: node _flagerr.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0, 300))); p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text().slice(0, 300)); });
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 15000));
console.log(await p.evaluate(() => !!window.__factory), errs.join('\n'));
await b.close();
