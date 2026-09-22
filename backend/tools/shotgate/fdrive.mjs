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

// the frame's luminance, read back in the page from a screenshot (the canvas
// itself is not preserved): the whole frame, the sky band, and a box around a screen point
const lumOf = async (p, box) => {
  const b64 = await p.screenshot({ encoding: 'base64' });
  return p.evaluate(async (b64, box) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const stat = (x, y, w, h) => { const d = g.getImageData(Math.max(0, x | 0), Math.max(0, y | 0), Math.max(1, w | 0), Math.max(1, h | 0)).data; let s = 0; for (let i = 0; i < d.length; i += 4) s += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; return +(s / (d.length / 4)).toFixed(1); };
    return { frame: stat(0, 0, c.width, c.height), sky: stat(0, 0, c.width, c.height * 0.12), box: box ? stat(box[0], box[1], box[2], box[3]) : null };
  }, b64, box);
};
const heroBox = (p) => p.evaluate(() => { const v = window.__game.pos();   const pr = { x: v[0], y: v[1] + 0.9, z: v[2] }; const cam = window.__camera; const m = cam.matrixWorldInverse; const pm = cam.projectionMatrix;
  const x = pr.x * m.elements[0] + pr.y * m.elements[4] + pr.z * m.elements[8] + m.elements[12];
  const y = pr.x * m.elements[1] + pr.y * m.elements[5] + pr.z * m.elements[9] + m.elements[13];
  const z = pr.x * m.elements[2] + pr.y * m.elements[6] + pr.z * m.elements[10] + m.elements[14];
  const w = pr.x * m.elements[3] + pr.y * m.elements[7] + pr.z * m.elements[11] + m.elements[15];
  const cx = (x * pm.elements[0] + z * pm.elements[8]) / -z, cy = (y * pm.elements[5] + z * pm.elements[9]) / -z;
  const sx = (cx * 0.5 + 0.5) * innerWidth, sy = (1 - (cy * 0.5 + 0.5)) * innerHeight; return [sx - 35, sy - 70, 70, 140]; });
const lightD = await p.evaluate(() => window.__game.facts().light);
const lumD = await lumOf(p, null);
console.log('the light :', JSON.stringify(lightD), '| frame', lumD.frame, '| sky', lumD.sky);
console.log('the car   :', JSON.stringify(fast.car));
console.log('throttle  : speed', fast.drive && fast.drive.speed, 'm/s after 6 s of W (top', fast.drive && fast.drive.top, ') | fov', fast.fov, 'of', fast.fov_base);
console.log('steering  : ease', boost.drive && boost.drive.steer_ease, 'at', boost.drive && boost.drive.speed, 'm/s under boost |', cruise.drive && cruise.drive.steer_ease, 'at', cruise.drive && cruise.drive.speed, 'cruising');
console.log('handbrake :', JSON.stringify(slide.drive), '| after', after.drive && after.drive.drifting);
console.log('the cost  : fps', cost.fps, '| p95', cost.p95, 'ms | tris', cost.tris.toLocaleString(), '| peds visible', slide.drive && slide.drive.peds_visible, 'casting', slide.drive && slide.drive.peds_casting);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = fast.drive && fast.drive.speed > 7 && fast.fov > fast.fov_base + 3
  && (!lightD.night || (lightD.moon <= 0.6 && lumD.frame < 105 && lumD.sky < 75))   // a night that reads as night
  && fast.car && fast.car.smooth && fast.car.cabin && fast.car.pillars === 6 && fast.car.body_verts > 600   // a smooth-shaded body with a real greenhouse
  && boost.drive && boost.drive.speed > 15 && boost.drive.steer_ease < 0.85 && cruise.drive && cruise.drive.steer_ease > boost.drive.steer_ease   // eases with speed
  && slide.drive && slide.drive.handbrake && slide.drive.drifting && slide.drive.slip > 0.2 && slide.drive.skids > 0 && slide.drive.smoke > 0
  && slide.drive.peds_casting <= 30 && slide.drive.peds_casting < slide.drive.peds_visible
  && cost.fps >= 30 && cost.tris < 4200000                     // the triangles are the honest number; the frame rate on a shared card is only a floor
  && errs.length === 0;
if (!ok) console.log('FAIL: the drive');
process.exit(ok ? 0 : 1);
