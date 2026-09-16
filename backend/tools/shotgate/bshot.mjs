import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.B + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
await new Promise(r => setTimeout(r, 9000));
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await new Promise(r => setTimeout(r, 3500));
for (const k of [0, 1]) {
  const r = await p.evaluate(async (k) => {
    const L = window.__game.landmark(); if (!L) return null;
    const dx = L.door[0], dz = L.door[1]; const nx = (0 - dx), nz = (0 - dz), nl = Math.hypot(nx, nz) || 1;
    window.__game.tp(dx + nx / nl * 16, dz + nz / nl * 16);
    const y = Math.atan2(-nx / nl, -nz / nl) + k * Math.PI;
    window.__game.look(y);
    await new Promise(r => setTimeout(r, 1200));
    return { yaw: +y.toFixed(2), pos: window.__game.pos().map(v => +v.toFixed(1)), door: [dx, dz] };
  }, k);
  console.log('heading', k, JSON.stringify(r));
  await p.screenshot({ path: 'bshot_' + k + '.png' });
}
await b.close();
