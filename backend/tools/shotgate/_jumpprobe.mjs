// Jump from the spawn while running and trace height and the landing dip. J=<job> node _jumpprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 960, height: 540 });
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 120000 });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500));
await p.evaluate(() => { if (window.__game.tp) window.__game.tp(0, 0); });
await new Promise(r => setTimeout(r, 700));
await p.evaluate(() => { window.__jt = []; const t0 = performance.now(); const f = () => { const g = window.__game, q = g.pos(), fa = g.facts();
  window.__jt.push([Math.round(performance.now() - t0), +q[0].toFixed(2), +q[1].toFixed(2), +q[2].toFixed(2), fa.land_dip_peak, fa.grounded]); if (performance.now() - t0 < 5200) requestAnimationFrame(f); }; requestAnimationFrame(f); });
await p.keyboard.down('KeyW'); await new Promise(r => setTimeout(r, 760));
await p.keyboard.down('ShiftLeft'); await new Promise(r => setTimeout(r, 1500));
await p.keyboard.down('Space'); await new Promise(r => setTimeout(r, 120)); await p.keyboard.up('Space');
await new Promise(r => setTimeout(r, 1500)); await p.keyboard.up('ShiftLeft'); await p.keyboard.up('KeyW');
await new Promise(r => setTimeout(r, 1000));
const t = await p.evaluate(() => window.__jt);
for (let i = 0; i < t.length; i += Math.max(1, Math.floor(t.length / 45))) console.log(JSON.stringify(t[i]));
await b.close();
