// Stand on a face of Crystal Works and look across it: FACE=index OUT=prefix node _flagface.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 120 && !(await p.evaluate(() => !!(window.__factory && window.__game)).catch(() => false)); i++) await wait(500);
await wait(2500); await p.keyboard.press('Space'); await wait(2500);
const F = +(process.env.FACE || 2);
await p.evaluate((F) => { const f = window.__factory, P = f.player, fc = f.FACES[F], H = f.HALF, o = +(window.__offU || 0.25);
  P.pos.set ? P.pos.set(fc.n[0] * (H + 1.0) - fc.u[0] * H * o, fc.n[1] * (H + 1.0) - fc.u[1] * H * o, fc.n[2] * (H + 1.0) - fc.u[2] * H * o) : (P.pos = [fc.n[0] * (H + 1), fc.n[1] * (H + 1), fc.n[2] * (H + 1)]);
  P.face = F; if (P.up && P.up.set) P.up.set(...fc.n); if (P.fwd && P.fwd.set) P.fwd.set(...fc.u); P.vy = 0; }, F);
await wait(3500);
await p.screenshot({ path: `${process.env.OUT}_f${F}.jpg`, type: 'jpeg', quality: 85 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'ok');
await b.close();
