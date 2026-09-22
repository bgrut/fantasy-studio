// The car up close: a three-quarter front view at rest, and the hero on foot
// mid-turn. A=<drift job id>  B=<manor job id>
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--ignore-gpu-blocklist','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760, deviceScaleFactor: 1 });
const wait = ms => new Promise(r => setTimeout(r, ms));
if (process.env.A) {
  await p.goto('http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
  await wait(9000); const btn = await p.$('#startbtn'); if (btn) await btn.click(); await wait(2500);
  // the camera: a three-quarter front view, close, from the cinematic hook if any, else the chase cam pulled round
  await p.evaluate(() => { const c = window.__camera, pos = window.__game.pos(); const y = window.__game.heading();
    c.position.set(pos[0] - Math.sin(y + 2.4) * 5.2, pos[1] + 1.6, pos[2] - Math.cos(y + 2.4) * 5.2); c.lookAt(pos[0], pos[1] + 0.5, pos[2]); window.__cinePin = true; });
  await wait(300);
  await p.screenshot({ path: 'car_front.png' });
}
if (process.env.B) {
  await p.goto('http://127.0.0.1:8789/games/job_' + process.env.B + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
  await wait(9000); const btn = await p.$('#startbtn'); if (btn) await btn.click(); await wait(2500);
  await p.keyboard.down('KeyW'); await wait(700); await p.keyboard.down('KeyA'); await wait(300);
  await p.screenshot({ path: 'hero_turn.png' });
  await p.keyboard.up('KeyA'); await p.keyboard.up('KeyW');
}
await b.close();
