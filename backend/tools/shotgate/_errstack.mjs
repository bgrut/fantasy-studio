import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERR', e.message, (e.stack || '').split('\n').slice(0, 4).join(' | ')));
p.on('console', m => { if (m.type() === 'error') console.log('CONSOLE', m.text().slice(0, 300), JSON.stringify(m.location())); });
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1', { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 5000)); await b.close();
