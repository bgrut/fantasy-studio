// Where do long frames go? Loads a page, waits W ms, then CPU-profiles 8 s and
// prints the heaviest functions by self time, and the long frames seen.
//   J=<job> | URL=...   [Q=?query] [W=ms] [STEPS=fbeat]   node _stallprof.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
await p.goto(URL + (process.env.Q || '?fresh=1'), { waitUntil: 'domcontentloaded', timeout: 90000 });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__factory && window.__game))) break; await wait(500); }
await wait(+(process.env.W || 20000));
const s = await p.target().createCDPSession();
await s.send('Profiler.enable'); await s.send('Profiler.setSamplingInterval', { interval: 500 }); await s.send('Profiler.start');
const frames = await p.evaluate(() => new Promise(res => { const out = []; let last = performance.now(); const t0 = last; const f = () => { const t = performance.now(); if (t - last > 120) out.push([Math.round(last - t0), Math.round(t - last)]); last = t; if (t - t0 < 8000) requestAnimationFrame(f); else res(out); }; requestAnimationFrame(f); }));
const { profile } = await s.send('Profiler.stop');
const byId = new Map(profile.nodes.map(n => [n.id, n])), self = new Map();
const dts = profile.timeDeltas; profile.samples.forEach((id, k) => { const n = byId.get(id); const key = (n.callFrame.functionName || '(anon)') + ' ' + (n.callFrame.url || '').split('/').pop() + ':' + n.callFrame.lineNumber; self.set(key, (self.get(key) || 0) + (dts[k] || 0)); });
console.log('long frames', JSON.stringify(frames));
[...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 25).forEach(([k, v]) => console.log((v / 1000).toFixed(0).padStart(6) + ' ms  ' + k));
await b.close();
