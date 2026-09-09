// Aim the first-person camera straight at the companion, and at the far plane
// from orbit: two things that had to be seen to be believed.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(() => {
  const r = window.__renderer, orig = r.render.bind(r), cam = window.__camera;
  const d = [0.82, 0.26, -0.51], L = Math.hypot(...d); d[0] /= L; d[1] /= L; d[2] /= L;
  r.render = (sc, c) => {
    if (c === cam) { cam.lookAt(cam.position.x + d[0], cam.position.y + d[1], cam.position.z + d[2]); cam.updateMatrixWorld(); }
    orig(sc, c);
  };
});
await new Promise(r=>setTimeout(r,600));
await p.screenshot({ path: (process.env.OUT || 'look') + '_planet.png' });
await b.close();
