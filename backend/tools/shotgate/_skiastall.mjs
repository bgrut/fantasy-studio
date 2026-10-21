// Are a generated game's frozen frames Chrome's own shaders (Skia painting the HUD) rather
// than the game's? J=job_N [CLICK=ms] [SPAN=ms] node _skiastall.mjs
// Traces the first seconds of play with the skia and gpu categories, then lists every
// long frame and the slow shader builds inside it, with the thread that waited on each and
// the DOM changes just before (the HUD state that asked for the new shader).
import puppeteer from 'puppeteer-core';
import fs from 'fs';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.evaluateOnNewDocument(() => {
  const T = window.__sk = { frames: [], dom: [] };
  let last = 0; const f = (t) => { if (last && t - last > 150) T.frames.push([Math.round(last), Math.round(t - last)]); last = t; requestAnimationFrame(f); }; requestAnimationFrame(f);
  const desc = n => n ? (n.id ? '#' + n.id : (n.tagName || '?').toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.split(' ').join('.') : '')) : '?';
  addEventListener('DOMContentLoaded', () => new MutationObserver(ms => { for (const m of ms) {
    const n = m.type === 'characterData' ? m.target.parentElement : m.target;
    T.dom.push([Math.round(performance.now()), desc(n) + (m.type === 'attributes' ? ' @' + m.attributeName : ' ' + m.type) + (m.addedNodes && m.addedNodes.length ? ' +' + desc(m.addedNodes[0]) : '')]);
    if (T.dom.length > 4000) T.dom.splice(0, 1000); } }).observe(document.body, { subtree: true, attributes: true, childList: true, characterData: true }));
});
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
await w(+(process.env.CLICK || 9000));
const TRACE = (process.env.TEMP || '.') + '/skiastall_trace.json';
await p.tracing.start({ path: TRACE, categories: ['devtools.timeline', 'toplevel', 'gpu', 'skia', 'disabled-by-default-skia.shaders'] });
const tClick = await p.evaluate(() => Math.round(performance.now()));
await p.click('#startbtn').catch(() => {});
await w(+(process.env.SPAN || 16000));
await p.tracing.stop();
const T = await p.evaluate(() => window.__sk);
await b.close();
const tr = JSON.parse(fs.readFileSync(TRACE, 'utf8')); fs.unlinkSync(TRACE);
const ev = tr.traceEvents || tr;
const threads = new Map(); for (const e of ev) if (e.ph === 'M' && e.name === 'thread_name') threads.set(e.pid + ':' + e.tid, e.args.name);
const slow = ev.filter(e => e.ph === 'X' && e.dur > 200000 && /shader|compile|link|program/i.test(e.name))
  .map(e => ({ name: e.name, ms: Math.round(e.dur / 1000), ts: e.ts, thread: threads.get(e.pid + ':' + e.tid) || e.tid }));
// map trace time to page time with the click marker: the first EventDispatch click
const click = ev.find(e => e.name === 'EventDispatch' && e.args && e.args.data && e.args.data.type === 'click');
const off = click ? click.ts / 1000 - tClick : null;
console.log('click at', tClick, 'long frames after click', JSON.stringify(T.frames.filter(f => f[0] + f[1] > tClick)));
for (const s of slow.sort((a, c) => a.ts - c.ts)) {
  const pt = off == null ? null : Math.round(s.ts / 1000 - off);
  const before = pt == null ? [] : T.dom.filter(d => d[0] <= pt && d[0] > pt - 400).map(d => d[1]);
  console.log(String(s.ms).padStart(6) + ' ms  at ' + pt + '  ' + s.name + '  [' + s.thread + ']  dom: ' + [...new Set(before)].slice(-6).join(' | '));
}
if (!slow.length) console.log('no shader build over 200 ms in the trace');
