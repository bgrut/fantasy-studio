// A board put out past the break: does it float on the swell, get carried in, and count rides?
//   J=job_N OUT=prefix X= Z= node _surfcheck.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(5000);
await p.evaluate((x, z) => window.__game.tp(x, z), +process.env.X, +process.env.Z);
const track = [];
for (let i = 0; i < 16; i++) {
  await wait(1000);
  track.push(await p.evaluate(() => { const q = window.__game.pos(); const o = document.querySelector('#hud .obj, #obj, .objective'); return [+q[0].toFixed(1), +q[1].toFixed(2), +q[2].toFixed(1)]; }));
  if (i === 6) await p.screenshot({ path: `${process.env.OUT}_ride.jpg`, type: 'jpeg', quality: 85 });
}
const quest = await p.evaluate(() => (document.body.innerText.match(/Ride \d+ waves[^\n]*/) || [''])[0]);
console.log(JSON.stringify({ track, quest, errs }));
await b.close();
