// Every face its own ground: the player stood on the ember face, the salt face
// and the underside, and an orbit that shows three platings meeting at a corner.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 6000));
await p.evaluate(() => { document.getElementById('tutor')?.classList.remove('on'); window.__factory.ageHints(); });
for (const [k, f] of [['ember', 2], ['salt', 4], ['under', 1]]) {
  await p.evaluate((f) => { const F = window.__factory; F.goFace(f, 4, Math.floor(F.N / 2), 2.4); }, f);
  await new Promise(r => setTimeout(r, 1200));
  await p.screenshot({ path: 'face_' + k + '.png' });
}
// the corner: TAB overhead pulled back so three faces meet
await p.keyboard.press('Tab'); await new Promise(r => setTimeout(r, 1400));
await p.screenshot({ path: 'face_corner.png' });
console.log('facts     :', JSON.stringify(await p.evaluate(() => window.__game.facts().plating)));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
