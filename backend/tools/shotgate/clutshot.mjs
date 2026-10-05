// What lies on the ground: the clutter's count, and the ground a few metres
// ahead of the hero from a low camera.   J=job_N OUT=<dir> node clutshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1400,800'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (/clutter/.test(m.text())) errs.push(m.text()); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 10000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1500));
const info = await p.evaluate(() => {
  const g = window.__game, pp = g.pos(), yaw = g.heading();
  const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
  // off the trail: three metres to the side of the hero, looking down at the ground ahead
  const sx = Math.cos(yaw) * 3, sz = -Math.sin(yaw) * 3;
  window.__camPin = { pos: [pp[0] + sx, pp[1] + 1.1, pp[2] + sz], look: [pp[0] + sx + fx * 2.6, pp[1] + 0.05, pp[2] + sz + fz * 2.6] };
  return { clutter: g.facts().clutter, calls: window.__frameCalls };
});
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/clutter_${J}.jpg`, type: 'jpeg', quality: 88 });
console.log(J, JSON.stringify(info), JSON.stringify(errs.slice(0, 3)));
await b.close();
