// The adventure in play: START, then a few seconds of driving, then a frame.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760','--autoplay-policy=no-user-gesture-required'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/', { waitUntil:'domcontentloaded', timeout:120000 });
await new Promise(r => setTimeout(r, 9000));
await p.screenshot({ path: 'adv_start.png' });
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await new Promise(r => setTimeout(r, 1500));
await p.keyboard.down('KeyW');
await new Promise(r => setTimeout(r, +(process.env.DRIVE || 4000)));
await p.screenshot({ path: 'adv_play.png' });
await p.keyboard.up('KeyW');
const hud = await p.evaluate(() => ({ h1: document.querySelector('#hud h1')?.textContent, obj: document.querySelector('#obj')?.textContent, quest: document.querySelector('#quest')?.textContent, texts: [...document.querySelectorAll('#hud *')].map(e => e.textContent.trim()).filter(Boolean).slice(0, 12) }));
console.log(JSON.stringify(hud)); console.log('errors:', errs.length ? errs.join(' | ') : 'none');
await b.close();
