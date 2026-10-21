// How long the GPU stays busy after a game loads: J=job_N node _backlog.mjs. Every second of
// the opening card it reads one pixel back (a sync point: it waits on everything queued) and
// prints that wait with the program count; a long wait is shader builds still in flight.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
const rows = [];
for (let s = 0; s < 40; s++) {
  rows.push(await p.evaluate(() => { const gl = window.__renderer.getContext(), px = new Uint8Array(4), t0 = performance.now();
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return [Math.round(t0 / 1000), Math.round(performance.now() - t0), window.__renderer.info.programs.length, window.__precompiled || 0]; }));
  await w(1000);
}
console.log('[t s, sync ms, programs, precompiles]'); console.log(rows.map(r => r.join('/')).join('  '));
await b.close();
