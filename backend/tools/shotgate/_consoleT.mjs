import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); const L = []; p.on('console', m => { const t = m.text(); if (new RegExp(process.env.PAT || '.').test(t)) L.push(m.type() + ' ' + t.slice(0, 300)); });
p.on('pageerror', e => L.push('PAGEERR ' + e.message.slice(0, 300)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await new Promise(r => setTimeout(r, 500)); }
await new Promise(r => setTimeout(r, 3000)); console.log(L.slice(0, 20).join('\n')); await b.close();
