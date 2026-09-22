// A frame mid-slide: boost to speed, handbrake and steer, and shoot while the
// marks are being laid and the smoke is up.   A=<drift job id>
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--ignore-gpu-blocklist','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760, deviceScaleFactor: 1 });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
await wait(9000); const btn = await p.$('#startbtn'); if (btn) await btn.click();
await p.keyboard.down('KeyW');
for (let i = 0; i < 40; i++) { await wait(500); const f = await p.evaluate(() => window.__game.facts()); if (f.drive && f.drive.speed > 1) break; }
await wait(3500);
await p.keyboard.down('Space'); await p.keyboard.down('KeyD'); await wait(700);
await p.screenshot({ path: 'drift_slide.png' });
await wait(500); await p.keyboard.up('Space'); await p.keyboard.up('KeyD'); await wait(1200);
await p.screenshot({ path: 'drift_after.png' });
console.log(JSON.stringify(await p.evaluate(() => window.__game.facts().drive)));
await b.close();
