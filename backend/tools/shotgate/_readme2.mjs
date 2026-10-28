// README shots, with set-ups: each game started, a set-up run in the page (async allowed), keys held
// while shooting, a pinned camera, every overlay hidden. 1600x900.
// SHOTS=shots.json OUT=dir [ONLY=a,b] node _readme2.mjs
// shots.json: [{ "name", "job", "setup": "<async js>", "wait": ms, "hold": ["KeyW"], "holdMs": ms, "pin": "<js expr or null>" }]
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const list = JSON.parse(fs.readFileSync(process.env.SHOTS, 'utf8'));
const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const wait = ms => new Promise(r => setTimeout(r, ms));
// toward-the-goal framing, usable in pins: TG(back, up, ahead, lookUp)
const TG = `window.TG = (back, up, ahead, lookUp) => { const q = window.__game.pos(), g = window.__game.goal() || [q[0], q[2] + 30]; const dx = g[0] - q[0], dz = g[1] - q[2], L = Math.hypot(dx, dz) || 1, ux = dx / L, uz = dz / L;
  return { pos: [q[0] - ux * back, q[1] + up, q[2] - uz * back], look: [q[0] + ux * ahead, q[1] + lookUp, q[2] + uz * ahead] }; };`;
for (const s of list) {
  if (only && !only.includes(s.name)) continue;
  const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 120)));
  try {
    await p.goto(`http://127.0.0.1:8789/games/job_${s.job}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 120000 }).catch(() => {});
    await wait(5000); await p.click('#startbtn').catch(() => {});
    await p.waitForFunction(() => window.__game && !(window.__game.facts && window.__game.facts().intro), { timeout: 30000 }).catch(() => {});
    await wait(s.boot || 4000);
    await p.evaluate(TG);
    if (s.setup) await p.evaluate(async (src) => { await eval('(async () => {' + src + '})()'); }, s.setup);
    await wait(s.wait || 2500);
    if (s.pin) await p.evaluate((src) => { window.__camPin = eval(src); }, s.pin);
    await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(#app):not(script):not(style){visibility:hidden !important} #app > *:not(canvas){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
    for (const k of (s.hold || [])) await p.keyboard.down(k);
    await wait(s.holdMs || 2200);
    await p.screenshot({ path: `${process.env.OUT}/${s.name}.jpg`, type: 'jpeg', quality: 90 });
    for (const k of (s.hold || [])) await p.keyboard.up(k);
    console.log('shot', s.name, errs.length ? 'ERR ' + errs[0] : '');
  } catch (e) { console.log('fail', s.name, e.message.slice(0, 160)); }
  await p.close();
}
await b.close();
