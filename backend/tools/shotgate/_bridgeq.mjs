// The broken bridges and the named places: J=job_N OUT=prefix node _bridgeq.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!window.__scene)) break; await w(500); }
await w(4000); await p.click('#startbtn').catch(() => {}); await w(5000);
const info = await p.evaluate(() => ({ repair: window.__repair ? window.__repair() : null, places: window.__places }));
console.log(JSON.stringify(info));
const q = info.repair && info.repair.panels[0];
if (q) { await p.evaluate(q => { const y = window.__hAt(q[0], q[1]); window.__camPin = { pos: [q[0] + 6, y + 3.2, q[1] + 6], look: [q[0], y + 0.8, q[1]] }; }, q); await w(1600); await p.screenshot({ path: process.env.OUT + '_bridge.jpg', type: 'jpeg', quality: 85 });
  // mend it: stand there and hold E
  await p.evaluate(q => { window.__camPin = null; window.__game.tp(q[0] + 0.5, q[1] + 0.5); }, q); await w(600);
  await p.keyboard.down('KeyE'); await w(2200); await p.keyboard.up('KeyE'); await w(400);
  console.log('after E', JSON.stringify(await p.evaluate(() => window.__repair())));
  await p.evaluate(q => { const y = window.__hAt(q[0], q[1]); window.__camPin = { pos: [q[0] + 6, y + 3.2, q[1] + 6], look: [q[0], y + 0.8, q[1]] }; }, q); await w(1200); await p.screenshot({ path: process.env.OUT + '_mended.jpg', type: 'jpeg', quality: 85 }); }
const pl = (info.places || [])[0];
if (pl) { await p.evaluate(t => { const y = window.__hAt(t[0], t[1]); window.__camPin = { pos: [t[0] + 26, y + 12, t[1] + 26], look: [t[0], y + 5, t[1]] }; }, pl.at); await w(1600); await p.screenshot({ path: process.env.OUT + '_place.jpg', type: 'jpeg', quality: 85 }); }
console.log(JSON.stringify(errs));
await b.close();
