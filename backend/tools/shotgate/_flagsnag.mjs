// Crystal Works: close-up of grove instances. KIND=dead|bush IDX=0 OUT=dir node _flagsnag.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(8000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
const verts = { dead: 1115, bush: 120 }[process.env.KIND || 'dead'];
const idxs = (process.env.IDX || '0,1,2').split(',').map(Number);
for (const k of idxs) {
  const pin = await p.evaluate((verts, k) => {
    const g = __scene.getObjectByName('grove');
    const m = g.children.find(c => c.geometry.attributes.position.count === verts);
    const M = new m.matrix.constructor(); m.getMatrixAt(k, M);
    const e = M.elements, P = [e[12], e[13], e[14]];
    // the face's up is the largest axis of the position
    const ax = [0, 1, 2].reduce((a, i) => Math.abs(P[i]) > Math.abs(P[a]) ? i : a, 0);
    const up = [0, 0, 0]; up[ax] = Math.sign(P[ax]);
    const side = [0, 0, 0]; side[(ax + 1) % 3] = 1;
    const pos = P.map((v, i) => v + up[i] * 2.2 + side[i] * 4.5), look = P.map((v, i) => v + up[i] * 1.0);
    window.__camPin = { pos, look }; return { P, pos };
  }, verts, k);
  await w(2500);
  await p.screenshot({ path: `${process.env.OUT}/snag${k}.jpg`, type: 'jpeg', quality: 88 });
  console.log(k, JSON.stringify(pin));
}
await b.close();
