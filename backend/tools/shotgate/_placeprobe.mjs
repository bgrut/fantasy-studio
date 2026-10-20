// The places a sentence named: where they stand, what logged, and a frame of each.
//   J=job_N OUT=prefix node _placeprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const logs = []; p.on('console', m => { const t = m.text(); if (/places|place_|\[places\]/.test(t)) logs.push(t.slice(0, 200)); });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.evaluateOnNewDocument((d) => { window.__PD = d; }, process.env.PD || '12');
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(5000);
const pl = await p.evaluate(() => window.__places);
console.log('places', JSON.stringify(pl)); console.log('logs', JSON.stringify(logs)); console.log('errors', JSON.stringify(errs));
for (const [k, q] of (pl || []).entries()) {
  await p.evaluate((q) => { const y = window.__hAt ? window.__hAt(q.at[0], q.at[1]) : 0;
    const D = +(window.__PD || 12); window.__camPin = { pos: [q.at[0] + D, y + D * 0.45, q.at[1] + D * 0.6], look: [q.at[0], y + 1.5, q.at[1]] }; }, q);
  await wait(1800);
  await p.screenshot({ path: `${process.env.OUT}_${k}_${q.kind}.jpg`, type: 'jpeg', quality: 85 });
}
await b.close();
