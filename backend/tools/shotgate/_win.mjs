// the end card of a job: J=job_N OUT=file node _win.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width:1600, height:900 }); const errs=[]; p.on('pageerror', e=>errs.push(e.message.slice(0,200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/?noguide=1`, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,10000)); await p.click('#startbtn').catch(()=>{}); await new Promise(r=>setTimeout(r,3000));
await p.evaluate(() => window.__game.win && window.__game.win()); await new Promise(r=>setTimeout(r,2500));
await p.screenshot({ path: process.env.OUT, type:'jpeg', quality:85 }); console.log(errs.join(' | ') || 'ok'); await b.close();
