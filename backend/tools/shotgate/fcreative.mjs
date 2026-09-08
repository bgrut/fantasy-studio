// Creative mode. It has to be a different WORLD, not a cheat on this one:
// chosen by the URL at creation, everything open from the first frame, seams
// that never thin, a market that sits still, free upgrades — and the survival
// save of the same prompt untouched under its own key.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
p.on('console', m => { const u = (m.location() && m.location().url) || '';
  if (m.type()==='error' && !/favicon/i.test(u)) errs.push('console: '+m.text().slice(0,160)); });
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';
const wait = ms => new Promise(r => setTimeout(r, ms));

// 1. a survival world first, with a little progress in it
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const surv = await p.evaluate(async () => {
  const F = window.__factory;
  F.addValue(60); await new Promise(r => setTimeout(r, 400)); F.save();
  const f = window.__game.facts();
  return { creative: f.creative, goal: f.goal_index, key: F.SAVE_KEY, badge: getComputedStyle(document.querySelector('#hud h1'), '::after').display };
});
console.log('survival  : creative', surv.creative, '| tier', surv.goal, '| key', surv.key, '| badge', surv.badge);

// 2. the creative world: everything open, from the first frame
await p.goto(URL + q + 'creative=1&fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const cr = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, f = window.__game.facts();
  const w = ms => new Promise(r => setTimeout(r, ms));
  // seams: find the starter rig's seam and watch it for a while
  let seam = null;
  F.cells.forEach((face, fi) => face.forEach((col, i) => col.forEach((c, j) => {
    if (c.t === TY.MINER && c.mesh && !seam) seam = F.cells[fi][i][j]; })));
  const rich0 = seam ? seam.rich : null;
  // market: run it hard
  for (let k = 0; k < 40; k++) F.stepMarket(4);
  const prices = F.TRADED.map(t => +F.PRICE[t].toFixed(2));
  // upgrades: free, and to the raised cap
  const ore0 = f.value;
  let bought = 0; while (F.buy('tick')) bought++;
  const ore1 = window.__game.facts().value;
  await w(5000);
  const g = window.__game.facts();
  return { creative: f.creative, unlocked: f.unlocked, caps: f.caps, upgrade_caps: f.upgrade_caps,
           worlds_open: f.worlds_open, worlds: F.WORLDS.length, card: document.querySelector('#goal b').textContent,
           badge: getComputedStyle(document.querySelector('#hud h1'), '::after').display,
           key: F.SAVE_KEY, rich0: rich0 && +rich0.toFixed(3), rich1: seam && +seam.rich.toFixed(3),
           prices, bought, oreSpent: +(ore0 - ore1).toFixed(1), tickLvl: F.UPGRADES.tick.lvl,
           rows: [...document.querySelectorAll('#world .wr')].map(o => o.textContent + (o.classList.contains('can') ? ' [open]' : ' [locked]')) };
});
console.log('creative  : creative', cr.creative, '| card', JSON.stringify(cr.card), '| badge', cr.badge, '| key', cr.key);
console.log('open      : unlocked', cr.unlocked.length, '| caps', cr.caps.join(','), '| upgrade caps',
            JSON.stringify(cr.upgrade_caps), '| worlds', cr.worlds_open, 'of', cr.worlds, '|', cr.rows.join(' · '));
console.log('pushback  : seam', cr.rich0, '->', cr.rich1, 'over 5s under a rig | prices after 160s',
            cr.prices.join('/'), '| bought', cr.bought, 'ticks for', cr.oreSpent, 'value (lvl', cr.tickLvl + ')');

// 3. the survival world is still there, exactly as it was
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const back = await p.evaluate(() => { const f = window.__game.facts(); return { creative: f.creative, goal: f.goal_index, unlocked: f.unlocked.length }; });
console.log('survival  : back at tier', back.goal, '| creative', back.creative, '| unlocked', back.unlocked);

// 4. "new world" offers the choice in-game, and picking the other mode reloads into it
const flip = await p.evaluate(async () => {
  const w = document.getElementById('wipe');
  w.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 100));
  const offered = [...w.querySelectorAll('[data-mode]')].map(o => o.dataset.mode);
  const cr = w.querySelector('[data-mode="creative"]');
  if (cr) cr.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  return { offered };
});
await wait(5500);
const flipped = await p.evaluate(() => ({ creative: window.__game.facts().creative, url: location.search }));
console.log('new world : offers', flip.offered.join('/'), '| picked creative ->', flipped.creative, flipped.url);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'creative.png' });
await b.close();

const ok = !surv.creative && surv.goal === 1 && surv.badge === 'none'
  && cr.creative && /CREATIVE/.test(cr.card) && cr.badge !== 'none' && cr.key !== surv.key
  && cr.unlocked.length >= 10 && cr.caps.length === 3 && cr.upgrade_caps.tick === 8
  && cr.worlds_open === cr.worlds && cr.rows.every(r => / \[open\]$/.test(r))
  && cr.rich0 !== null && cr.rich1 >= cr.rich0
  && cr.prices.every(x => x === 1) && cr.bought === 8 && cr.oreSpent === 0
  && !back.creative && back.goal === 1 && back.unlocked < 10
  && flip.offered.join('/') === 'survival/creative' && flipped.creative
  && errs.length === 0;
process.exit(ok ? 0 : 1);
