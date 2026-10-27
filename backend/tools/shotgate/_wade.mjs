// Walk through the creek where the path crosses it: sample the wading depth and the rings and splashes,
// shoot it from the side. J=job_N OUT=prefix [RUN=1] node _wade.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,800', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 90000 }).catch(() => {});
await wait(4000); await p.click('#startbtn').catch(() => {});
await p.waitForFunction(() => window.__game && !(window.__game.facts && window.__game.facts().intro), { timeout: 30000 }).catch(() => {});
await wait(3000);
const c = await p.evaluate(() => { const k = window.__creek && window.__creek(); if (!k || !k.crossings.length) return null; const [x, z] = k.crossings[0], L = Math.hypot(x, z) || 1;
  // across the creek: from the spawn's side, four metres back, to four metres past, a little off the stepping stones
  const ux = x / L, uz = z / L, vx = -uz, vz = ux, ox = vx * 2.2, oz = vz * 2.2;
  const A = [x - ux * 4 + ox, z - uz * 4 + oz], B = [x + ux * 6 + ox, z + uz * 6 + oz];
  window.__game.tp(A[0], A[1]); window.__game.face(B[0], B[1]); window.__game.setYaw(Math.atan2(-ux, -uz));
  window.__camPin = () => { const q = window.__game.pos(); return { pos: [q[0] + vx * 5.5 - ux * 1.5, q[1] + 2.2, q[2] + vz * 5.5 - uz * 1.5], look: [q[0], q[1] + 0.3, q[2]] }; };
  return { x, z, A, B, w: k.w }; });
if (!c) { console.log('no crossing'); await b.close(); process.exit(0); }
await wait(800);
if (process.env.RUN) await p.keyboard.down('ShiftLeft');
await p.keyboard.down('KeyW');
const S = [];
for (let k = 0; k < 36; k++) { await wait(300); S.push(await p.evaluate(() => ({ w: window.__wade ? window.__wade() : null, pos: window.__game.pos().map(v => +v.toFixed(2)) })));
  if (k === 20 || k === 25 || k === 30) await p.screenshot({ path: `${process.env.OUT}_${k}.jpg`, type: 'jpeg', quality: 86 }); }
await p.keyboard.up('KeyW'); if (process.env.RUN) await p.keyboard.up('ShiftLeft');
await wait(1500); await p.screenshot({ path: `${process.env.OUT}_out.jpg`, type: 'jpeg', quality: 86 });
console.log(JSON.stringify(c));
console.log(S.map((s, k) => `${k}: d${s.w && s.w.depth} wet${s.w && s.w.wet} rings${s.w && s.w.rings} drops${s.w && s.w.drops} @${s.pos}`).join('\n'));
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
