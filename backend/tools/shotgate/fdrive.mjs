// The drive: steering eases with speed, the handbrake steps the rear out and
// leaves marks and smoke, the view widens with speed, and the street costs
// what it should (pedestrians cast shadows only up close). On the card.
//   A=<drift job id>   (skips without it)
import puppeteer from 'puppeteer-core';
const A = process.env.A;
if (!A) { console.log('skipped   : needs --adv (the drift race)'); process.exit(0); }
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--ignore-gpu-blocklist','--disable-frame-rate-limit','--disable-gpu-vsync','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760, deviceScaleFactor: 1 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto('http://127.0.0.1:8789/games/job_' + A + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
await wait(9000);
const btn = await p.$('#startbtn'); if (btn) await btn.click();
const F = () => p.evaluate(() => window.__game.facts());
// the countdown: hold W and wait until the car is actually moving, then six more seconds of throttle
await p.keyboard.down('KeyW');
for (let i = 0; i < 40; i++) { await wait(500); const f = await F(); if (f.drive && f.drive.speed > 1) break; }
await wait(6000);
const fast = await F();
// 2. steering eases with speed: at boost speed (Shift, the car's top) the ease is well under one
await p.keyboard.down('ShiftLeft'); await wait(4000);
const boost = await F();
await p.keyboard.up('ShiftLeft'); await wait(3000);
const cruise = await F();
// 3. the handbrake: at cruising speed, Space and A together
await p.keyboard.down('Space'); await p.keyboard.down('KeyA'); await wait(900);
const slide = await F();
await p.keyboard.up('Space'); await p.keyboard.up('KeyA'); await wait(600);
const after = await F();
// 4. the cost, with the limit off
await p.keyboard.up('KeyW');
const cost = await p.evaluate(async () => { const d = []; let last = performance.now(); const t0 = last;
  const tr = [];   // the cascades take turns, so the triangles are averaged over the window, not read off one frame
  await new Promise(done => { const tick = (t) => { d.push(t - last); last = t; tr.push(window.__renderer.info.render.triangles); if (t - t0 < 4000) requestAnimationFrame(tick); else done(); }; requestAnimationFrame(tick); });
  d.shift(); d.sort((a, b) => a - b); return { fps: +(1000 / (d.reduce((a, b) => a + b, 0) / d.length)).toFixed(0), p95: +d[Math.floor(d.length * 0.95)].toFixed(1), tris: Math.round(tr.reduce((a, b) => a + b, 0) / tr.length) }; });
console.log('the car   :', JSON.stringify(fast.car));
console.log('throttle  : speed', fast.drive && fast.drive.speed, 'm/s after 6 s of W (top', fast.drive && fast.drive.top, ') | fov', fast.fov, 'of', fast.fov_base);
console.log('steering  : ease', boost.drive && boost.drive.steer_ease, 'at', boost.drive && boost.drive.speed, 'm/s under boost |', cruise.drive && cruise.drive.steer_ease, 'at', cruise.drive && cruise.drive.speed, 'cruising');
console.log('handbrake :', JSON.stringify(slide.drive), '| after', after.drive && after.drive.drifting);
console.log('the cost  : fps', cost.fps, '| p95', cost.p95, 'ms | tris', cost.tris.toLocaleString(), '| peds visible', slide.drive && slide.drive.peds_visible, 'casting', slide.drive && slide.drive.peds_casting);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = fast.drive && fast.drive.speed > 7 && fast.fov > fast.fov_base + 3
  && fast.car && fast.car.smooth && fast.car.cabin && fast.car.pillars === 6 && fast.car.body_verts > 600   // a smooth-shaded body with a real greenhouse
  && boost.drive && boost.drive.speed > 15 && boost.drive.steer_ease < 0.85 && cruise.drive && cruise.drive.steer_ease > boost.drive.steer_ease   // eases with speed
  && slide.drive && slide.drive.handbrake && slide.drive.drifting && slide.drive.slip > 0.2 && slide.drive.skids > 0 && slide.drive.smoke > 0
  && slide.drive.peds_casting <= 30 && slide.drive.peds_casting < slide.drive.peds_visible
  && cost.fps >= 30 && cost.tris < 4200000                     // the triangles are the honest number; the frame rate on a shared card is only a floor
  && errs.length === 0;
if (!ok) console.log('FAIL: the drive');
process.exit(ok ? 0 : 1);
