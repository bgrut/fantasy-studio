// A flagship ore seam close up: the player stands two metres from one, looking at it.
//   OUT=<dir> node seamshot.mjs
import puppeteer from 'puppeteer-core';
const OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('response', r => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url()); });
await p.goto(process.env.URL || 'http://127.0.0.1:8790/', { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 8000));
await p.keyboard.press('Enter').catch(() => {}); await new Promise(r => setTimeout(r, 4000)); await p.keyboard.press('g').catch(() => {});
await new Promise(r => setTimeout(r, 1200));
const got = await p.evaluate(() => {
  const S = window.__scene, F = window.__factory, V = S.position.constructor;
  let bed = null;
  S.traverse(o => { if (!bed && o.name === 'bed' && o.parent) bed = o; });
  if (!bed) return 'no seam';
  const t = bed.getWorldPosition(new V());
  const ax = [Math.abs(t.x), Math.abs(t.y), Math.abs(t.z)], k = ax.indexOf(Math.max(...ax));
  const f = F.FACES.findIndex(F_ => Math.abs(F_.n[k]) === 1 && Math.sign(F_.n[k]) === Math.sign([t.x, t.y, t.z][k]));
  const n = new V(...F.FACES[f].n), u = new V(...F.FACES[f].u);
  F.player.face = f; F.player.up.copy(n);
  F.player.pos.copy(t).addScaledVector(u, -2.2).addScaledVector(n, 1.2);
  F.player.fwd.copy(u); F.player.pitch = -0.42;
  return [t.x, t.y, t.z].map(v => +v.toFixed(1));
});
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/seam_close.jpg`, type: 'jpeg', quality: 88 });
console.log(JSON.stringify(got), JSON.stringify(errs.slice(0, 5)));
await b.close();
