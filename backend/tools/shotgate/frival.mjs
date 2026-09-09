// The rival buyer. It has to bid one product up and nothing else, mark that
// product on the board and the card, count what it bought and the premium,
// and leave on time with a toast that says what it took.
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

const r = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const none = window.__game.facts().rival;
  // a baseline sale of each, then the buyer arrives for ember ingots
  const unit = t => (F.VALUE ? F.VALUE[t] : 0);
  const v0 = window.__game.facts().value;
  F.PRICE[TY.INGOT_E] = 1.0; F.PRICE[TY.INGOT] = 1.0;
  F.bank(TY.INGOT_E); const plainEmber = window.__game.facts().value - v0;
  const v1 = window.__game.facts().value;
  F.bank(TY.INGOT); const plainCrystal = window.__game.facts().value - v1;
  const rv = F.offerRival(TY.INGOT_E);
  await w(300);
  const during = window.__game.facts().rival;
  const card = document.getElementById('rival');
  const cardOn = card.classList.contains('on'), cardText = card.querySelector('b').textContent;   // read NOW, before the buyer leaves
  const hot = [...document.querySelectorAll('#tick .mk.hot .nm')].map(o => o.textContent);
  const v2 = window.__game.facts().value;
  F.bank(TY.INGOT_E); const rivalEmber = window.__game.facts().value - v2;
  const v3 = window.__game.facts().value;
  F.bank(TY.INGOT); const rivalCrystal = window.__game.facts().value - v3;
  await w(300);
  const mid = window.__game.facts().rival;
  const offerToast = document.getElementById('toast').textContent;
  F.rivalLeft = 0.2;
  await w(700);
  const after = window.__game.facts().rival;
  return { none, plainEmber: +plainEmber.toFixed(2), plainCrystal: +plainCrystal.toFixed(2), rivalEmber: +rivalEmber.toFixed(2), rivalCrystal: +rivalCrystal.toFixed(2),
           mult: rv.mult, during, cardOn, cardText, hot, mid, offerToast,
           after, leftToast: document.getElementById('toast').textContent, hotAfter: document.querySelectorAll('#tick .mk.hot').length };
});
console.log('arrives   : before', JSON.stringify(r.none), '| offered', JSON.stringify(r.during), '| card', r.cardOn, JSON.stringify(r.cardText), '| board marks', JSON.stringify(r.hot));
console.log('said      :', JSON.stringify(r.offerToast));
console.log('pays      : ember ingot', r.plainEmber, '->', r.rivalEmber, '(x' + r.mult + ') | crystal ingot', r.plainCrystal, '->', r.rivalCrystal, '(unchanged)');
console.log('counts    :', JSON.stringify(r.mid));
console.log('leaves    :', JSON.stringify(r.after), '| board marks left', r.hotAfter, '| said:', JSON.stringify(r.leftToast));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'rival.png' });
await b.close();

const ok = r.none === null && r.during && /ember/.test(r.during.item) && r.cardOn && /RIVAL BUYER/.test(r.cardText) && r.hot.length === 1 && /ember/.test(r.hot[0])
  && /RIVAL BUYER/.test(r.offerToast)
  && Math.abs(r.rivalEmber - r.plainEmber * r.mult) < 0.05 && Math.abs(r.rivalCrystal - r.plainCrystal) < 0.05
  && r.mid.sold === 1 && r.mid.extra > 0
  && r.after === null && r.hotAfter === 0 && /rival buyer left/.test(r.leftToast) && /took 1 /.test(r.leftToast)
  && errs.length === 0;
process.exit(ok ? 0 : 1);
