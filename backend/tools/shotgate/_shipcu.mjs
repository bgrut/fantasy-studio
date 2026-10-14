// A close look at the hero from a few set angles: the camera is pinned each
// render to an offset from the hero. J=job_1393 OUT=<prefix> D=<distance> node _shipcu.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || 'cu', D = +(process.env.D || 22);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 120000 });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000));
await p.evaluate(() => { for (const el of document.querySelectorAll('#hud, .fs-card, #fsdlg, #toast')) el.style.visibility = 'hidden'; });
const views = [[0.6, 0.35, 'q'], [1.57, 0.12, 's'], [-2.4, 0.5, 'b']];
for (const [az, el, tag] of views) {
  await p.evaluate((az, el, D) => {
    let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
    const cam = window.__camera, R = window.__renderer, V = cam.position.constructor;
    if (!window.__cuOrig) window.__cuOrig = R.render.bind(R);
    R.render = (s, c) => { if (c === cam && pl) { const t = pl.getWorldPosition(new V()); t.y += 6;
      cam.position.set(t.x + Math.sin(az) * D * Math.cos(el), t.y + D * Math.sin(el), t.z + Math.cos(az) * D * Math.cos(el)); cam.lookAt(t); cam.updateMatrixWorld(); }
      return window.__cuOrig(s, c); };
  }, az, el, D);
  await new Promise(r => setTimeout(r, 1500));
  await p.screenshot({ path: `${OUT}_${tag}.jpg`, quality: 88 });
}
console.log('errors:', errs.length ? errs.join(' | ') : 'none');
await b.close();
