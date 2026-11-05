// Crystal Works close: a crystal outcrop in the meadow, the camera low beside it, at 2x pixels.
// OUT=file.jpg [URL=] [DIST=1.6] [K=0 (which outcrop, nearest first)] node _flagcloseup.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900, deviceScaleFactor: 2 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(7000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
const pin = await p.evaluate((D, K) => {
  // the crystal outcrops on the top face, nearest the start first
  const out = []; let om = null;
  window.__scene.traverse(o => { if (o.isInstancedMesh && o.name === 'outcrops' && o.count && !om) { om = o; } });
  const all = []; window.__scene.traverse(o => { if (o.isInstancedMesh && o.name === 'outcrops') all.push(o); });
  for (const m of all) { const M = m.matrixWorld.clone(), t = M.clone();
    for (let i = 0; i < m.count; i++) { m.getMatrixAt(i, t); t.premultiply(m.matrixWorld); const v = new window.__camera.position.constructor().setFromMatrixPosition(t);
      if (v.y > 30 && m.material.emissive && m.material.emissive.b > m.material.emissive.r) out.push([v.x, v.y, v.z]); } }
  out.sort((a, b) => Math.hypot(a[0], a[2]) - Math.hypot(b[0], b[2]));
  const c = out[K] || [0, 34.7, 3];
  return { pos: [c[0] + D * 0.8, c[1] + D * 0.38, c[2] + D * 0.6], look: [c[0], c[1] + 0.12, c[2]], n: out.length };
}, +(process.env.DIST || 1.6), +(process.env.K || 0));
await p.evaluate(pn => { window.__camPin = { pos: pn.pos, look: pn.look }; }, pin);
await w(2500); await p.screenshot({ path: process.env.OUT, type: 'jpeg', quality: 92 });
console.log(JSON.stringify(pin));
await b.close();
