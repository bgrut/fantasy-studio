// The assembler. It has to be locked until tier seven, take exactly one alloy
// bar and one ingot of any kind and nothing else, make a component worth more
// than both, count and sell it, ride the belt as the biggest bar, show on the
// board and in contracts once unlocked, and survive a reload.
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

// 1. locked until tier seven; the chip exists
const lock = await p.evaluate(async () => {
  const F = window.__factory;
  const chip = !!document.querySelector('.tool[data-tool="assembler"]');
  const before = !!F.UNLOCKED.assembler;
  F.goalIdx = 7; await new Promise(r => setTimeout(r, 300));
  return { chip, before, after: !!F.UNLOCKED.assembler, key: document.querySelector('.tool[data-tool="assembler"] .key').textContent };
});
console.log('locked    : chip', lock.chip, '| before tier 7', lock.before, '| after', lock.after, '| key', lock.key);

// 2. the recipe: an alloy and an ingot in, a component out; an ore is refused
const recipe = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let s = null;
  for (let i = 4; i < F.N - 4 && !s; i++) for (let j = 4; j < F.N - 4 && !s; j++)
    if ([[0, 0], [1, 0], [-1, 0]].every(([a, bb]) => F.cells[0][i + a][j + bb].t === TY.EMPTY)) s = [i, j];
  const [i, j] = s;
  F.place(0, i, j, TY.ASSEMBLER, 0);
  F.place(0, i - 1, j, TY.BELT, 0);                // feeds it
  F.place(0, i + 1, j, TY.BELT, 0);                // takes its output (points away, into nothing)
  const A = F.cells[0][i][j], feed = F.cells[0][i - 1][j], out = F.cells[0][i + 1][j];
  const oreOk = F.accepts(A, TY.CRYSTAL), alloyOk = F.accepts(A, TY.ALLOY), ingotOk = F.accepts(A, TY.INGOT_E);
  feed.item = TY.ALLOY; F.step();
  const afterAlloy = { ha: A.ha | 0, hb: A.hb | 0, secondAlloy: F.accepts(A, TY.ALLOY) };
  feed.item = TY.INGOT_E; F.step();
  // the cook starts on the machine pass of the NEXT tick, after the ingot landed
  let cooking = 0, made = null;
  for (let k = 0; k < 8 && !made; k++) { F.step(); cooking = Math.max(cooking, A.cook | 0); if (out.item) made = out.item; }
  await new Promise(r => setTimeout(r, 150));      // a frame, so the bar is drawn
  const value = F.VALUE ? null : null;
  const label = F.lookLabel ? null : null;
  return { oreOk, alloyOk, ingotOk, afterAlloy, cooking, made, component: TY.COMPONENT, bars: window.__scene.getObjectByName('bars').count };
});
console.log('recipe    : accepts ore', recipe.oreOk, '| alloy', recipe.alloyOk, '| ingot', recipe.ingotOk,
            '| after the alloy: has alloy', recipe.afterAlloy.ha, 'ingot', recipe.afterAlloy.hb, 'second alloy refused', !recipe.afterAlloy.secondAlloy,
            '| cooking', recipe.cooking, 'ticks | made', recipe.made === recipe.component ? 'a component' : recipe.made, '| bars drawn', recipe.bars);

// 3. worth more than both; counted; on the board; wanted by contracts
const worth = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const v0 = window.__game.facts().value;
  F.PRICE[TY.COMPONENT] = 1.0; F.PRICE[TY.ALLOY] = 1.0; F.PRICE[TY.INGOT] = 1.0;
  F.bank(TY.COMPONENT); const vc = window.__game.facts().value - v0;
  F.bank(TY.ALLOY); const va = window.__game.facts().value - v0 - vc;
  F.bank(TY.INGOT); const vi = window.__game.facts().value - v0 - vc - va;
  await w(200);
  const f = window.__game.facts();
  const chip = document.getElementById('ncomp').textContent;
  const board = document.querySelectorAll('#tick .mk').length;
  const c = F.offerContract(TY.COMPONENT);
  return { vc: +vc.toFixed(1), va: +va.toFixed(1), vi: +vi.toFixed(1), components: f.components, chip, board,
           contract: document.querySelector('#contract b').textContent, traded: F.TRADED.length };
});
console.log('worth     : component', worth.vc, '| alloy', worth.va, '| ingot', worth.vi, '| counted', worth.components, '(chip', worth.chip + ')',
            '| board bars', worth.board, '| contract', JSON.stringify(worth.contract));

// 4. reload keeps the machine and the count
await p.evaluate(() => window.__factory.save());
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const back = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES; let n = 0;
  F.cells.forEach(face => face.forEach(col => col.forEach(c => { if (c.t === TY.ASSEMBLER) n++; })));
  return { assemblers: n, components: window.__game.facts().components, unlocked: !!F.UNLOCKED.assembler };
});
console.log('reloaded  :', JSON.stringify(back));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'assembler.png' });
await b.close();

const ok = lock.chip && !lock.before && lock.after && lock.key === 'Q'
  && !recipe.oreOk && recipe.alloyOk && recipe.ingotOk && recipe.afterAlloy.ha === 1 && recipe.afterAlloy.hb === 0 && !recipe.afterAlloy.secondAlloy
  && recipe.cooking > 0 && recipe.made === recipe.component && recipe.bars >= 1
  && worth.vc > worth.va + worth.vi && worth.components === 1 && worth.chip === '1' && worth.board === 5 && worth.traded === 5 && /COMPONENT/.test(worth.contract)
  && back.assemblers === 1 && back.components === 1 && back.unlocked
  && errs.length === 0;
process.exit(ok ? 0 : 1);
