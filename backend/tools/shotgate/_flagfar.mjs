// Crystal Works: each far world in the sky, framed from the worldlet.   OUT=prefix [URL=] node _flagfar.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.goto(URL + '?fresh=1&noguide=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(5000);
await p.addStyleTag({ content: 'body > *:not(canvas){visibility:hidden !important}' });
const n = await p.evaluate(() => { let f = null; window.__scene.traverse(o => { if (o.name === 'body' && o.parent && o.parent.parent && !f) f = o.parent.parent; }); window.__farG = f; return f ? f.children.length : 0; });
for (let k = 0; k < n; k++) {
  await p.evaluate(k => { const g = window.__farG.children[k], P = g.getWorldPosition(new window.__camera.position.constructor());
    const d = P.clone().normalize(); window.__camPin = { pos: [P.x - d.x * 170, P.y - d.y * 170, P.z - d.z * 170], look: [P.x, P.y, P.z] }; }, k);
  await w(1800); await p.screenshot({ path: `${process.env.OUT}_far${k}.jpg`, type: 'jpeg', quality: 88 });
}
console.log(n, errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
