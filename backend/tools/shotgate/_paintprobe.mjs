// the finishes: which are open, and two of them on the works. OUT=prefix
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8790/?fresh=1', { waitUntil: 'domcontentloaded' }); await new Promise(r => setTimeout(r, 7000));
console.log('fresh', JSON.stringify(await p.evaluate(() => window.__paint())), 'swatches', await p.evaluate(() => document.querySelectorAll('#paint .pnt').length));
await p.goto('http://127.0.0.1:8790/?fresh=1&creative=1', { waitUntil: 'domcontentloaded' }); await new Promise(r => setTimeout(r, 7000));
for (const id of ['brass', 'obsidian']) {
  await p.evaluate((id) => { document.querySelectorAll('#paint .pnt').forEach(el => { if (el.title.toLowerCase().startsWith(id)) el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })); }); }, id);
  await new Promise(r => setTimeout(r, 900));
  console.log(id, JSON.stringify(await p.evaluate(() => ({ p: window.__paint(), toast: document.getElementById('toast').textContent.slice(0, 80) }))));
  await p.screenshot({ path: process.env.OUT + id + '.jpg', type: 'jpeg', quality: 80 });
}
console.log('errors', errs.slice(0, 3).join(' | ') || 'none');
await b.close();
