// Hold keys and log the hero's position every half second: J=job_N KEYS=KeyW,Space SECS=8 node _climbprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(3500);
if (process.env.PRE) console.log('pre', JSON.stringify(await p.evaluate(src => { try { return eval(src); } catch (e) { return 'PRE ' + e.message; } }, process.env.PRE)));
await wait(800);
const keys = (process.env.KEYS || 'KeyW').split(','), out = [];
for (const k of keys) await p.keyboard.down(k);
for (let t = 0; t < (+(process.env.SECS || 8)) * 2; t++) { await wait(500); out.push((await p.evaluate(() => window.__game.pos())).map(v => +v.toFixed(1)).join(',')); }
for (const k of keys) await p.keyboard.up(k);
console.log(out.join(' | '), errs.length ? 'ERR ' + errs[0] : '');
await b.close();
