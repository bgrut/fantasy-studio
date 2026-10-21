// What the page is doing in a long frame of play: J=job_N [CLICK=ms] [SPAN=ms] node _playprof.mjs
// CPU-profiles the first seconds after Start and prints self time by function and file.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
await w(+(process.env.CLICK || 4000));
const cdp = await p.target().createCDPSession();
await cdp.send('Profiler.enable'); await cdp.send('Profiler.setSamplingInterval', { interval: 2000 }); await cdp.send('Profiler.start');
await p.click('#startbtn').catch(() => {});
await w(+(process.env.SPAN || 15000));
const { profile } = await cdp.send('Profiler.stop');
const byId = new Map(profile.nodes.map(n => [n.id, n])); const self = new Map();
const dts = profile.timeDeltas; profile.samples.forEach((id, i) => { const n = byId.get(id); const cf = n.callFrame;
  const k = (cf.functionName || '(anon)') + ' ' + cf.url.split('/').pop() + ':' + cf.lineNumber; self.set(k, (self.get(k) || 0) + (dts[i] || 0) / 1000); });
const tot = [...self.values()].reduce((a, b) => a + b, 0);
console.log('total ms', Math.round(tot));
for (const [k, v] of [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 25)) console.log(String(Math.round(v)).padStart(7), k);
// inclusive: walk parents
const parent = new Map(); for (const n of profile.nodes) for (const c of (n.children || [])) parent.set(c, n.id);
const incl = new Map(); profile.samples.forEach((id, i) => { const seen = new Set(); let cur = id; while (cur) { const cf = byId.get(cur).callFrame; const k = (cf.functionName || '(anon)') + ' ' + cf.url.split('/').pop() + ':' + cf.lineNumber; if (!seen.has(k)) { seen.add(k); incl.set(k, (incl.get(k) || 0) + (dts[i] || 0) / 1000); } cur = parent.get(cur); } });
console.log('-- inclusive (game.js only)');
for (const [k, v] of [...incl.entries()].filter(([k]) => /game\.js|proc|places|design/.test(k)).sort((a, b) => b[1] - a[1]).slice(0, 25)) console.log(String(Math.round(v)).padStart(7), k);
await b.close();
