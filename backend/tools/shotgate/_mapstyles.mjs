// Every minimap style on one city: J=job_N OUT=prefix [STYLES=a,b] node _mapstyles.mjs
// Loads the game with ?map=<style>, starts it, and saves the map's own corner of the frame
// (window.__minimap says where), plus the maker's own pick with no override.
import puppeteer from 'puppeteer-core';
const STYLES = (process.env.STYLES || 'auto,radar,mono,paper,chart,ink,blueprint,neon,pixel,tape,wash').split(',');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const w = ms => new Promise(r => setTimeout(r, ms));
for (const st of STYLES) {
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
  await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1${st === 'auto' ? '' : '&map=' + st}`, { waitUntil: 'domcontentloaded' });
  for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
  await w(1500); await p.click('#startbtn').catch(() => {}); await w(3500);
  const m = await p.evaluate(() => { const c = [...document.querySelectorAll('canvas')].find(q => q.style.position === 'fixed' && q.style.bottom); if (!c) return null; const r = c.getBoundingClientRect(); return { r: [r.x, r.y, r.width, r.height], info: window.__minimap }; });
  if (m) await p.screenshot({ path: `${process.env.OUT}_${st}.png`, clip: { x: Math.max(0, m.r[0] - 12), y: Math.max(0, m.r[1] - 12), width: m.r[2] + 24, height: m.r[3] + 24 } });
  console.log(st, JSON.stringify(m && m.info), errs.length ? 'ERR ' + errs[0] : '');
  await p.close();
}
await b.close();
