// Crystal Works for the README: started, every overlay hidden, the held tool put away (clean=1), shot from
// pinned cameras round the worldlet. OUT=dir [URL=] node _flagreadme.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(8000);
const H = Math.abs(await p.evaluate(() => window.__game.facts().player_y)) || 34;
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
for (const [n, pin] of [['cw-orbit', { pos: [H * 1.9, H * 1.35, H * 2.1], look: [0, -H * 0.1, 0] }],
                        ['cw-low', { pos: [H * 0.45, H + 2.6, H * 0.7], look: [-H * 0.25, H + 0.5, -H * 0.35] }],
                        ['cw-edge', { pos: [H + 3, H + 5, H + 3], look: [H * 0.1, H * 0.25, H * 0.1] }],
                        ['cw-machines', { pos: [6, H + 3.2, 7], look: [0, H + 0.8, 0] }]]) {
  await p.evaluate(pn => { window.__camPin = pn; }, pin); await w(2200);
  await p.screenshot({ path: `${process.env.OUT}/${n}.jpg`, type: 'jpeg', quality: 90 });
}
console.log('ok', H);
await b.close();
