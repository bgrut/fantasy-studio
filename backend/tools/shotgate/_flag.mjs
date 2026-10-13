// the flagship's opening in frames: OUT=prefix [URL=] node _flag.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1', { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms)); const O = process.env.OUT;
await wait(2500); await p.screenshot({ path: O + '_1.jpg', type: 'jpeg', quality: 85 });
await wait(4500); await p.screenshot({ path: O + '_2.jpg', type: 'jpeg', quality: 85 });
await p.keyboard.press('Enter'); await wait(1500); await p.screenshot({ path: O + '_3.jpg', type: 'jpeg', quality: 85 });
await p.keyboard.press('KeyL'); await wait(900); await p.screenshot({ path: O + '_4.jpg', type: 'jpeg', quality: 85 });
console.log(errs.length ? errs.join(' | ') : 'ok'); await b.close();
