// Break things: walk up to the breakables one at a time, swing, shoot the pieces flying and lying.
// J=job_N OUT=prefix [N=3] node _smash.mjs
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
const N = +(process.env.N || 3), out = [];
for (let i = 0; i < N; i++) {
  const tgt = await p.evaluate((i) => { const L = (window.__breakables || []).filter(q => !q.broken); const q = L[i * 3 % Math.max(1, L.length)]; if (!q) return null;
    const a = Math.atan2(-q.x, -q.z), x = q.x + Math.sin(a) * 1.25, z = q.z + Math.cos(a) * 1.25;
    window.__game.tp(x, z); return { x: q.x, z: q.z, kind: q.kind, fx: x, fz: z }; }, i);
  if (!tgt) break;
  await wait(600);
  await p.evaluate((t) => { window.__game.face(t.x, t.z);
    window.__camPin = { pos: [t.fx + (t.fx - t.x) * 2.6 + 1.6, window.__game.pos()[1] + 2.4, t.fz + (t.fz - t.z) * 2.6 + 1.2], look: [t.x, window.__game.pos()[1] + 0.5, t.z] }; }, tgt);
  await wait(500);
  await p.evaluate((t) => window.__game.face(t.x, t.z), tgt);
  await p.keyboard.press('KeyF');
  await wait(330); await p.screenshot({ path: `${process.env.OUT}_${i}a.jpg`, type: 'jpeg', quality: 86 });
  await wait(1700); await p.screenshot({ path: `${process.env.OUT}_${i}b.jpg`, type: 'jpeg', quality: 86 });
  out.push(Object.assign(tgt, await p.evaluate(() => ({ brk: window.__break && window.__break(), yard: window.__yard && window.__yard(), fps: window.__game.facts && window.__game.facts().fps }))));
}
console.log(JSON.stringify(out.map(o => ({ kind: o.kind, at: [o.x, o.z], left: o.brk && o.brk.left, debris: o.brk && o.brk.debris, fps: o.fps }))), JSON.stringify(out.length ? out[out.length - 1].yard : null), errs.length ? 'ERR ' + errs.join(' | ') : '');
await b.close();
