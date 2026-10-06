// A service game played through: waits for a customer at the counter, goes
// behind it, makes their order at the stations it needs (E at each) and hands
// it over (E), several times; shoots the cafe, a customer with their order
// over their head, and the barista at work. Reports window.__serve.
//   J=job_N OUT=<dir> TAG=<name> node serveshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'cafe';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await sleep(12000);
await p.screenshot({ path: `${OUT}/${TAG}_1_title.jpg`, type: 'jpeg', quality: 88 });
await p.click('#startbtn').catch(() => {}); await sleep(2500); await p.keyboard.press('g').catch(() => {});
const has = await p.evaluate(() => !!window.__serve);
if (!has) { console.log(TAG, 'NO SERVICE SYSTEM', JSON.stringify(errs.slice(0, 4))); await b.close(); process.exit(1); }
// the room, from the door
await p.evaluate(() => { const s = window.__serve(), q = s.queue[1];
  window.__camPin = { pos: [q[0] + 0.3, 2.6, q[1] - 7.5], look: [q[0], 1.2, q[1] + 1.5] }; });
await sleep(9000);
await p.screenshot({ path: `${OUT}/${TAG}_2_room.jpg`, type: 'jpeg', quality: 88 });
const log = [];
for (let round = 0; round < 4; round++) {
  // a customer waiting?
  let w = null;
  for (let k = 0; k < 60 && !w; k++) { w = await p.evaluate(() => window.__serve().customers.find(c => c.state === 'wait') || null); if (!w) await sleep(500); }
  if (!w) { log.push('no customer came'); break; }
  if (round === 0) {
    await p.evaluate((w) => { window.__camPin = { pos: [w.pos[0] + 1.6, 2.4, w.pos[1] - 2.6], look: [w.pos[0], 1.9, w.pos[1]] }; }, w);
    await sleep(700);
    await p.screenshot({ path: `${OUT}/${TAG}_3_order.jpg`, type: 'jpeg', quality: 88 });
  }
  const NEEDS = { espresso: ['espresso'], latte: ['espresso', 'milk steamer'], cappuccino: ['espresso', 'milk steamer'], tea: ['kettle'] };
  for (const stName of NEEDS[w.order]) {
    await p.evaluate((n) => { const s = window.__serve(), st = s.stations.find(x => x.name === n); window.__game.tp(st.x, st.z - 0.4); }, stName);
    await sleep(400);
    await p.keyboard.press('e'); await sleep(300);
  }
  if (round === 0) {
    await p.evaluate(() => { const s = window.__serve(), st = s.stations[1];
      window.__camPin = { pos: [st.x + 1.8, 2.3, st.z - 3.2], look: [st.x, 1.2, st.z] }; });
    await sleep(700);
    await p.screenshot({ path: `${OUT}/${TAG}_4_barista.jpg`, type: 'jpeg', quality: 88 });
  }
  // hand it across the counter
  await p.evaluate((w) => { const s = window.__serve(); const c = s.customers.find(c => c.state === 'wait' && c.order === w.order) || w;
    window.__game.tp(c.pos[0], c.pos[1] + 1.9); }, w);
  await sleep(400);
  await p.keyboard.press('e'); await sleep(500);
  const s = await p.evaluate(() => { const s = window.__serve(); return { served: s.served, held: s.held, tips: s.tips }; });
  log.push(w.order + ' -> served ' + s.served + (s.held ? ' (still holding ' + s.held + ')' : ''));
}
await p.evaluate(() => { window.__camPin = null; });
await sleep(1000);
await p.screenshot({ path: `${OUT}/${TAG}_5_play.jpg`, type: 'jpeg', quality: 88 });
const fin = await p.evaluate(() => ({ serve: (({ served, missed, tips }) => ({ served, missed, tips }))(window.__serve()), quest: window.__game.quest() }));
console.log(TAG, JSON.stringify(log), JSON.stringify(fin), 'errors', JSON.stringify(errs.slice(0, 4)));
await b.close();
