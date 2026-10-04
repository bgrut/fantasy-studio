// The flagship demo as a player first sees it, and two closer views.
//   OUT=<dir> node flagshot.mjs
import puppeteer from 'puppeteer-core';
const OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8790/', { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 8000));
await p.keyboard.press('Enter').catch(() => {});
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 5000));
await p.screenshot({ path: `${OUT}/flag_start.jpg`, type: 'jpeg', quality: 88 });
await p.keyboard.press('g').catch(() => {});
await new Promise(r => setTimeout(r, 2500));
await p.screenshot({ path: `${OUT}/flag_play.jpg`, type: 'jpeg', quality: 88 });
console.log(JSON.stringify(errs.slice(0, 5)));
await b.close();
