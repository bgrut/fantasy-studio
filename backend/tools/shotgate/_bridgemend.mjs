// A broken bridge over a creek: mend one and walk over it. J=job_N [OUT=prefix] node _bridgemend.mjs
// Walks up the ramp (y rises), is stopped by the gap in the deck, holds E, then crosses at deck height.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await w(500); }
await w(4000); await p.click('#startbtn').catch(() => {});
await p.evaluate(() => new Promise(res => { let n = 0, last = performance.now(); const f = () => { const t = performance.now(); n = t - last < 100 ? n + 1 : 0; last = t; if (n >= 20) res(); else requestAnimationFrame(f); }; requestAnimationFrame(f); }));
await w(1500);
const spots = await p.evaluate(() => window.__repairSpots ? window.__repairSpots() : []);
const info = await p.evaluate(() => { let br = null; window.__scene && window.__scene.traverse(o => { if (o.userData && o.userData.bridge && !br) br = { x: o.position.x, y: o.position.y, z: o.position.z, yaw: o.rotation.y }; }); return br; });
const out = { spots, bridge: info };
if (!info) { console.log(JSON.stringify(out), errs); await b.close(); process.exit(0); }
const nx = Math.cos(info.yaw), nz = -Math.sin(info.yaw), P = () => p.evaluate(() => window.__game.pos());
const go = async (ax, az) => { await p.evaluate((x, z) => window.__game.tp(x, z), ax, az); await p.keyboard.down('KeyW'); await w(300); await p.keyboard.up('KeyW'); await w(500); };
// on the bank beyond the ramp, facing the bridge
const sx = info.x - nx * 6.6, sz = info.z - nz * 6.6;
await go(sx, sz);
await p.evaluate((x, z) => window.__game.face(x, z), info.x, info.z);
out.bank = await P();
await p.keyboard.down('KeyW');
let peak = -1e9; out.w1 = []; for (let i = 0; i < 30; i++) { await w(200); const q = await P(); peak = Math.max(peak, q[1]); const al1 = (q[0] - info.x) * nx + (q[2] - info.z) * nz; out.w1.push([+al1.toFixed(1), +(q[1] - info.y).toFixed(2)]); if (al1 > -1.2) break; }
await p.keyboard.up('KeyW');
out.walked = await P(); out.deckPeakBefore = +(peak - info.y).toFixed(2);
out.distToCentre = +Math.hypot(out.walked[0] - info.x, out.walked[2] - info.z).toFixed(2);
if (process.env.OUT) await p.screenshot({ path: process.env.OUT + '_gap.jpg', type: 'jpeg', quality: 88 });
// mend it: hold E where the walk stopped, or from the middle of the span
await p.keyboard.down('KeyE'); for (let i = 0; i < 60; i++) { await w(200); const s = await p.evaluate(() => window.__repairSpots().length); if (s < spots.length) { out.mended = true; break; } } await p.keyboard.up('KeyE');
// is the game still running after the mend? frames in the next few seconds, and how long the longest gap between them
out.afterMend = await p.evaluate(() => new Promise(res => { let n = 0, last = performance.now(), worst = 0; const t0 = last; const f = () => { const t = performance.now(); worst = Math.max(worst, t - last); last = t; n++; if (t - t0 > 6000) res({ frames: n, worstMs: Math.round(worst) }); else requestAnimationFrame(f); }; requestAnimationFrame(f); }));
out.state = await p.evaluate(() => { const f = window.__game.facts ? window.__game.facts() : {}; return { won: f.won, lost: f.lost, live: f.live, hud: (document.querySelector('#toast,.toast') || {}).textContent || '', overlay: [...document.querySelectorAll('body > div')].filter(d => d.offsetWidth > window.innerWidth * 0.6 && d.offsetHeight > window.innerHeight * 0.6 && getComputedStyle(d).display !== 'none' && getComputedStyle(d).visibility !== 'hidden').map(d => d.id || d.className).slice(0, 6) }; });
if (process.env.OUT) await p.screenshot({ path: process.env.OUT + '_after.jpg', type: 'jpeg', quality: 88 });
await go(sx, sz); await p.evaluate((x, z) => window.__game.face(x, z), info.x, info.z);
await p.keyboard.down('KeyW');
let pk2 = -1e9, far = 0; out.w2 = []; for (let i = 0; i < 40; i++) { await w(200); const q = await P(); pk2 = Math.max(pk2, q[1]); const along = (q[0] - info.x) * nx + (q[2] - info.z) * nz; out.w2.push([+along.toFixed(1), +(q[1] - info.y).toFixed(2)]); far = Math.max(far, along); if (along > 6) break; }
await p.keyboard.up('KeyW');
out.deckPeakAfter = +(pk2 - info.y).toFixed(2); out.reachedAlong = +far.toFixed(2); out.errors = errs;
if (process.env.OUT) { await p.evaluate((x, y, z, nx, nz) => { window.__camPin = { pos: [x + nz * 7 - nx * 2, y + 2.6, z - nx * 7 - nz * 2], look: [x, y + 0.7, z] }; }, info.x, info.y, info.z, nx, nz); await w(1500); await p.screenshot({ path: process.env.OUT + '_side.jpg', type: 'jpeg', quality: 88 }); }
console.log(JSON.stringify(out));
await b.close();
