// Crystal Works, every face from close orbit, clean. OUT=dir node _flagfaces.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(8000);
const H = Math.abs(await p.evaluate(() => window.__game.facts().player_y)) || 34;
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
if (process.env.PRE) await p.evaluate(src => { try { eval(src); } catch (e) {} }, process.env.PRE);   // PRE='js' before the shots
const S = (process.env.SHOTS || 'top,px,nx,pz,nz,bot,lowpx,lownz').split(',');
const PIN = { top: { pos: [0.3, H * 2.2, 0.4], look: [0, 0, 0] },
  px: { pos: [H * 2.1, H * 0.3, H * 0.2], look: [0, 0, 0] }, nx: { pos: [-H * 2.1, H * 0.3, -H * 0.2], look: [0, 0, 0] },
  pz: { pos: [H * 0.2, H * 0.3, H * 2.1], look: [0, 0, 0] }, nz: { pos: [-H * 0.2, H * 0.3, -H * 2.1], look: [0, 0, 0] },
  bot: { pos: [0.3, -H * 2.2, 0.4], look: [0, 0, 0] },
  lowpx: { pos: [H + 2.2, H * 0.4, H * 0.5], look: [H, -H * 0.3, -H * 0.4] }, lownz: { pos: [-H * 0.5, H * 0.4, -H - 2.2], look: [H * 0.4, -H * 0.3, -H] } };
for (const n of S) { if (!n.startsWith('keep')) await p.evaluate(pn => { window.__camPin = pn; }, PIN[n] || null); await w(2200);   // 'play': the game's own camera; 'keep*': the pin PRE set
  await p.screenshot({ path: `${process.env.OUT}/${n}.jpg`, type: 'jpeg', quality: 85 }); }
console.log('ok', H, JSON.stringify(await p.evaluate(() => window.__game.stats())));
await b.close();
