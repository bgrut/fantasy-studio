// Does the build bar fit the screen? Every tool chip must sit wholly inside
// the viewport at the widths players actually have: at 1280 the twelfth chip
// used to run off the right edge.
//   URL=http://127.0.0.1:8790/ node toolfit.mjs
import puppeteer from 'puppeteer-core';
// the studio build when a job is given, the standalone demo otherwise
const URL = process.env.J ? 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/' : (process.env.URL || 'http://127.0.0.1:8790/');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
let bad = 0;
for (const [w, h] of [[1920, 1080], [1440, 900], [1366, 768], [1280, 720], [1024, 700]]) {
  const p = await b.newPage(); await p.setViewport({ width: w, height: h });
  await p.goto(URL + '?fresh=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await new Promise(r => setTimeout(r, 5000));
  const r = await p.evaluate(() => [...document.querySelectorAll('#tools .tool')]
    .filter(t => t.offsetParent)
    .map(t => { const q = t.getBoundingClientRect(); return [t.dataset.tool, Math.round(q.left), Math.round(q.right)]; }));
  const out = r.filter(([, l, rr]) => l < 0 || rr > w);
  if (out.length || !r.length) bad++;
  console.log(String(w).padEnd(5), r.length, 'tools', out.length ? 'OUTSIDE: ' + out.map(o => o[0]).join(',') : 'all inside');
  await p.close();
}
await b.close();
console.log(bad ? 'FAIL' : 'PASS');
process.exit(bad ? 1 : 0);
