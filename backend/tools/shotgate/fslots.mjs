// A save you can name: keep the run through the panel, reload, wipe, open it
// back, forget it. The kept run carries a picture and a machine count.
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
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 6000));
const count = `(() => { const F = window.__factory, TY = F.TYPES; let n = 0;
  for (let f = 0; f < 6; f++) for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) { const t = F.cells[f][i][j].t; if (t !== TY.EMPTY && t !== TY.NODE && t !== TY.PROP) n++; }
  return n; })()`;
const kept = await p.evaluate(async (count) => {
  const F = window.__factory, TY = F.TYPES; let spot = null;
  for (let i = 3; i < F.N - 3 && !spot; i++) for (let j = 3; j < F.N - 3 && !spot; j++) if (F.cells[0][i][j].t === TY.EMPTY) spot = [i, j];
  F.addValue(500); F.place(0, spot[0], spot[1], TY.SMELTER, 0);
  await new Promise(r => setTimeout(r, 500));
  const m0 = eval(count);
  const inp = document.querySelector('#runs .keep input');
  inp.value = 'the first works';
  // a hotkey typed into the name box must not pick a tool
  const before = document.querySelector('.tool.on') && document.querySelector('.tool.on').dataset.tool;
  inp.dispatchEvent(new KeyboardEvent('keydown', { key: '3', code: 'Digit3', bubbles: true }));
  const after = document.querySelector('.tool.on') && document.querySelector('.tool.on').dataset.tool;
  document.querySelector('#runs .keep span').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 900));
  const runs = F.readRuns();
  return { m0, kept: runs.length, name: runs[0] && runs[0].name, thumb: runs[0] && runs[0].thumb ? runs[0].thumb.length : 0,
           machines: runs[0] && runs[0].machines, rows: document.querySelectorAll('#runs .run').length, toolHeld: before === after };
}, count);
console.log('kept      :', JSON.stringify(kept));
// the list survives a reload; then wipe, open, forget through the panel
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 5000));
const back = await p.evaluate(async (count) => {
  const F = window.__factory;
  const listed = F.readRuns().length, rows = document.querySelectorAll('#runs .run').length;
  F.wipe(); await new Promise(r => setTimeout(r, 400));
  const m1 = eval(count);
  document.querySelector('#runs .run i[data-open]').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 600));
  const m2 = eval(count);
  const fg = document.querySelector('#runs .run i[data-forget]');
  fg.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  const armed = fg.textContent;
  fg.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 300));
  let orphan = null; try { orphan = localStorage.getItem(F.RUNS_KEY); } catch (e) {}
  return { listed, rows, m1, m2, armed, after: F.readRuns().length, rowsAfter: document.querySelectorAll('#runs .run').length, index: orphan };
}, count);
console.log('back      :', JSON.stringify(back));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = kept.kept === 1 && kept.name === 'the first works' && kept.thumb > 1500 && kept.machines === kept.m0 && kept.rows === 1 && kept.toolHeld
  && back.listed === 1 && back.rows === 1 && back.m1 < kept.m0 && back.m2 === kept.m0
  && back.armed === 'sure?' && back.after === 0 && back.rowsAfter === 0
  && errs.length === 0;
if (!ok) console.log('FAIL: a save you can name');
process.exit(ok ? 0 : 1);
