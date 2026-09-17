// The performance pass, on the card the player has. Headless Chrome on the
// d3d11 ANGLE backend reaches the real GPU on this machine (gpuprobe.mjs shows
// which renderer a launch gets); with the frame-rate limit off, the frame rate
// is raw throughput rather than the vsync cap, so the headroom is visible.
//
//   node perfpass.mjs                              the demo on :8790, written to flagship/PERF.md
//   URL=http://127.0.0.1:8789/games/job_N/dist/ node perfpass.mjs --no-write
//
// Six phases of forty seconds each on the demo: the fresh start, a built
// factory, the overhead, the works' minute, the same factory without the
// occlusion pass, and the performance tier. Every phase reports the average
// frame rate, the median and 95th-percentile frame times, the worst frame,
// draw calls and triangles.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const WRITE = !process.argv.includes('--no-write');
const SECS = +(process.env.SECS || 40);
const q = URL.includes('?') ? '&' : '?';

const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0, 200)));

const sleep = ms => new Promise(r => setTimeout(r, ms));
const open = async (extra) => {
  await p.goto(URL + q + 'nointro=1' + (extra || ''), { waitUntil: 'domcontentloaded', timeout: 90000 });
  await sleep(6000);
  await p.evaluate(() => { document.getElementById('tutor')?.classList.remove('on'); window.__factory.ageHints(); });
};
// frame deltas for a stretch of seconds, from inside the page
const sample = async (secs) => p.evaluate(async (secs) => {
  const d = [];
  let last = performance.now();
  await new Promise(done => {
    const tick = (t) => { d.push(t - last); last = t; if (t - t0 < secs * 1000) requestAnimationFrame(tick); else done(); };
    const t0 = performance.now();
    requestAnimationFrame(tick);
  });
  d.shift();
  d.sort((a, b) => a - b);
  const at = k => d[Math.min(d.length - 1, Math.floor(d.length * k))];
  const mean = d.reduce((a, b) => a + b, 0) / d.length;
  const st = window.__game.stats();
  const gl = window.__renderer.getContext();
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return { frames: d.length, fps: +(1000 / mean).toFixed(1), p50: +at(0.5).toFixed(2), p95: +at(0.95).toFixed(2), worst: +d[d.length - 1].toFixed(1),
           calls: st.calls, tris: st.tris, dpr: window.devicePixelRatio, w: innerWidth, h: innerHeight,
           gpu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
           tier: (location.search.match(/[?&]q=(\w+)/) || [])[1] || 'ultra', ao: !/[?&]ao=0/.test(location.search) };
}, secs);

const rows = [];
const phase = async (name, note) => {
  const r = await sample(SECS);
  rows.push(Object.assign({ name, note }, r));
  console.log(name.padEnd(22), 'fps', String(r.fps).padStart(6), '| p50', String(r.p50).padStart(6), 'ms | p95', String(r.p95).padStart(6), 'ms | worst', String(r.worst).padStart(6), 'ms | calls', String(r.calls).padStart(4), '| tris', r.tris.toLocaleString());
  return r;
};

// 1. the fresh start
await open('&fresh=1');
await phase('fresh start', 'the starter line, first person');

// 2. a built factory: belts across the top face, a dozen machines, three hubs
const built = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES; F.addValue(20000);
  let belts = 0, machines = 0;
  for (let j = 4; j < F.N - 4; j += 3) for (let i = 3; i < F.N - 3; i++) if (F.cells[0][i][j].t === TY.EMPTY && F.place(0, i, j, TY.BELT, 0)) belts++;
  const kinds = [TY.SMELTER, TY.FORGE, TY.SPLITTER, TY.HUB, TY.SMELTER, TY.ASSEMBLER];
  let k = 0;
  for (let j = 5; j < F.N - 5; j += 6) for (let i = 4; i < F.N - 4; i += 7) if (F.cells[0][i][j].t === TY.EMPTY && F.place(0, i, j, kinds[k++ % kinds.length], 0)) machines++;
  for (let f = 1; f < 6; f++) for (let i = 4; i < F.N - 4; i += 2) if (F.cells[f][i][8].t === TY.EMPTY && F.place(f, i, 8, TY.BELT, 0)) belts++;
  await new Promise(r => setTimeout(r, 1500));
  return { belts, machines };
});
console.log('built                 ', built.belts, 'belts,', built.machines, 'machines placed');
await phase('built factory', built.belts + ' belts and ' + built.machines + ' machines');

// 3. the overhead
await p.keyboard.press('Tab'); await sleep(1500);
await phase('overhead', 'TAB, the planning screen');
await p.keyboard.press('Tab'); await sleep(800);

// 4. the works' minute
await p.evaluate(() => window.__factory.playWorks()); await sleep(1500);
await phase('the works minute', 'sparks, seam waves, racing sweeps');

// 5. the same factory without the occlusion pass (the autosave carries the factory)
await open('&ao=0');
await phase('no occlusion', 'the built factory, ?ao=0');

// 6. the performance tier
await open('&q=performance');
await phase('performance tier', 'the built factory, ?q=performance');

console.log('errors                ', errs.length ? errs.join(' | ') : 'none');
await b.close();

const gpu = rows[0].gpu;
const md = [
  '# Performance pass',
  '',
  'Measured on ' + new Date().toISOString().slice(0, 10) + ' with `backend/tools/shotgate/perfpass.mjs`: headless Chrome on the d3d11 ANGLE backend,',
  'frame-rate limit off, 1280 by 760 at device pixel ratio 1, forty seconds a phase.',
  '',
  'GPU: `' + gpu + '`',
  '',
  '| phase | what | fps | p50 ms | p95 ms | worst ms | draw calls | triangles | occlusion | tier |',
  '|---|---|---:|---:|---:|---:|---:|---:|---|---|',
  ...rows.map(r => '| ' + r.name + ' | ' + r.note + ' | ' + r.fps + ' | ' + r.p50 + ' | ' + r.p95 + ' | ' + r.worst + ' | ' + r.calls + ' | ' + r.tris.toLocaleString() + ' | ' + (r.ao ? 'on' : 'off') + ' | ' + r.tier + ' |'),
  '',
  'The frame rate is raw throughput with the limit off; a player sees it capped at the display rate. The 95th-percentile frame time is the number that matters for smoothness: under 16.7 ms is a solid sixty.',
  '',
];
if (WRITE) {
  const out = path.resolve(HERE, '../../../flagship/PERF.md');
  // the reading under the table is written by hand and survives a rerun
  let reading = '';
  try { const old = fs.readFileSync(out, 'utf-8'); const k = old.indexOf('## Reading'); if (k >= 0) reading = old.slice(k); } catch (e) {}
  fs.writeFileSync(out, md.join('\n') + reading, 'utf-8');
  console.log('written               ', out);
}
process.exit(errs.length ? 1 : 0);
