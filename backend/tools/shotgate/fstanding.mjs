// Standing orders. Three contracts kept in a row have to earn one; a lapse
// has to reset the streak; the order has to hold while the rate is met, pay
// each minute, and close after ten seconds short — saying how long it held.
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

await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);

// 1. two fills and a lapse leave no order; three fills in a row post one
const earned = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.addValue(60); await w(300);
  const fill = async () => { const c = F.offerContract(TY.INGOT); for (let k = 0; k < c.need; k++) F.bank(TY.INGOT); await w(200); };
  await fill(); await fill();
  F.offerContract(TY.INGOT); F.contractLeft = 0.1; await w(500);        // a lapse
  const afterLapse = { streak: window.__game.facts().streak, standing: window.__game.facts().standing };
  await fill(); await fill(); await fill();
  const f = window.__game.facts();
  const card = document.getElementById('standing');
  return { afterLapse, streak: f.streak, standing: f.standing, cardOn: card.classList.contains('on'),
           cardText: card.querySelector('b').textContent, toast: document.getElementById('toast').textContent };
});
console.log('streak    : after two fills and a lapse', JSON.stringify(earned.afterLapse), '| after three in a row: streak', earned.streak,
            '| order', JSON.stringify(earned.standing));
console.log('card      :', earned.cardOn, JSON.stringify(earned.cardText), '| said:', JSON.stringify(earned.toast).slice(0, 120) + '...');

// 2. the order holds while the rate is met and pays on the minute
const held = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const st = F.standing;
  for (let k = 0; k < st.perMin + 2; k++) F.bank(TY.INGOT);          // a minute's worth, at once
  await w(1200);
  const a = window.__game.facts().standing;
  const ore0 = window.__game.facts().value;
  F.standingHeld = 59.5;                                               // to the minute mark
  await w(900);
  const f = window.__game.facts();
  return { rate: a.rate, perMin: a.per_min, short: a.short, heldBefore: a.held, minutes: f.standing && f.standing.minutes,
           paid: +(f.value - ore0).toFixed(1), pay: st.pay, toast: document.getElementById('toast').textContent };
});
console.log('holds     : rate', held.rate, 'of', held.perMin, '| short', held.short, '| held', held.heldBefore, '-> minute', held.minutes,
            '| paid', held.paid, '(pay ' + held.pay + ') | said:', JSON.stringify(held.toast));

// 3. and closes after ten seconds short, saying how long it held; the streak resets
const closed = await p.evaluate(async () => {
  const F = window.__factory;
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.standing.log.length = 0;                                           // the line stops
  F.standing.held = 130;
  await w(1200);
  const shortAt = window.__game.facts().standing && window.__game.facts().standing.short;
  const cardShort = document.getElementById('standing').classList.contains('short');
  await w((F.STANDING_GRACE + 0.5) * 1000);
  const f = window.__game.facts();
  return { shortAt, cardShort, standing: f.standing, streak: f.streak, toast: document.getElementById('toast').textContent };
});
console.log('closes    : short', closed.shortAt + 's in, card marked short', closed.cardShort, '| after the grace: order', JSON.stringify(closed.standing),
            '| streak', closed.streak, '| said:', JSON.stringify(closed.toast));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'standing.png' });
await b.close();

const ok = earned.afterLapse.streak === 0 && earned.afterLapse.standing === null
  && earned.streak >= 3 && earned.standing && earned.standing.per_min >= 4 && earned.cardOn && /STANDING ORDER/.test(earned.cardText) && /STANDING ORDER/.test(earned.toast)
  && held.rate >= held.perMin && held.short === 0 && held.minutes === 1 && held.paid >= held.pay && /HELD/.test(held.toast)
  && closed.shortAt > 0 && closed.cardShort && closed.standing === null && closed.streak === 0 && /closed after 2:1\d/.test(closed.toast)
  && errs.length === 0;
process.exit(ok ? 0 : 1);
