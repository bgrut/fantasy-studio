// Any interior venue (hospital, school, lab, mall...): the hall from the
// entrance, a look into a room off it, a second room, and the play view.
// Reports window.__venue / __mall.   J=job_N OUT=<dir> TAG=<name> node venueshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 11000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1000));
const plan = await p.evaluate(async () => { const s = await (await fetch('spec.json')).json(); return s.world.level.interior || null; });
if (!plan) { console.log(TAG, 'NO INTERIOR'); await b.close(); process.exit(1); }
const hall = plan.rooms[0], hd = hall[3] / 2, hw = hall[2] / 2;
const r1 = plan.rooms[1], r2 = plan.rooms[Math.min(plan.rooms.length - 1, 4)];
const into = (r) => { const s = r[0] > 0 ? 1 : -1; return { pos: [r[0] - s * (r[2] / 2 + Math.min(hw, 2.2)), 1.7, r[1] - 0.6], look: [r[0] + s * r[2] * 0.2, 1.0, r[1] + 0.4] }; };
const shots = [
  ['hall', { pos: [0, 1.8, -hd + 1.2], look: [0, 1.4, hd * 0.5] }],
  ['room1', into(r1)],
  ['room2', into(r2)],
];
for (const [name, pin] of shots) {
  await p.evaluate(pin => { window.__camPin = pin; }, pin);
  await new Promise(r => setTimeout(r, 700));
  await p.screenshot({ path: `${OUT}/${TAG}_${name}.jpg`, type: 'jpeg', quality: 88 });
}
await p.evaluate(() => { window.__camPin = null; });
await new Promise(r => setTimeout(r, 700));
await p.screenshot({ path: `${OUT}/${TAG}_play.jpg`, type: 'jpeg', quality: 88 });
const facts = await p.evaluate(() => ({ venue: window.__venue || window.__mall || null }));
console.log(TAG, plan.kind, JSON.stringify(facts), 'rooms', plan.rooms.length - 1, JSON.stringify(errs.slice(0, 4)));
await b.close();
