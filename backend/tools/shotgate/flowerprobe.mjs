// Pins the camera beside a planted wildflower and shoots it.  J=job_N OUT=<dir> node flowerprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 10000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1500));
const info = await p.evaluate(() => {
  const out = [];
  window.__scene.traverse(o => { if (o.isInstancedMesh && o.name === 'clutter_flower') out.push(o); });
  if (!out.length || !out[0].count) return { err: 'no flowers', n: out.length };
  const m = out[0], M = new m.matrix.constructor(), P = new window.__scene.position.constructor();
  m.getMatrixAt(Math.floor(m.count / 2), M); P.setFromMatrixPosition(M);
  window.__camPin = { pos: [P.x + 1.4, P.y + 0.9, P.z + 1.4], look: [P.x, P.y + 0.45, P.z] };
  return { at: P.toArray().map(v => +v.toFixed(2)), counts: out.map(o => o.count), vis: m.visible };
});
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/flower_probe.jpg`, type: 'jpeg', quality: 88 });
console.log(JSON.stringify(info), JSON.stringify(errs.slice(0, 3)));
await b.close();
