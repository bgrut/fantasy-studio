// The first thing a player sees: the demo loaded with no parameters, shot at three moments before any click.
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
await wait(2500); await p.screenshot({ path: 'renders/title_1.png' });
await wait(5000); await p.screenshot({ path: 'renders/title_2.png' });
const btn = await p.$('#startbtn'); console.log('start button:', !!btn);
if (btn) { await btn.click(); await wait(4000); await p.screenshot({ path: 'renders/title_3_after_start.png' }); await wait(8000); await p.screenshot({ path: 'renders/title_4_reveal.png' }); }
await b.close();
