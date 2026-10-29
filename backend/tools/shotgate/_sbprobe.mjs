// Soapbox run: hold W, print position, height, speed and rivals every second. J=10018 node _sbprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 120000 }).catch(() => {});
await new Promise(r => setTimeout(r, 4000)); await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 2000));
console.log('goal', JSON.stringify(await p.evaluate(() => window.__game.goal())));
await p.keyboard.down('KeyW');
for (let s = 0; s < +(process.env.SEC || 24); s++) {
  await new Promise(r => setTimeout(r, 1000));
  console.log(s, JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); const q = window.__game.pos();
    return { pos: q.map(v => +v.toFixed(1)), v: f.drive && f.drive.speed, state: f.state || f.status, won: f.won, msg: (document.querySelector('#hud .obj') || {}).textContent }; })));
}
await p.keyboard.up('KeyW');
console.log('errs', JSON.stringify(errs.slice(0, 6)));
await b.close();
