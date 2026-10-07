// The building a sentence named, from out in front of its door: the venue
// the runtime stood up (window.__landmark), framed whole.
//   J=job_N OUT=<dir> TAG=<name> [BACK=metres] node landmarkshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'landmark', BACK = +(process.env.BACK || 0);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000)); await p.keyboard.press('g').catch(() => {});
const L = await p.evaluate(() => window.__landmark || null);
if (L) {
  await p.evaluate(() => { document.querySelectorAll('div,span,p,h1,h2,section').forEach(e => { if (!e.querySelector('canvas')) e.style.opacity = 0; }); });
  await p.evaluate((L, BACK) => { const [cx, cz] = L.at, [dx, dz] = L.door; const nx = dx - cx, nz = dz - cz, nl = Math.hypot(nx, nz) || 1;
    const back = BACK || Math.max(L.w, L.h) * 1.9 + 8, side = 0.35 * back;
    window.__camPin = { pos: [cx + nx / nl * back + nz / nl * side, (L.gy || 0) + L.h * 0.45 + 3, cz + nz / nl * back - nx / nl * side], look: [cx, (L.gy || 0) + L.h * 0.38, cz] }; }, L, BACK);
  await new Promise(r => setTimeout(r, 2000));
  await p.screenshot({ path: `${OUT}/${TAG}_landmark.jpg`, type: 'jpeg', quality: 90 });
}
console.log(TAG, 'landmark', JSON.stringify(L), 'errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
