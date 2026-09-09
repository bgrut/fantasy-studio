// Ceremony: the title card in three worlds' voices, and the caption after an
// edge crossing. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const OUT = process.env.OUT || 'cere';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(() => { const F = window.__factory; F.goalIdx = F.GOALS.length; F.addCores(9); });
for (const id of ['ember', 'frost', 'verdant']) {
  const mood = await p.evaluate(async (id) => {
    const F = window.__factory;
    const k = F.WORLDS.findIndex(w => w.id === id);
    if (k < 0) return null;
    F.travelTo(k);
    await new Promise(r => setTimeout(r, 1500));
    return document.getElementById('title').dataset.mood;
  }, id);
  console.log(id, 'card mood', mood);
  await p.screenshot({ path: OUT + '_title_' + id + '.png' });
  await p.evaluate(() => window.__factory.endIntro());
  await new Promise(r => setTimeout(r, 300));
}
// back home, walk over an edge: stand near the north edge of the top face, hold W
await p.evaluate(async () => {
  const F = window.__factory;
  F.travelTo(0); F.endIntro();
  await new Promise(r => setTimeout(r, 400));
  const w = F.tileWorld(0, Math.floor(F.N / 2), F.N - 2);
  F.player.pos.set(w[0], F.HALF + 1.6, w[2]); F.player.face = 0;
  F.player.fwd.set(0, 0, -1);
});
await p.keyboard.down('KeyW');
await new Promise(r => setTimeout(r, 1100));
await p.keyboard.up('KeyW');
await new Promise(r => setTimeout(r, 250));
const cap = await p.evaluate(() => ({ face: window.__game.facts().player_face,
  caption: document.getElementById('facecap').textContent, on: document.getElementById('facecap').classList.contains('on'),
  fov: +window.__camera.fov.toFixed(1) }));
console.log('crossing', JSON.stringify(cap));
await p.screenshot({ path: OUT + '_crossing.png' });
await b.close();
