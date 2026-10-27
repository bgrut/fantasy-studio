// Throw at the cans: stand at the counter, press F again and again, sample what falls, shoot the stall.
// J=job_N OUT=prefix node _cans.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,800', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 90000 }).catch(() => {});
await wait(4000); await p.click('#startbtn').catch(() => {});
await p.waitForFunction(() => window.__game && !(window.__game.facts && window.__game.facts().intro), { timeout: 30000 }).catch(() => {});
await p.waitForFunction(() => window.__cans, { timeout: 120000 }).catch(() => {});
await wait(4000);
await p.evaluate(() => { window.__game.tp(0.2, 5.3); window.__game.face(0, 9); window.__camPin = { pos: [2.6, 2.4, 2.6], look: [0, 1.3, 8.6] }; });
await wait(1200);
await p.screenshot({ path: `${process.env.OUT}_stall.jpg`, type: 'jpeg', quality: 86 });
const S = [];
for (let k = 0; k < 40; k++) {
  await p.evaluate((k) => window.__game.face([-1.5, 0, 1.5][Math.floor(k / 7) % 3], 9), k);
  await p.keyboard.press('KeyF');
  await wait(k === 1 ? 260 : 700);
  if (k === 1) { await p.screenshot({ path: `${process.env.OUT}_fly.jpg`, type: 'jpeg', quality: 86 }); await wait(440); }
  const c = await p.evaluate(() => window.__cans());
  S.push(c); if (k === 5) await p.screenshot({ path: `${process.env.OUT}_hit.jpg`, type: 'jpeg', quality: 86 });
  if (c.won) break;
}
await wait(1500);
await p.evaluate(() => { const q = window.__game.pos(); window.__camPin = { pos: [q[0] + 1.6, q[1] + 1.6, q[2] - 2.6], look: [q[0], q[1] + 0.8, q[2]] }; });
await wait(900); await p.screenshot({ path: `${process.env.OUT}_bear.jpg`, type: 'jpeg', quality: 86 });
console.log(S.map((c, i) => `${i}: thrown${c.thrown} down${c.down} piles${c.piles} won${c.won} near${c.near}`).join('\n'));
console.log(JSON.stringify(await p.evaluate(() => window.__game.objectives && window.__game.objectives())).slice(0, 300));
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
