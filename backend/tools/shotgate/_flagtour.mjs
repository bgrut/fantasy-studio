// Crystal Works from several angles: OUT=prefix [URL=] node _flagtour.mjs
// the first-person opening, the overhead plan (Tab), the worldlet from orbit, low across a
// face at the machines, and a far face; for judging the flagship as a whole picture
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.goto(URL + '?fresh=1&noguide=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(6000);
const shot = async (n) => { await w(1600); await p.screenshot({ path: `${process.env.OUT}_${n}.jpg`, type: 'jpeg', quality: 88 }); };
await shot('fp');
await p.keyboard.press('Tab'); await w(1500); await shot('over'); await p.keyboard.press('Tab'); await w(800);
const info = await p.evaluate(() => { const f = window.__game.facts(); return { y: f.player_y, face: f.player_face }; });
const H = Math.abs(info.y) || 34;
for (const [n, pin] of [['orbit', { pos: [H * 2.2, H * 1.6, H * 2.4], look: [0, 0, 0] }],
                        ['low', { pos: [H * 0.5, H + 3.5, H * 0.75], look: [-H * 0.2, H, -H * 0.3] }],
                        ['edge', { pos: [H + 2, H + 6, H + 2], look: [H * 0.2, H * 0.2, H * 0.2] }]]) {
  await p.evaluate(pn => { window.__camPin = pn; }, pin); await shot(n);
}
await p.evaluate(() => { window.__camPin = null; });
console.log(JSON.stringify(info), errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
