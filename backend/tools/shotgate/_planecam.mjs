// A flying hero shot from views that ride along with it: each frame the camera pin is
// re-placed in the craft's own frame (right, up, back), so a plane at 30 m/s stays framed.
//   J=job_N OUT=prefix [VIEWS='[[r,u,b],...]'] node _planecam.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(4000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(#app):not(script):not(style){visibility:hidden !important} #app > *:not(canvas){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
const views = JSON.parse(process.env.VIEWS || '[[4.5,1.4,-6],[-7,2.2,3],[0,3.2,11],[9,-1.5,-2]]');
for (let i = 0; i < views.length; i++) {
  await p.evaluate(v => {
    cancelAnimationFrame(window.__pcLoop || 0);
    const step = () => {
      const pl = window.__plane || window.__balloon || window.__board; if (!pl) return;
      pl.updateMatrixWorld(true);
      const e = pl.matrixWorld.elements, o = [e[12], e[13], e[14]];
      // the craft's own axes: x right (local +X), y up, z back (local +Z, the nose is -Z)
      const ax = [e[0], e[1], e[2]], ay = [e[4], e[5], e[6]], az = [e[8], e[9], e[10]];
      const at = (r, u, bk) => [0, 1, 2].map(k => o[k] + ax[k] * r + ay[k] * u + az[k] * bk);
      window.__camPin = { pos: at(v[0], v[1], v[2]), look: at(0, 0.3, -0.5) };
      window.__pcLoop = requestAnimationFrame(step);
    };
    step();
  }, views[i]);
  await wait(1600); await p.screenshot({ path: `${process.env.OUT}_${i}.jpg`, type: 'jpeg', quality: 88 });
}
console.log(JSON.stringify(await p.evaluate(() => window.__planeState || null)), errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
