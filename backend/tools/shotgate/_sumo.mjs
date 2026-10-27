// Fight the sumo bouts: wait for the tachiai, hold W and thrust (F), sample the bout, shoot the ring.
// J=job_N OUT=prefix node _sumo.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,800', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 90000 }).catch(() => {});
await wait(4000); await p.click('#startbtn').catch(() => {});
await p.waitForFunction(() => window.__game && !(window.__game.facts && window.__game.facts().intro), { timeout: 30000 }).catch(() => {});
await p.evaluate(() => { window.__camPin = () => { const q = window.__game.pos(); return { pos: [q[0] + 7.5, q[1] + 3.2, q[2] + 1.5], look: [q[0], q[1] + 0.9, q[2] + 1.4] }; }; });
const S = [];
await p.waitForFunction(() => window.__sumo && window.__sumo().phase === 'enter', { timeout: 20000 }).catch(() => {});
await p.screenshot({ path: `${process.env.OUT}_enter.jpg`, type: 'jpeg', quality: 86 });
await p.evaluate(() => { window.__camPin = { pos: [-14, 9, -12], look: [0, 1, 9] }; }); await wait(500);
await p.screenshot({ path: `${process.env.OUT}_wide.jpg`, type: 'jpeg', quality: 86 });
await p.evaluate(() => { window.__camPin = () => { const q = window.__game.pos(); return { pos: [q[0] + 7.5, q[1] + 3.2, q[2] + 1.5], look: [q[0], q[1] + 0.9, q[2] + 1.4] }; }; });
for (let k = 0; k < 60; k++) {
  const st = await p.evaluate(() => window.__sumo());
  if (st.phase === 'push') { await p.keyboard.down('KeyW'); if (k % 3 === 0) await p.keyboard.press('KeyF'); }
  else await p.keyboard.up('KeyW');
  await p.evaluate(() => { const s = window.__sumo(), q = window.__game.pos(); if (s.cur) { window.__game.face(s.cur[0], s.cur[2]); window.__game.setYaw(Math.atan2(-(s.cur[0] - q[0]), -(s.cur[2] - q[2]))); } });
  await wait(300);
  S.push(Object.assign(st, { pos: (await p.evaluate(() => window.__game.pos())).map(v => +v.toFixed(2)) }));
  if (k === 12 || k === 20 || k === 30) await p.screenshot({ path: `${process.env.OUT}_${k}.jpg`, type: 'jpeg', quality: 86 });
}
await p.keyboard.up('KeyW');
console.log(S.filter((s, i) => i % 3 === 0).map(s => `${s.bout} ${s.phase} left${s.left} rival${s.cur} hero${s.pos}`).join('\n'));
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
