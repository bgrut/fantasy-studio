// Walk the treehouse village: up the stair round the first tree, deck to deck across every bridge: J=job_N node _canwalk.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(3000); await p.click('#startbtn').catch(() => {}); await wait(4000);
const C = await p.evaluate(() => window.__canopy);
const H = C.houses, bp = () => p.evaluate(() => window.__game.bpos());
const steer = async (tx, tz, tol, maxS) => { await p.keyboard.down('KeyW'); let q = await bp(), t = 0;
  for (; t < maxS * 7; t++) { const dx = tx - q[0], dz = tz - q[2]; if (Math.hypot(dx, dz) < tol) break; await p.evaluate((y) => window.__game.look(y), Math.atan2(-dx, -dz)); await wait(140); q = await bp(); }
  await p.keyboard.up('KeyW'); return q; };
// the stair: from its foot, keep turning along the spiral until up at the deck
const h0 = H[0], RM = 3.6 + 0.65, aEnd = C.stair - 0.115 * 0.6, a0 = aEnd - (Math.floor((h0[1] - (h0[1] - 0)) ) ) ;
const ground = await p.evaluate((h) => window.__game.bpos && 0, h0);
const stA0 = await p.evaluate(() => { const c = window.__canopy; return c.stair - 0.115 * 0.6; });
const NT = Math.floor((h0[1] - (await p.evaluate((x, z) => 0, h0[0], h0[2])) ) / 0.21);
void a0; void ground; void NT;
// start a little before the stair's first tread: the first tread is a full turn back from the end
const first = stA0 - (Math.floor(11 / 0.21) - 1) * 0.115;
await p.evaluate((q) => window.__game.tp3(q[0], q[1], q[2]), [h0[0] + Math.cos(first - 0.25) * RM, h0[1] - 9, h0[2] + Math.sin(first - 0.25) * RM]); await wait(1500);
let q = await bp(); console.log('foot', q.map(v => +v.toFixed(2)));
let a = first; await p.keyboard.down('KeyW');
for (let t = 0; t < 400; t++) { q = await bp(); a = Math.atan2(q[2] - h0[2], q[0] - h0[0]); const tx = h0[0] + Math.cos(a + 0.25) * RM, tz = h0[2] + Math.sin(a + 0.25) * RM;
  await p.evaluate((y) => window.__game.look(y), Math.atan2(-(tx - q[0]), -(tz - q[2]))); await wait(120); if (q[1] > h0[1] + 0.5) break; }
await p.keyboard.up('KeyW'); q = await bp(); console.log('top of stair', q.map(v => +v.toFixed(2)), 'deck', h0[1]);
// onto the deck and across each bridge
q = await steer(h0[0] + Math.cos(C.stair) * 2.4, h0[2] + Math.sin(C.stair) * 2.4, 0.5, 8); console.log('on deck 0', q.map(v => +v.toFixed(2)));
for (let k = 0; k + 1 < H.length; k++) { const A = H[k], B = H[k + 1], u = Math.atan2(B[2] - A[2], B[0] - A[0]);
  // round the deck to the bridge's foot
  q = await bp(); let qa = Math.atan2(q[2] - A[2], q[0] - A[0]);
  for (let s2 = 0; s2 < 8; s2++) { let d = Math.atan2(Math.sin(u - qa), Math.cos(u - qa)); if (Math.abs(d) < 0.3) break; qa += Math.sign(d) * Math.min(Math.abs(d), 0.7); q = await steer(A[0] + Math.cos(qa) * 2.4, A[2] + Math.sin(qa) * 2.4, 0.5, 6); }
  q = await steer(A[0] + Math.cos(u) * 2.6, A[2] + Math.sin(u) * 2.6, 0.5, 6);
  q = await steer(B[0] - Math.cos(u) * 2.4, B[2] - Math.sin(u) * 2.4, 0.6, 30);
  console.log('house', k + 1, 'at', q.map(v => +v.toFixed(2)), 'deck', B[1]); }
await wait(1500);
console.log('facts', JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return { won: f.won, lost: f.lost, step: f.step }; })));
await p.screenshot({ path: process.env.OUT || 'canwalk.jpg', type: 'jpeg', quality: 80 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
