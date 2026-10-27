// Frame time with parts of a scene switched off in turn: J=job_N TOGGLES='js array of [name, js-to-run]' node _fpsab.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(12000);
const meas = () => p.evaluate(() => new Promise(res => { const ts = []; let last = performance.now(); const f = (t) => { ts.push(t - last); last = t; if (ts.length < 40) requestAnimationFrame(f); else { ts.sort((a, b) => a - b); res([+(ts[20]).toFixed(1), +(ts[36]).toFixed(1)]); } }; requestAnimationFrame(f); }));
console.log('base', JSON.stringify(await meas()));
for (const [name, js] of eval(process.env.TOGGLES)) { await p.evaluate(js); await wait(1500); console.log(name, JSON.stringify(await meas())); }
await b.close();
