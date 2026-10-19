import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.text().slice(0, 160)); });
await p.goto('http://127.0.0.1:8790/?fresh=1', { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 6000));
const f = () => p.evaluate(() => { const g = window.__game.facts(); return [g.goal_index, g.value !== undefined ? g.value : null, g.banked, window.__factory.runValue]; });
console.log('before', JSON.stringify(await f()));
await p.evaluate(() => document.querySelector('.tool[data-tool="forge"]').dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))); await new Promise(r => setTimeout(r, 150));
console.log('after click', JSON.stringify(await f()));
try { await p.evaluate(() => window.__factory.addValue(60)); } catch (e) { console.log('THREW', e.message.slice(0, 300)); }
for (let k = 0; k < 10; k++) { await new Promise(r => setTimeout(r, 300)); console.log(k, JSON.stringify(await f())); }
console.log(errs.slice(0, 6).join(' | '));
await b.close();
