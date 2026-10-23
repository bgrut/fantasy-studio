// How long until a game is ready to start: J=job_N node _boot.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const t0 = Date.now();
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
let ready = null;
for (let i = 0; i < 240; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts)).catch(() => false)) { ready = Date.now() - t0; break; } await new Promise(r => setTimeout(r, 250)); }
console.log(JSON.stringify({ job: process.env.J, ready_ms: ready })); await b.close();
