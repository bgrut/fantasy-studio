// Evaluate an expression in a started game: J=job_N EXPR='...' [WAIT=ms] node _eval.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(+(process.env.WAIT || 3000));
console.log(JSON.stringify(await p.evaluate(src => { try { return eval(src); } catch (e) { return 'EVAL ' + e.message; } }, process.env.EXPR)));
if (errs.length) console.log('ERR', errs.join(' | '));
await b.close();
