// The maker each job drew: J=job_N node _vibeq.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
for (const J of process.env.J.split(',')) {
  const p = await b.newPage();
  await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 9000));
  const v = await p.evaluate(async () => { await document.fonts.ready; const V = window.__vibe || {};
    return Object.assign({}, V, { loaded: document.fonts.check('20px ' + JSON.stringify(V.head || 'x')), frame: document.body.dataset.art }); });
  console.log(J, JSON.stringify(v)); await p.close();
}
await b.close();
