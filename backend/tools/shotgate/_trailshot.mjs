// Look along the designer's trail: J=job_N OUT=file node _trailshot.mjs
// FULL=1 re-reads the whole grass field first; HOLE=1 also clears a 12 m square at the hero
// (a check that re-reading the field works at all).
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.click('#startbtn').catch(() => {}); await w(4000);
const v = await p.evaluate(() => { const g = window.__trailSegs; if (!g || g.length < 8) return null; const a = g[3], c = g[Math.min(g.length - 1, 22)];
  const y = window.__hAt(a[0], a[1]); return { pos: [a[0] - (c[0] - a[0]) * 0.25, y + 3.2, a[1] - (c[1] - a[1]) * 0.25], look: [c[0], window.__hAt(c[0], c[1]), c[1]] }; });
console.log(JSON.stringify(v));
if (process.env.FULL) {
  const ms = await p.evaluate((hole) => {
    if (hole) { const q = window.__game.pos(); (window.__grassHoles = window.__grassHoles || []).push({ x: q[0], z: q[2], c: 1, s: 0, hx: 6, hz: 6 }); }
    return window.__grassRemask();
  }, !!process.env.HOLE);
  console.log('full remask ms', ms);
}
if (v) { await p.evaluate(v => { window.__camPin = v; }, v); await w(1800); await p.screenshot({ path: process.env.OUT, type: 'jpeg', quality: 86 }); }
await b.close();
