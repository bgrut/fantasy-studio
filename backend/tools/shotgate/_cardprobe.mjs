// the works rating and the works card. OUT=prefix
import puppeteer from 'puppeteer-core';
import fs from 'fs';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8790/?fresh=1', { waitUntil: 'domcontentloaded' }); await new Promise(r => setTimeout(r, 20000));
console.log('rating', JSON.stringify(await p.evaluate(() => window.__rating())), 'panel', await p.evaluate(() => document.getElementById('wrn').textContent));
await p.evaluate(() => document.getElementById('wcard').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })));
await new Promise(r => setTimeout(r, 1500));
const card = await p.evaluate(() => ({ info: window.__worksCard, src: (document.querySelector('#wcardview img') || {}).src || '' }));
console.log('card', JSON.stringify(card.info));
if (card.src.startsWith('data:image/png')) fs.writeFileSync(process.env.OUT + 'card.png', Buffer.from(card.src.split(',')[1], 'base64'));
await p.screenshot({ path: process.env.OUT + 'view.jpg', type: 'jpeg', quality: 80 });
console.log('errors', errs.slice(0, 3).join(' | ') || 'none');
await b.close();
