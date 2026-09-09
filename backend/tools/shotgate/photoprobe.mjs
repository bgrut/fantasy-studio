// Photo mode and graded icons, proven: P hides the chrome, Enter saves a PNG
// and tells the studio, P again restores; the bar re-renders when you travel.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(() => { window.__shots = []; addEventListener('message', e => { if (e.data && e.data.type === 'fs-shot') window.__shots.push({ name: e.data.name, bytes: e.data.dataUrl.length, world: e.data.world }); }); });
const iconBefore = await p.evaluate(() => document.querySelector('.tool[data-tool="smelter"] img.ico').src.length + ':' + document.querySelector('.tool[data-tool="smelter"] img.ico').src.slice(-120));
await p.keyboard.press('KeyP'); await new Promise(r=>setTimeout(r,400));
const on = await p.evaluate(() => ({ photo: window.__game.facts().photo, body: document.body.className, hud: getComputedStyle(document.getElementById('hud')).opacity, cap: document.getElementById('facecap').textContent }));
await p.screenshot({ path: (process.env.OUT || 'photo') + '_mode.png' });
await p.keyboard.press('Enter'); await new Promise(r=>setTimeout(r,600));
const shots = await p.evaluate(() => window.__shots);
await p.keyboard.press('KeyP'); await new Promise(r=>setTimeout(r,400));
const off = await p.evaluate(() => ({ photo: window.__game.facts().photo, hud: getComputedStyle(document.getElementById('hud')).opacity }));
// travel: the bar is re-rendered under the new grade
const trav = await p.evaluate(async () => {
  const F = window.__factory; F.goalIdx = F.GOALS.length; F.addCores(9);
  const before = F.iconsWorld;
  F.travelTo(F.WORLDS.findIndex(w => w.id === 'ember')); F.endIntro();
  await new Promise(r => setTimeout(r, 800));
  return { before, after: F.iconsWorld, world: window.__game.facts().world, icons: document.querySelectorAll('.tool[data-tool="smelter"] img.ico').length, icon: document.querySelector('.tool[data-tool="smelter"] img.ico').src.length + ':' + document.querySelector('.tool[data-tool="smelter"] img.ico').src.slice(-120) };
});
await p.screenshot({ path: (process.env.OUT || 'photo') + '_ember_bar.png' });
console.log('photo on  :', JSON.stringify(on));
console.log('saved     :', JSON.stringify(shots));
console.log('photo off :', JSON.stringify(off));
console.log('travel    : icons world', trav.before, '->', trav.after, '| icon changed:', trav.icon !== iconBefore, '| icons on the tool:', trav.icons, '| world', trav.world);
await b.close();
const ok = on.photo && on.hud === '0' && /PHOTO/.test(on.cap) && shots.length === 1 && shots[0].bytes > 20000
  && !off.photo && off.hud === '1' && trav.after !== trav.before && trav.icon !== iconBefore && trav.icons === 1;
console.log(ok ? 'OK' : 'FAIL');
