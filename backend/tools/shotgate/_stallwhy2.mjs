// What blocks a generated game's first seconds of play: J=job_N [CLICK=ms] node _stallwhy2.mjs
// Wraps the WebGL calls that can block on the driver (compile, link, the program and
// shader queries) before the page runs, times each, remembers which program it was for,
// records every long frame, then names the programs (three's name + cacheKey) behind
// the slow calls.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.evaluateOnNewDocument(() => {
  const T = window.__gl = { ev: [], frames: [], ids: new WeakMap(), n: 0, mark: '' };
  const idOf = (o) => { if (!o) return -1; if (!T.ids.has(o)) T.ids.set(o, ++T.n); return T.ids.get(o); };
  const wrap = (proto, name) => { const f = proto[name]; if (!f) return;
    proto[name] = function (...a) { const t0 = performance.now(); const r = f.apply(this, a); const dt = performance.now() - t0;
      if (dt > 15) T.ev.push([Math.round(t0), Math.round(dt), name, idOf(a[0]), T.mark]); return r; }; };
  for (const P of [WebGL2RenderingContext.prototype]) for (const n of ['getProgramInfoLog', 'getProgramParameter', 'getShaderInfoLog', 'getShaderParameter',
    'linkProgram', 'compileShader', 'getUniformLocation', 'getActiveUniform', 'getAttribLocation', 'useProgram', 'texImage2D', 'texSubImage2D', 'bufferData', 'drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced', 'readPixels', 'finish', 'getError', 'clientWaitSync']) wrap(P, n);
  window.__progId = idOf;
  let last = 0; const f = (t) => { if (last && t - last > 100) T.frames.push([Math.round(last), Math.round(t - last), T.mark]); last = t; requestAnimationFrame(f); }; requestAnimationFrame(f);
});
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html${process.env.Q || ""}`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
const tReady = await p.evaluate(() => Math.round(performance.now()));
await w(+(process.env.CLICK || 4000));
await p.evaluate(() => { window.__gl.mark = 'play'; window.__gl.tStart = Math.round(performance.now()); });
await p.click('#startbtn').catch(() => {});
await w(22000);
const r = await p.evaluate(() => {
  const T = window.__gl, R = window.__renderer, byId = new Map();
  for (const q of R.info.programs) byId.set(window.__progId(q.program), { name: q.name, key: String(q.cacheKey).slice(0, 90), usedTimes: q.usedTimes });
  const play = T.ev.filter(e => e[4] === 'play');
  const sum = {}; for (const e of play) { const k = e[2]; sum[k] = (sum[k] || 0) + e[1]; }
  const progCost = new Map(); for (const e of play) if (e[3] > 0) progCost.set(e[3], (progCost.get(e[3]) || 0) + e[1]);
  const top = [...progCost.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14).map(([id, ms]) => ({ ms: Math.round(ms), id, prog: byId.get(id) || null }));
  return { tStart: T.tStart, warm: window.__warmMs, rewarms: window.__rewarms, programs: R.info.programs.length, framesPlay: T.frames.filter(f => f[2] === 'play'), framesBefore: T.frames.filter(f => f[2] !== 'play').slice(-6),
           callTotalsPlay: sum, slowestCallsPlay: play.sort((a, b) => b[1] - a[1]).slice(0, 12), topPrograms: top };
});
console.log('ready at', tReady, 'start at', r.tStart, 'warm', JSON.stringify(r.warm), 'rewarms', r.rewarms, 'programs', r.programs);
console.log('long frames before play', JSON.stringify(r.framesBefore));
console.log('long frames in play', JSON.stringify(r.framesPlay));
console.log('blocking time by call (play)', JSON.stringify(r.callTotalsPlay));
console.log('slowest calls (play) [t, ms, call, prog]', JSON.stringify(r.slowestCallsPlay));
for (const t of r.topPrograms) console.log('  ' + String(t.ms).padStart(6) + ' ms  #' + t.id + '  ' + (t.prog ? t.prog.name + ' | ' + t.prog.key : '(not a three program: shader or texture)'));
await b.close();
