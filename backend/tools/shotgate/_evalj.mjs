// Start a job and print the value of an expression. J=10001 JS="expr" node _evalj.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200))); p.on('console', m => { if (/warn|error/.test(m.type()) && !/404|Failed to load/.test(m.text())) errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 120000 }).catch(() => {});
await new Promise(r => setTimeout(r, 5000)); await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, +(process.env.WAIT || 6000)));
console.log(JSON.stringify(await p.evaluate(src => { try { return eval(src); } catch (e) { return 'ERR ' + e.message; } }, process.env.JS)));
console.log('errs', JSON.stringify(errs.slice(0, 6)));
await b.close();
