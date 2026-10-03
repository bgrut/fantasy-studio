// MOTION MATCHING LAB DRIVER (2026-10-03): opens mmlab.html (served from a job's
// dist root with proc/mm.js and mm/ beside it), prints the per-phase numbers
// (trunk lean, planted-foot slide, pops, jumps, takes) and saves the frame strip.
//   Q='f=<file.glb>&walk=2.4&run=6.4[&dbg=<phase>]' OUT=mm.png node mmlab.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1920, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await p.goto('http://127.0.0.1:8791/mmlab.html?' + (process.env.Q || 'f=zz_ranger.glb'));
await p.waitForFunction(() => window.__mm, { timeout: 120000 }).catch(() => {});
console.log(JSON.stringify(await p.evaluate(() => window.__mm), null, 1), errs.join('|'));
await p.screenshot({ path: process.env.OUT || 'mm.png' }); await b.close();
