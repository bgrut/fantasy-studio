// The crossing as a frame: teleport next to an edge, hold W over it, and
// shoot the moment the face changes, while the wash and the caption are up.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 4000));
const start = await p.evaluate(() => {
  const F = window.__factory;
  document.getElementById('tutor')?.classList.remove('on');
  // stand two metres short of the east edge of the top face, facing it
  F.player.pos.set(F.HALF - 2.2, F.HALF + 1.6, 0);
  F.player.fwd.set(1, 0, 0); F.player.pitch = -0.12;
  return window.__game.facts().player_face;
});
await p.mouse.click(640, 380);                        // pointer lock, so the keys are the game's
await new Promise(r => setTimeout(r, 300));
await p.keyboard.down('KeyW');
let shot = false, waited = 0;
while (!shot && waited < 6000) {
  await new Promise(r => setTimeout(r, 80)); waited += 80;
  const f = await p.evaluate(() => window.__game.facts());
  if (f.player_face !== start) {
    await new Promise(r => setTimeout(r, 260));
    await p.screenshot({ path: process.env.OUT || 'cross.png' });
    const g = await p.evaluate(() => ({ ...window.__game.facts(), caption: document.getElementById('facecap')?.textContent }));
    console.log('crossed   :', start, '->', f.player_face, '| wash', g.crossWash, '| lit', g.crossLit, '| caption', JSON.stringify(g.caption));
    shot = true;
  }
}
await p.keyboard.up('KeyW');
if (!shot) console.log('never crossed');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
