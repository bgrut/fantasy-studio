// Frame rate of a page: J=<job> (studio) or URL=...   node _fpsprobe.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
await p.goto(URL + (process.env.Q || '?fresh=1&nointro=1'), { waitUntil: 'domcontentloaded', timeout: 90000 });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__factory && window.__game))) break; await wait(500); }
await wait(4000);
for (let k = 0; k < 3; k++) {
  const r = await p.evaluate(() => new Promise(res => { let n = 0, worst = 0, last = performance.now(); const t0 = last;
    const f = () => { const t = performance.now(); worst = Math.max(worst, t - last); last = t; n++; if (t - t0 < 2000) requestAnimationFrame(f); else res({ fps: +(n / ((t - t0) / 1000)).toFixed(1), worst: Math.round(worst) }); };
    requestAnimationFrame(f); }));
  const gl = await p.evaluate(() => { try { const c = document.createElement('canvas').getContext('webgl2'); const d = c.getExtension('WEBGL_debug_renderer_info'); return c.getParameter(d.UNMASKED_RENDERER_WEBGL); } catch (e) { return 'n/a'; } });
  console.log(JSON.stringify(r), k === 0 ? gl : '');
}
await b.close();
