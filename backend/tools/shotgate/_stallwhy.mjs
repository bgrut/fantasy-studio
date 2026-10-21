// Why does a studio build stop drawing? Replays fbeat's reveal, weather and
// sound steps, logs every frame gap over 150 ms with the WebGL work queued
// just before it (program links, texture uploads by size, buffer uploads) and
// the step markers, then times the idle cue.
//   J=<job> | URL=...   [RUNS=n]   node _stallwhy.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const RUNS = +(process.env.RUNS || 1);
const hook = () => {
  const T = window.__stall = { ev: [], gaps: [], links: 0, tex: 0 };
  const mark = (k, v) => { T.ev.push([Math.round(performance.now()), k, v]); if (!/^(link|tex|texsub|store|mip|read|tex3d|toDataURL)$/.test(k)) console.timeStamp('MARK ' + k + ' ' + (v ?? '')); };
  T.mark = mark;
  const wrap = (proto, name, fn) => { const o = proto[name]; proto[name] = function (...a) { fn.call(this, a); return o.apply(this, a); }; };
  for (const P of [WebGL2RenderingContext.prototype]) {
    wrap(P, 'linkProgram', () => { T.links++; mark('link', T.links); });
    wrap(P, 'texImage2D', a => { const s = a.find(x => x && (x.width || x.videoWidth)); const w = s ? (s.width || s.videoWidth) + 'x' + (s.height || s.videoHeight) : (a[3] + 'x' + a[4]); mark('tex', w); });
    wrap(P, 'texSubImage2D', a => mark('texsub', a.length));
    wrap(P, 'texImage3D', a => mark('tex3d', a[3] + 'x' + a[4] + 'x' + a[5]));
    wrap(P, 'texStorage2D', a => mark('store', a[3] + 'x' + a[4]));
    wrap(P, 'readPixels', a => mark('read', a[2] + 'x' + a[3]));
    wrap(P, 'generateMipmap', () => mark('mip', 1));
  }
  const oc = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (...a) { mark('toDataURL', this.width + 'x' + this.height); return oc.apply(this, a); };
  const desc = n => n ? (n.id ? '#' + n.id : (n.tagName || '?').toLowerCase() + (n.className && typeof n.className === 'string' ? '.' + n.className.split(' ').join('.') : '')) + (n.parentElement && !n.id ? '<' + (n.parentElement.id || n.parentElement.tagName.toLowerCase()) : '') : '?';
  const seen = new Map();
  addEventListener('DOMContentLoaded', () => new MutationObserver(ms => {
    for (const m of ms) {
      const n = m.type === 'characterData' ? m.target.parentElement : m.target;
      if (!n || n.id === 'nitem' || n.id === 'ore' || n.id === 'rate') continue;
      const k = desc(n) + (m.type === 'attributes' ? ' @' + m.attributeName + '=' + String(n.getAttribute(m.attributeName)).slice(0, 60) : ' ' + m.type);
      const t = performance.now();
      if (seen.has(k) && t - seen.get(k) < 2000) continue; seen.set(k, t);
      T.ev.push([Math.round(t), 'dom', k]); console.timeStamp('DOM ' + k);
    }
  }).observe(document.body, { subtree: true, attributes: true, childList: true, characterData: true }));
  let last = performance.now();
  const f = () => { const t = performance.now(); if (t - last > 150) T.gaps.push([Math.round(last), Math.round(t - last)]); last = t; requestAnimationFrame(f); };
  requestAnimationFrame(f);
};
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let run = 0; run < RUNS; run++) {
  const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760', '--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
  // the GPU process's own CPU time, from the OS: driver threads that Chrome's tracer cannot see
  const sys = await b.target().createCDPSession();
  const cpuLog = []; let cpuOn = true, prevCpu = null;
  const tW0 = Date.now();
  (async () => { while (cpuOn) { try { const { processInfo } = await sys.send('SystemInfo.getProcessInfo');
      const g = processInfo.filter(x => x.type === 'gpu').reduce((a, x) => a + x.cpuTime, 0);
      const r = processInfo.filter(x => x.type === 'renderer').reduce((a, x) => a + x.cpuTime, 0);
      const t = Date.now(); if (prevCpu) cpuLog.push([t - tW0, Math.round((g - prevCpu.g) / ((t - prevCpu.t) / 1000) * 100), Math.round((r - prevCpu.r) / ((t - prevCpu.t) / 1000) * 100)]);
      prevCpu = { g, r, t }; } catch (e) {} await new Promise(r => setTimeout(r, 250)); } })();
  await p.evaluateOnNewDocument(hook);
  const CATS = process.env.LIGHT ? ['devtools.timeline', 'toplevel', 'gpu', 'skia', 'disabled-by-default-skia.shaders', 'disabled-by-default-skia.gpu', 'disabled-by-default-devtools.timeline'] : ['toplevel', 'gpu', 'viz', 'cc', 'benchmark', 'audio', 'media', 'blink', 'v8', 'ipc', 'mojom', 'scheduler', 'disabled-by-default-gpu.service', 'disabled-by-default-gpu.device', 'disabled-by-default-viz.gpu_composite_time', 'disabled-by-default-devtools.timeline', 'devtools.timeline', 'loading', 'base', 'renderer.scheduler', 'gpu.capture', 'disabled-by-default-cc.debug.scheduler.frames', 'disabled-by-default-toplevel.flow', 'skia', 'skia.gpu', 'disabled-by-default-skia', 'disabled-by-default-skia.gpu', 'disabled-by-default-skia.shaders', 'cc.debug', 'disabled-by-default-cc.debug'];
  const TRACE = process.env.TRACE ? process.env.TRACE.replace('.json', '_' + run + '.json') : null;
  if (TRACE && process.env.TRACEALL) await p.tracing.start({ path: TRACE, categories: CATS });
  await p.goto(URL + '?fresh=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
  for (let k = 0; k < 60; k++) { if (await p.evaluate(() => typeof window.__game === 'object')) break; await wait(200); }
  await p.evaluate(() => __stall.mark('booted'));
  await wait(4700);
  await p.evaluate(() => __stall.mark('handoff ' + document.getElementById('title').classList.contains('on')));
  await p.evaluate(async () => {
    const F = window.__factory; F.addCores(20);
    for (let k = 0; k < F.WORLDS.length; k++) { if (k !== F.worldIdx) F.travelTo(k); F.endIntro(); F.player.face = 1; __stall.mark('world', k); await new Promise(r => setTimeout(r, 2200)); }
  });
  if (TRACE && !process.env.TRACEALL) await p.tracing.start({ path: TRACE, categories: CATS });
  const r = await p.evaluate(async (NOCLICK, NOBELTS, MODE, EARLYG) => {
    const F = window.__factory, f = () => window.__game.facts();
    if (EARLYG) { __stall.mark('earlyG'); dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyG', key: 'g' })); await new Promise(r => setTimeout(r, 3000)); }
    __stall.mark('click');
    if (MODE === 'nolock') HTMLCanvasElement.prototype.requestPointerLock = function () { __stall.mark('lock stubbed'); return Promise.resolve(); };
    document.addEventListener('pointerlockchange', () => __stall.mark('pointerlockchange ' + !!document.pointerLockElement));
    document.addEventListener('pointerlockerror', () => __stall.mark('pointerlockerror'));
    if (MODE === 'audio') F.audioStart();
    else if (MODE === 'lock') { F.audioStart(); await new Promise(r => setTimeout(r, 3000)); __stall.mark('lockclick'); window.__renderer.domElement.dispatchEvent(new MouseEvent('click', { bubbles: true })); }
    else if (!NOCLICK) window.__renderer.domElement.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    __stall.mark('locked ' + (document.pointerLockElement === window.__renderer.domElement));
    await new Promise(r => setTimeout(r, 400));
    __stall.mark('belts');
    const TY = F.TYPES;
    if (!NOBELTS) for (let i = 4; i < Math.min(F.N - 4, 30); i++) if (F.cells[0][i][4].t === TY.EMPTY) F.place(0, i, 4, TY.BELT, 0);
    for (let k = 0; k < 3; k++) F.step();
    await new Promise(r => setTimeout(r, 1200));
    __stall.mark('sold'); F.sfxSold(F.TYPES.INGOT);
    dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyM' })); await new Promise(r => setTimeout(r, 100));
    dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyM' }));
    if (f().tutorial) { dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyG', key: 'g' })); await new Promise(r => setTimeout(r, 300)); }
    const before = f().idleNudges, fr0 = window.__renderer.info.render.frame;
    __stall.mark('idleAt'); F.idleAt(95); const t0 = performance.now();
    for (let k = 0; k < 80 && f().idleNudges === before; k++) await new Promise(r => setTimeout(r, 125));
    __stall.mark('nudged');
    return { ms: Math.round(performance.now() - t0), frames: window.__renderer.info.render.frame - fr0, nudged: f().idleNudges - before };
  }, !!process.env.NOCLICK, !!process.env.NOBELTS, process.env.MODE || '', !!process.env.EARLYG);
  await wait(1500);
  if (TRACE) await p.tracing.stop();
  const T = await p.evaluate(() => ({ ev: __stall.ev, gaps: __stall.gaps, links: __stall.links }));
  const T0 = await p.evaluate(() => performance.timeOrigin);
  console.log(`origin ${T0}`);
  cpuOn = false;
  const wall0 = await p.evaluate(() => Date.now() - performance.now());
  const LK = T.ev.filter(e => /pointerlock|stubbed/.test(e[1])).map(e => e[1]).join(',');
  console.log(`run ${run}: [${LK}] idle cue after ${r.ms} ms (${r.frames} frames, +${r.nudged}) | ${T.links} links | gaps ${T.gaps.length}`);
  for (const [at, dur] of T.gaps) {
    if (dur < 250) continue;
    // what the page queued in the 300 ms before the gap opened
    const pre = T.ev.filter(e => e[0] >= at - 300 && e[0] <= at + 5);
    const sum = {};
    for (const e of pre) { const k = e[1] === 'tex' || e[1] === 'store' || e[1] === 'toDataURL' || e[1] === 'read' || e[1] === 'tex3d' ? e[1] + ':' + e[2] : e[1]; sum[k] = (sum[k] || 0) + 1; }
    const steps = T.ev.filter(e => e[0] <= at && !/^(link|tex|texsub|store|mip|read|tex3d|toDataURL)$/.test(e[1])).slice(-1)[0];
    const w0 = wall0 + at - tW0, w1 = w0 + dur;
    const inGap = cpuLog.filter(c => c[0] > w0 + 250 && c[0] <= w1);
    const cpuStr = inGap.length ? ' | gpu proc cpu% ' + inGap.map(c => c[1]).join(',') + ' | renderer ' + inGap.map(c => c[2]).join(',') : '';
    console.log(`  gap ${String(dur).padStart(5)} ms at ${at}${cpuStr} after [${steps ? steps[1] + ' ' + (steps[2] ?? '') : '-'}] queued: ${JSON.stringify(sum)}`);
  }
  if (process.env.DUMP) console.log(JSON.stringify(T.ev.filter(e => !/^(texsub)$/.test(e[1]))));
  await b.close();
}
