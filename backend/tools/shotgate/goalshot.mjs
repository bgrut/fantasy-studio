// What waits at the end of the walk: the camera pinned a little way off
// the level's goal, looking at it (a cabin, a lighthouse, a helicopter).
//   J=job_N OUT=<dir> TAG=<name> node goalshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'goal';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g').catch(() => {});
const g = await p.evaluate(async () => { try { const s = await (await fetch('spec.json')).json(); return (s.world && s.world.level && s.world.level.goal) || null; } catch (e) { return null; } });
if (g) {
  await p.evaluate(() => { for (const el of document.body.children) if (el.tagName !== 'CANVAS' && !el.querySelector('canvas')) el.style.visibility = 'hidden'; });
  await p.evaluate(([x, z]) => { const y = 0; window.__camPin = { pos: [x - 9, 5.5, z - 12], look: [x + 4, 1.5, z + 1] }; }, g);
  await new Promise(r => setTimeout(r, 1800));
  await p.screenshot({ path: `${OUT}/${TAG}_goal.jpg`, type: 'jpeg', quality: 90 });
}
console.log(TAG, 'goal', JSON.stringify(g), 'errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
