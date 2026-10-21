// Which lights change at Start: J=job_N node _lightsq.mjs. Lists every light shown before
// and after the click; a light that appears or vanishes rebuilds every lit program.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
await w(+(process.env.CLICK || 15000));
const L = () => p.evaluate(() => { const out = []; const sc = window.__scene || (window.__game && window.__game.scene);
  const walk = (o, vis, path) => { const v = vis && o.visible; const pth = path + '/' + (o.name || o.type);
    if (o.isLight) out.push((v ? 'ON  ' : 'off ') + o.type + ' ' + pth.slice(-90) + ' i=' + (+o.intensity).toFixed(2)); for (const c of o.children) walk(c, v, pth); };
  walk(sc, true, ''); return out; });
const a = await L(); await p.click('#startbtn').catch(() => {}); await w(3000); const c = await L();
console.log('before', a.filter(x => x.startsWith('ON')).length, 'after', c.filter(x => x.startsWith('ON')).length);
for (const x of c) if (!a.includes(x)) console.log('  + ' + x);
for (const x of a) if (!c.includes(x)) console.log('  - ' + x);
await b.close();
