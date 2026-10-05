// The grass field up close: the play view, a low look across the ground a few
// metres off the trail, and a close look at the blades at the hero's feet.
//   URL=<game index.html> OUT=<dir> TAG=<name> node grassshot.mjs
//   (or J=job_N for a job the backend serves)
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || `http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`;
const OUT = process.env.OUT || '.', TAG = process.env.TAG || process.env.J || 'grass';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1400,800'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
p.on('console', m => { if (m.type() === 'error' || /grass|shader|THREE\.WebGLProgram/i.test(m.text())) errs.push(m.text().slice(0, 300)); });
await p.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 10000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 2500));
await p.screenshot({ path: `${OUT}/grass_${TAG}_play.jpg`, type: 'jpeg', quality: 88 });
const pin = (side, h, ahead, lookY) => p.evaluate((side, h, ahead, lookY) => {
  const g = window.__game, pp = g.pos(), yaw = g.heading();
  const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
  const sx = Math.cos(yaw) * side, sz = -Math.sin(yaw) * side;
  window.__camPin = { pos: [pp[0] + sx, pp[1] + h, pp[2] + sz], look: [pp[0] + sx + fx * ahead, pp[1] + lookY, pp[2] + sz + fz * ahead] };
  return { grass: window.__grass, fps: window.__fps || null };
}, side, h, ahead, lookY);
const info = await pin(3, 1.1, 2.6, 0.05);
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/grass_${TAG}_low.jpg`, type: 'jpeg', quality: 88 });
await pin(3, 0.45, 1.2, 0.1);
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/grass_${TAG}_close.jpg`, type: 'jpeg', quality: 88 });
const fps = await p.evaluate(() => new Promise(res => { let n = 0; const t0 = performance.now();
  const f = () => { n++; if (performance.now() - t0 < 2000) requestAnimationFrame(f); else res(+(n / 2).toFixed(1)); }; requestAnimationFrame(f); }));
console.log(TAG, JSON.stringify(info), 'fps', fps, JSON.stringify(errs.slice(0, 4)));
await b.close();
