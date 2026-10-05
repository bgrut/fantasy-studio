// The flagship's screen: the play view with the readout and cards, the
// ledger opened with L, and the overhead view (which opens it by itself).
//   [URL=http://127.0.0.1:8790/] OUT=<dir> [Q=creative=1] node hudshot.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', OUT = process.env.OUT || '.', Q = process.env.Q || '';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(URL + (Q ? (URL.includes('?') ? '&' : '?') + Q : ''), { waitUntil: 'domcontentloaded', timeout: 60000 });
await sleep(8000);
await p.keyboard.press('Enter').catch(() => {}); await sleep(3500);
await p.keyboard.press('g').catch(() => {}); await sleep(600);
// a little money so the readout and the wrist have something to say
await p.evaluate(() => { const F = window.__factory; for (let k = 0; k < 30; k++) F.step(); });
await sleep(1500);
await p.screenshot({ path: `${OUT}/hud_1_play.jpg`, type: 'jpeg', quality: 88 });
await p.keyboard.press('l'); await sleep(700);
await p.screenshot({ path: `${OUT}/hud_2_ledger.jpg`, type: 'jpeg', quality: 88 });
await p.keyboard.press('l'); await sleep(500);
await p.keyboard.press('Tab'); await sleep(1600);
await p.screenshot({ path: `${OUT}/hud_3_overhead.jpg`, type: 'jpeg', quality: 88 });
await p.keyboard.press('Tab'); await sleep(900);
const st = await p.evaluate(() => ({ ledger: document.body.classList.contains('ledger'), ro: document.getElementById('ro-ore').textContent,
  ping: document.getElementById('ledgerTab').classList.contains('ping'), hudX: document.getElementById('hud').getBoundingClientRect().x }));
console.log(JSON.stringify(st), JSON.stringify(errs.slice(0, 4)));
await b.close();
