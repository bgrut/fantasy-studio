// The runs bridge: the runtime tells its parent the kept runs at boot and on
// every change, and answers keep, open and forget. A top-level page is its own
// parent, so the page's window sees exactly what the studio's frame would.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';
await p.evaluateOnNewDocument(() => { window.__runsMsgs = []; addEventListener('message', e => { if (e.data && e.data.type === 'fs-runs') window.__runsMsgs.push(e.data.runs); }); });
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 5000));
const r = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const count = () => { let n = 0; for (let f = 0; f < 6; f++) for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) { const t = F.cells[f][i][j].t; if (t !== TY.EMPTY && t !== TY.NODE && t !== TY.PROP) n++; } return n; };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const last = () => window.__runsMsgs[window.__runsMsgs.length - 1];
  const atBoot = window.__runsMsgs.length;                    // told at boot, before anything was kept
  window.postMessage({ type: 'fs-runs-ask' }, '*'); await wait(200);
  const asked = window.__runsMsgs.length;
  let spot = null; for (let i = 3; i < F.N - 3 && !spot; i++) for (let j = 3; j < F.N - 3 && !spot; j++) if (F.cells[0][i][j].t === TY.EMPTY) spot = [i, j];
  F.addValue(500); F.place(0, spot[0], spot[1], TY.SMELTER, 0); await wait(300);
  const m0 = count();
  window.postMessage({ type: 'fs-keep-run', name: 'from the studio' }, '*'); await wait(900);
  const kept = last();
  F.wipe(); await wait(300); const m1 = count();
  window.postMessage({ type: 'fs-open-run', id: kept[0] && kept[0].id }, '*'); await wait(700);
  const m2 = count();
  window.postMessage({ type: 'fs-forget-run', id: kept[0] && kept[0].id }, '*'); await wait(400);
  return { atBoot, asked, m0, kept: kept ? kept.length : -1, name: kept && kept[0] && kept[0].name, thumb: !!(kept && kept[0] && kept[0].thumb && kept[0].thumb.startsWith('data:image/jpeg')),
           machines: kept && kept[0] && kept[0].machines, m1, m2, after: last().length };
});
console.log('told      : at boot', r.atBoot, '| on ask', r.asked - r.atBoot, '| kept', r.kept, JSON.stringify(r.name), '| picture', r.thumb, '| machines', r.machines, 'of', r.m0);
console.log('answered  : wipe ->', r.m1, '| open ->', r.m2, '| forget ->', r.after, 'left');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = r.atBoot >= 1 && r.atBoot <= 3 && r.asked === r.atBoot + 1 && r.kept === 1 && r.name === 'from the studio' && r.thumb && r.machines === r.m0
  && r.m1 < r.m0 && r.m2 === r.m0 && r.after === 0 && errs.length === 0;
if (!ok) console.log('FAIL: the runs bridge');
process.exit(ok ? 0 : 1);
