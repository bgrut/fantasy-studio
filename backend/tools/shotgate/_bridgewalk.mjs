// Walk the rope bridge over the gorge end to end: sample how far it sags under the walker and whether
// they stay on it, and shoot it from the side as they go. J=job_N OUT=prefix node _bridgewalk.mjs
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
const g0 = await p.evaluate(() => window.__gorge && window.__gorge());
if (!g0) { console.log('no gorge', errs.join(' | ')); await b.close(); process.exit(0); }
// stand two metres short of the near end, facing across
await p.evaluate((g) => { const ux = g.B[0] - g.A[0], uz = g.B[2] - g.A[2], L = Math.hypot(ux, uz);
  window.__game.tp(g.A[0] - ux / L * 2.5, g.A[2] - uz / L * 2.5); window.__game.face(g.B[0], g.B[2]);
  // a camera out to the side of the bridge, a little above it, looking at the walker
  window.__camPin = () => { const q = window.__game.pos(), vx = -uz / L, vz = ux / L; return { pos: [q[0] + vx * 9 - ux / L * 3, q[1] + 2.5, q[2] + vz * 9 - uz / L * 3], look: [q[0], q[1] + 0.6, q[2]] }; };
}, g0);
await wait(800);
// the camera's yaw decides what W means: aim it across the bridge
await p.evaluate((g) => { if (window.__game.setYaw) window.__game.setYaw(Math.atan2(-(g.B[0] - g.A[0]), -(g.B[2] - g.A[2]))); }, g0);
const samples = [];
await p.keyboard.down('KeyW');
for (let k = 0; k < 44; k++) {
  await p.evaluate((g) => window.__game.face(g.B[0], g.B[2]), g0);
  await wait(500);
  const s = await p.evaluate(() => ({ g: window.__gorge(), pos: window.__game.pos() }));
  samples.push({ k, on: s.g.on, sag: s.g.sagMid, lat: s.g.latMid, y: +s.pos[1].toFixed(2), x: +s.pos[0].toFixed(1), z: +s.pos[2].toFixed(1) });
  if (k === 6 || k === 18 || k === 30) await p.screenshot({ path: `${process.env.OUT}_${k}.jpg`, type: 'jpeg', quality: 86 });
}
await p.keyboard.up('KeyW');
await wait(600); await p.screenshot({ path: `${process.env.OUT}_end.jpg`, type: 'jpeg', quality: 86 });
console.log(JSON.stringify(g0));
console.log(samples.map(s => `${s.k}:${s.on ? 'ON' : '--'} y${s.y} sag${s.sag} lat${s.lat} @${s.x},${s.z}`).join('\n'));
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
