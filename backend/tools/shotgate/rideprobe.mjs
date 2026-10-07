// What the hips do through fbuilding's own sequence (walk, run, jump, land,
// stop, walk again), logged every frame from inside the page: the hips bone's
// height, the gait blend, the motion-matching take. For a hip-ride failure,
// shows which moment and which take carries the dip.
//   J=<bare job number> node rideprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await sleep(9000); await p.click('#startbtn').catch(() => {}); await sleep(2500); await p.keyboard.press('g');
await p.evaluate(() => {
  let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
  let hips = null; pl.traverse(o => { if (!hips && o.isBone && /^hips$/i.test(o.name)) hips = o; });
  const V = pl.position.constructor, v = new V(); window.__rlog = []; let mark = '';
  window.__rmark = m => { mark = m; };
  const tick = () => { hips.getWorldPosition(v); const f = window.__game.facts(), m = window.__mm ? window.__mm() : null;
    window.__rlog.push([mark, +(v.y - pl.position.y).toFixed(3), f.gait ? +(f.gait.run || 0).toFixed(2) : null, m && m.on ? m.take : '-', +(f.walk_v || 0).toFixed(2)]);
    requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
});
const mark = m => p.evaluate(m => window.__rmark(m), m);
await mark('walk'); await p.keyboard.down('KeyW'); await sleep(760);
await mark('run'); await p.keyboard.down('ShiftLeft'); await sleep(1500);
await mark('jump'); await p.keyboard.down('Space'); await sleep(120); await p.keyboard.up('Space'); await sleep(1500);
await mark('stop'); await p.keyboard.up('ShiftLeft'); await p.keyboard.up('KeyW'); await sleep(900);
await mark('walk2'); await p.keyboard.down('KeyW'); await sleep(900);
await mark('end'); await sleep(100); await p.keyboard.up('KeyW');
const log = await p.evaluate(() => window.__rlog);
// per phase: hips height range and the takes seen
const by = {};
for (const [m, y, run, take, v] of log) { const o = by[m] || (by[m] = { lo: 9, hi: -9, takes: new Set(), runMax: 0, vMax: 0 }); o.lo = Math.min(o.lo, y); o.hi = Math.max(o.hi, y); o.takes.add(take); o.runMax = Math.max(o.runMax, run || 0); o.vMax = Math.max(o.vMax, v); }
for (const [m, o] of Object.entries(by)) console.log(m.padEnd(6), 'hips', o.lo.toFixed(3), '..', o.hi.toFixed(3), '(span', (o.hi - o.lo).toFixed(3) + ')', 'run<=', o.runMax, 'v<=', o.vMax, [...o.takes].slice(0, 5).join(' | '));
const last90 = log.slice(-90); const ys = last90.map(r => r[1]);
console.log('last 90 frames span', (Math.max(...ys) - Math.min(...ys)).toFixed(3), 'phases', [...new Set(last90.map(r => r[0]))].join(','));
await b.close();
