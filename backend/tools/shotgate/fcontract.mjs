// Contracts, shards and rank. A contract has to be posted, count deliveries of
// its item and nothing else, pay its bonus and a shard when filled, lapse
// quietly when not; three shards have to become a core; a meltdown has to
// raise the rank, which pays the next contract more; all of it has to survive
// a reload.
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

// 1. nothing is posted before the first tier; after it, a contract is posted
//    and sized to the item; the card shows it
const posted = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const before = window.__game.facts().contract;
  F.addValue(60); await w(400);                       // tier 1: the market opens
  const c = F.offerContract(TY.INGOT);
  await w(300);
  const f = window.__game.facts();
  const card = document.getElementById('contract');
  return { before, item: f.contract && f.contract.item, need: c.need, bonus: c.bonus, left: f.contract.left,
           cardOn: card.classList.contains('on'), cardText: card.querySelector('b').textContent,
           toast: document.getElementById('toast').textContent, rankLine: document.getElementById('rank').textContent };
});
console.log('posted    : before tier 1', JSON.stringify(posted.before), '| deliver', posted.need, posted.item, 'for +' + posted.bonus,
            '| left', posted.left, '| card', posted.cardOn, JSON.stringify(posted.cardText), '| said:', JSON.stringify(posted.toast));
console.log('rank line :', JSON.stringify(posted.rankLine));

// 2. only the contracted item counts; filling pays the bonus and a shard
const filled = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const c = F.contract;
  F.bank(TY.ALLOY); F.bank(TY.INGOT_E);               // the wrong things
  await w(200);
  const wrong = window.__game.facts().contract.have;
  const ore0 = window.__game.facts().value, shards0 = window.__game.facts().shards;
  for (let k = 0; k < c.need - 1; k++) F.bank(TY.INGOT);
  await w(200);
  const almost = window.__game.facts().contract;
  F.bank(TY.INGOT);
  await w(300);
  const f = window.__game.facts();
  return { need: c.need, bonus: c.bonus, wrong, almost: almost && almost.have, after: f.contract,
           gained: +(f.value - ore0).toFixed(1), shards: f.shards, shards0, filled: f.contracts_filled,
           toast: document.getElementById('toast').textContent, rankLine: document.getElementById('rank').textContent };
});
console.log('filled    : wrong items counted', filled.wrong, '| at need-1:', filled.almost, '| after the last: contract',
            JSON.stringify(filled.after), '| gained', filled.gained, '(bonus ' + filled.bonus + ' + the ingot) | shards',
            filled.shards0, '->', filled.shards, '| said:', JSON.stringify(filled.toast));
console.log('rank line :', JSON.stringify(filled.rankLine));

// 3. a contract lapses quietly; three shards make a core
const lapse = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.offerContract(TY.INGOT_S);
  F.contractLeft = 0.2;
  await w(600);
  const gone = window.__game.facts().contract;
  const lapsedToast = document.getElementById('toast').textContent;
  F.shards = 2;
  const cores0 = window.__game.facts().cores;
  const c = F.offerContract(TY.INGOT);
  for (let k = 0; k < c.need; k++) F.bank(TY.INGOT);
  await w(300);
  const f = window.__game.facts();
  return { gone, lapsedToast, cores0, cores: f.cores, shards: f.shards, toast: document.getElementById('toast').textContent };
});
console.log('lapsed    : contract', JSON.stringify(lapse.gone), '| said:', JSON.stringify(lapse.lapsedToast));
console.log('three     : shards 2 + a fill -> cores', lapse.cores0, '->', lapse.cores, '| shards left', lapse.shards, '| said:', JSON.stringify(lapse.toast));

// 4. a meltdown raises the rank, which pays the next contract more
const ranked = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.goalIdx = F.GOALS.length;
  F.addValue(F.MELT_MIN + 50);
  const c0 = F.offerContract(TY.INGOT); const bonus0 = c0.bonus, need0 = c0.need; F.contractLeft = 0.1; await w(400);
  F.meltdown(); F.endIntro(); await w(400);
  const f = window.__game.facts();
  const c1 = F.offerContract(TY.INGOT);
  return { rank: f.rank, need0, bonus0, need1: c1.need, bonus1: c1.bonus, rankLine: document.getElementById('rank').textContent,
           edge: '#' + window.__scene.getObjectByName('worldEdge').material.color.getHexString() };
});
console.log('ranked    : rank', ranked.rank, '| contract bonus for', ranked.need0, 'ingots', ranked.bonus0, '-> for', ranked.need1, 'ingots', ranked.bonus1,
            '| line', JSON.stringify(ranked.rankLine), '| edge', ranked.edge);

// 5. shards and rank survive a reload
await p.evaluate(() => window.__factory.save());
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const back = await p.evaluate(() => { const f = window.__game.facts(); return { rank: f.rank, shards: f.shards, filled: f.contracts_filled }; });
console.log('reloaded  : rank', back.rank, '| shards', back.shards, '| contracts filled', back.filled);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'contract.png' });
await b.close();

const perUnit0 = ranked.bonus0 / ranked.need0, perUnit1 = ranked.bonus1 / ranked.need1;
const ok = posted.before === null && /ingot/.test(posted.item) && posted.need >= 4 && posted.cardOn && /DELIVER \d+ \w+ INGOTS?/.test(posted.cardText)
  && /CONTRACT/.test(posted.toast) && /UNRANKED/.test(posted.rankLine)
  && filled.wrong === 0 && filled.almost === filled.need - 1 && filled.after === null && filled.gained > filled.bonus
  && filled.shards === filled.shards0 + 1 && filled.filled === 1 && /FILLED/.test(filled.toast)
  && lapse.gone === null && /lapsed/.test(lapse.lapsedToast) && lapse.cores === lapse.cores0 + 1 && lapse.shards === 0 && /CORE FROM SHARDS/.test(lapse.toast)
  && ranked.rank === 1 && perUnit1 > perUnit0 * 1.1 && /RANK I/.test(ranked.rankLine)
  && back.rank === 1 && back.shards === 0 && back.filled === 2
  && errs.length === 0;
process.exit(ok ? 0 : 1);
