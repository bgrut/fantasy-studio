// Hold W (and Shift) for a while, then shoot: a ride or slide seen in motion.   J=job_N OUT=prefix [KEYS=KeyW,ShiftLeft] [HOLD=ms] node _slideprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await p.click('#startbtn').catch(() => {}); await wait(3000);
if (process.env.PRE) console.log('pre', JSON.stringify(await p.evaluate(src => { try { return eval(src); } catch (e) { return 'PRE ' + e.message; } }, process.env.PRE)));
const keys = (process.env.KEYS || 'KeyW,ShiftLeft').split(',');
const p0 = await p.evaluate(() => window.__game.pos());
for (const k of keys) await p.keyboard.down(k);
await wait(+(process.env.HOLD || 2500));
await p.screenshot({ path: `${process.env.OUT}_0.jpg`, type: 'jpeg', quality: 85 });
const p1 = await p.evaluate(() => window.__game.pos());
for (const k of keys) await p.keyboard.up(k);
if (process.env.EXTRA) console.log('extra', JSON.stringify(await p.evaluate(src => { try { return eval(src); } catch (e) { return 'EVAL ' + e.message; } }, process.env.EXTRA)));
console.log('moved', Math.hypot(p1[0] - p0[0], p1[2] - p0[2]).toFixed(1), 'm', errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
