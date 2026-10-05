// A mall interior: the play view, the concourse from the entrance, a
// storefront, and the fountain. Reports window.__mall.   J=job_N OUT=<dir> node mallshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 11000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: `${OUT}/mall_play.jpg`, type: 'jpeg', quality: 88 });
const plan = await p.evaluate(async () => { const s = await (await fetch('spec.json')).json(); return s.world.level.interior; });
const hall = plan.rooms[0], hd = hall[3] / 2, hw = hall[2] / 2, H = plan.wall_h;
const unit = plan.rooms[1];
// the hero is not safe in here: the views go before the play view's fight
const shots = [
  ['mall_fountain', { pos: [hw * 0.55, 2.6, -7], look: [0, 0.8, 0] }],
  ['mall_concourse', { pos: [0, 2.2, -hd + 1.5], look: [0, 1.6, hd * 0.5] }],
  ['mall_store', { pos: [-unit[0] * 0.05, 1.8, unit[1] - 5], look: [unit[0], 1.4, unit[1]] }],
];
for (const [name, pin] of shots) {
  await p.evaluate(pin => { window.__camPin = pin; }, pin);
  await new Promise(r => setTimeout(r, 700));
  await p.screenshot({ path: `${OUT}/${name}.jpg`, type: 'jpeg', quality: 88 });
}
const facts = await p.evaluate(() => ({ mall: window.__mall || null, fps: window.__fps || null }));
console.log(J, JSON.stringify(facts), 'units', plan.rooms.length - 1, JSON.stringify(errs.slice(0, 4)));
await b.close();
