// screenshot with named objects hidden: J=job_N HIDE=a,b OUT=x.jpg
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 4000));
console.log(await p.evaluate(h => { const out = []; for (const n of h.split(',')) { const o = window.__scene.getObjectByName(n); if (o) { o.visible = false; out.push(n); } } return out.join(','); }, process.env.HIDE || ''));
await new Promise(r => setTimeout(r, 800));
await p.screenshot({ path: process.env.OUT, type: 'jpeg', quality: 70 });
await b.close();
