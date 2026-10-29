// Crystal Works: a camera at eye height beside the tallest standing boulders on the top face. OUT=dir node _flagboulder.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(8000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
const spots = await p.evaluate(() => { const g = window.__factory.GEO.detailStone; let m = null; window.__scene.traverse(o => { if (o.isInstancedMesh && o.geometry === g) m = o; });
  const out = [], M = new m.matrix.constructor(), P = m.position.clone(), Q = m.quaternion.clone(), S = m.scale.clone();
  for (let k = 0; k < m.count; k++) { m.getMatrixAt(k, M); M.decompose(P, Q, S); if (S.y > S.x * 1.8 && P.y > 30) out.push([P.x, P.y, P.z, S.y]); }
  return { n: m.count, top: out.sort((a, c) => c[3] - a[3]).slice(0, 3) }; });
console.log(JSON.stringify(spots));
let k = 0;
for (const [x, y, z] of spots.top) {
  await p.evaluate(pn => { window.__camPin = pn; }, { pos: [x + 3.2, y + 1.4, z + 2.4], look: [x, y + 0.3, z] }); await w(2200);
  await p.screenshot({ path: `${process.env.OUT}/boulder${k++}.jpg`, type: 'jpeg', quality: 85 });
}
await b.close();
