// A frame of the reveal, mostly sky: URL, Q (extra query), OUT
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1' + (process.env.Q || ''), { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, +(process.env.AT || 2000)));
await p.screenshot({ path: process.env.OUT || 'sky.png' });
console.log('errors:', errs.length ? errs.join(' | ') : 'none');
await b.close();
