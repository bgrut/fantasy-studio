// A hundred belts is a small factory. If detail costs a draw call per part,
// the art pass is a frame-rate pass in the other direction — so this measures
// before anything is added, and guards it afterwards.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
await p.goto(URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

const built = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let belts = 0, miners = 0;
  // a serpentine of belts across the top face, plus some machines
  for (let j = 4; j < Math.min(F.N - 4, 26); j += 2) {
    for (let i = 4; i < Math.min(F.N - 4, 26); i++) {
      if (F.cells[0][i][j].t !== TY.EMPTY) continue;
      if (F.place(0, i, j, TY.BELT, 0)) belts++;
    }
  }
  for (let k = 0; k < 12; k++) {
    const i = 4 + k * 2, j = 3;
    if (i < F.N - 4 && F.cells[0][i][j].t === TY.EMPTY &&
        F.place(0, i, j, TY.SMELTER, 0)) miners++;
  }
  await new Promise(r => setTimeout(r, 1200));
  return { belts, miners };
});

// look at the whole thing from orbit, where everything is on screen at once
await p.evaluate(()=>{ window.__game.inspect(true); });
await new Promise(r=>setTimeout(r,1500));
const frames = await p.evaluate(async () => {
  const t = [];
  let last = performance.now();
  for (let k = 0; k < 90; k++) {
    await new Promise(r => requestAnimationFrame(r));
    const now = performance.now(); t.push(now - last); last = now;
  }
  t.sort((a, b) => a - b);
  return { median: t[45], p90: t[81], stats: window.__game.stats() };
});
console.log('built     :', built.belts, 'belts +', built.miners, 'smelters');
console.log('draw calls:', frames.stats.calls, '| tris', frames.stats.tris,
            '| geometries', frames.stats.geometries);
console.log('frame time:', frames.median.toFixed(1) + 'ms median,',
            frames.p90.toFixed(1) + 'ms p90');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'perf.png' });
await b.close();
// headless swiftshader is slower than real hardware; the guard is on draw
// calls, which is what actually scales with the art
const ok = frames.stats.calls < 320 && frames.p90 < 60 && errs.length === 0;
process.exit(ok ? 0 : 1);
