// README screenshots: each game started, the HUD hidden, shot from a pinned
// camera (or the game's own), 1600x900.   SHOTS=shots.json OUT=dir node _readmeshots.mjs
// shots.json: [{ "name": "ant-kitchen", "job": 1923, "pin": "<js expr -> {pos,look}> or null", "wait": 6000, "keys": "KeyW", "hold": 0 }]
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const list = JSON.parse(fs.readFileSync(process.env.SHOTS, 'utf8'));
const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (const s of list) {
  if (only && !only.includes(s.name)) continue;
  const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 120)));
  try {
    const url = s.url || `http://127.0.0.1:8789/games/job_${s.job}/dist/index.html`;
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await wait(s.boot || 10000);
    if (!s.url) { await p.click('#startbtn').catch(() => {}); }
    await wait(2500);
    if (s.keys) { await p.keyboard.down(s.keys); await wait(s.hold || 2500); await p.keyboard.up(s.keys); }
    await wait(s.wait || 5000);
    if (s.pin) await p.evaluate((src) => { window.__camPin = eval(src); }, s.pin);
    // the world alone: every overlay hidden
    await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(#app):not(script):not(style){visibility:hidden !important} #app > *:not(canvas){visibility:hidden !important}'; document.head.appendChild(st); });
    await wait(s.pin ? 2500 : 900);
    await p.screenshot({ path: `${process.env.OUT}/${s.name}.jpg`, type: 'jpeg', quality: 90 });
    console.log('shot', s.name, errs.length ? 'ERR ' + errs[0] : '');
  } catch (e) { console.log('fail', s.name, e.message.slice(0, 120)); }
  await p.close();
}
await b.close();
