// The ambience layer on two worlds: embers rising on Ember Reach, breath on
// Frostline. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
for (const [id, tag] of [['ember', 'embers'], ['frost', 'breath']]) {
  const ok = await p.evaluate(async (id) => {
    const F = window.__factory;
    F.goalIdx = F.GOALS.length; F.addCores(9);
    const k = F.WORLDS.findIndex(w => w.id === id);
    if (k < 0) return false;
    F.travelTo(k); F.endIntro();
    F.player.pitch = -0.05;
    await new Promise(r => setTimeout(r, 4200));   // let the layer fill
    return { world: window.__game.facts().world, particles: window.__game.facts().particles };
  }, id);
  console.log(tag, JSON.stringify(ok));
  if (ok) await p.screenshot({ path: (process.env.OUT || 'amb') + '_' + tag + '.png' });
}
await b.close();
