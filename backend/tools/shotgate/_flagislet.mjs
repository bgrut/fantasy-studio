// Crystal Works: a close look at the islets adrift round a green worldlet, and the sky
// from the surface with them in it.   OUT=prefix [URL=] node _flagislet.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.goto(URL + '?fresh=1&noguide=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(5000);
await p.addStyleTag({ content: 'body > *:not(canvas){visibility:hidden !important}' });
const shot = async (n) => { await w(1800); await p.screenshot({ path: `${process.env.OUT}_${n}.jpg`, type: 'jpeg', quality: 88 }); };
const info = await p.evaluate(() => {
  let g = null; window.__scene.traverse(o => { if (o.name === 'worldIslets') g = o; });
  if (!g) return { none: true };
  return { visible: g.visible, calls: g.children.length, at: g.userData.isl.map(o => o.g).map(c => [c.position.x, c.position.y, c.position.z, c.scale.x].map(v => +v.toFixed(1))) };
});
console.log(JSON.stringify(info));
if (info.at) {
  for (const k of [0, 3]) {
    await p.evaluate(k => {
      let g = null; window.__scene.traverse(o => { if (o.name === 'worldIslets') g = o; });
      const c = g.userData.isl[k].g, P = c.position, s = c.scale.x;
      const d = Math.hypot(P.x, P.z), ox = P.x / d, oz = P.z / d;   // look from the worldlet's side, out at the islet
      window.__camPin = { pos: [P.x - ox * s * 3.2 + oz * s * 1.2, P.y + s * 0.9, P.z - oz * s * 3.2 - ox * s * 1.2], look: [P.x, P.y - s * 0.5, P.z] };
    }, k);
    await shot('islet' + k);
  }
  await p.evaluate(() => { window.__camPin = null; });
}
// from the surface, looking up and out
await p.evaluate(() => { const c = window.__camera; window.__camPin = { pos: [c.position.x, c.position.y + 1.6, c.position.z], look: [c.position.x + 60, c.position.y + 38, c.position.z - 40] }; });
await shot('skyward');
console.log(errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
