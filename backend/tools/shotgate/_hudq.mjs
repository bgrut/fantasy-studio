// Which HUD elements are first painted at Start: J=job_N node _hudq.mjs. Lists every element
// shown (with its route to an id) in play that was not shown during the opening card.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
await w(2000);
const shown = () => p.evaluate(() => { const out = {};
  const path = e => { const a = []; for (let n = e; n && n !== document.body && a.length < 4; n = n.parentElement) { a.push(n.id ? '#' + n.id : n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\s+/)[0] : '')); if (n.id) break; } return a.reverse().join(' > '); };
  for (const e of document.body.querySelectorAll('*')) { if (e.closest('#fsstart')) continue; const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue;
    let ok = true; for (let n = e; n && ok; n = n.parentElement) { const s = getComputedStyle(n); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity < 0.02) ok = false; }
    if (ok) out[path(e)] = (out[path(e)] || 0) + 1; }
  return out; });
const a = await shown();
await p.click('#startbtn').catch(() => {}); await w(+(process.env.AFTER || 5000));
const c = await shown();
console.log('during the card:', Object.keys(a).length, 'in play:', Object.keys(c).length);
for (const k of Object.keys(c)) if (!a[k]) console.log('  new  ' + k);
await b.close();
