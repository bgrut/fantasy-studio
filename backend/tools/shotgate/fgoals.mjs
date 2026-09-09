// The progression frame, twelve tiers deep. What has to be true:
//   - a locked machine actually refuses to be built
//   - a RATE goal is held, not reached: the timer resets the instant the rate
//     drops, and only a held stretch completes it
//   - each tier advances on the thing it says it wants and nothing else
//   - rewards (caps, capabilities) derive from the goal index, so they survive
//     a reload without being saved
//   - a world that asks for a capability says so, and opens when it is handed out
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
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'fresh=1',
  { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,5000));

const wait = ms => new Promise(r => setTimeout(r, ms));
const facts = () => p.evaluate(() => window.__game.facts());
const at = (f) => f.goal_index + '/' + f.goal_total + ' ' + JSON.stringify(f.goal);

const f0 = await facts();
console.log('at start  :', at(f0), '| unlocked', f0.unlocked.join(','),
            '| caps', JSON.stringify(f0.upgrade_caps));

// 1. a locked machine must actually refuse to be built
const locked = await p.evaluate(async () => {
  const F = window.__factory;
  const before = window.__game.facts().machines;
  document.querySelector('.tool[data-tool="forge"]').dispatchEvent(
    new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 120));
  return { before, toolAfter: F.tool,
           dimmed: document.querySelector('.tool[data-tool="forge"]').classList.contains('locked'),
           toast: document.getElementById('toast').textContent };
});
console.log('locked    : forge tool selected?', locked.toolAfter === 'forge' ? 'YES (wrong)' : 'no',
            '| dimmed', locked.dimmed, '| said:', JSON.stringify(locked.toast));

// 2. tier 1 is a total
await p.evaluate(() => window.__factory.addValue(60)); await wait(400);
const t1 = await facts();
console.log('bank 60   :', at(t1), '| unlocked', t1.unlocked.join(','));

// 3. tier 2 is a RATE, and it is held. Money does not buy it; a rate under the
//    target holds nothing; a rate over it accumulates; dropping resets to zero
const t2 = await p.evaluate(async () => {
  const F = window.__factory, g = F.GOALS[1];
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.addValue(5000); await w(300);
  const money = window.__game.facts().goal_index;
  F.rateNow = g.rate - 50; await w(1500);
  const under = g.held;
  F.rateNow = g.rate + 100; await w(2200);
  const over = g.held;
  const readout = document.querySelector('#goal .held') && document.querySelector('#goal .held').textContent;
  F.rateNow = 10; await w(700);
  const dropped = g.held;
  g.held = g.hold - 1; F.rateNow = g.rate + 100; await w(1500);
  const f = window.__game.facts();
  F.rateNow = null;
  return { target: g.rate, hold: g.hold, money, under, over: +over.toFixed(2), readout,
           dropped, idx: f.goal_index, goal: f.goal, caps: f.upgrade_caps };
});
console.log('rate tier : ' + t2.target + '/min for ' + t2.hold + 's | +5000 value -> tier',
            t2.money, '| under target held', t2.under, '| over: held', t2.over,
            '(' + t2.readout + ') | dropped ->', t2.dropped, '| held out -> tier', t2.idx,
            '| tick cap', t2.caps.tick);

// 4. tier 3 is a face; tier 4 an alloy; tier 5 three rigs on three seams
const t5 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.player.face = 2; await w(300);
  const face = window.__game.facts().goal_index;
  F.PRICE[TY.ALLOY] = 1.0;                 // the market may already be paying over 1.20; tier 7 must not be met here
  F.bank(TY.ALLOY); await w(300);
  const alloy = window.__game.facts().goal_index;
  // rigs go on NODE tiles; find three seams anywhere and drop a rig on each
  let placed = 0;
  for (let f = 0; f < 6 && placed < 3; f++)
    for (let i = 0; i < F.N && placed < 3; i++)
      for (let j = 0; j < F.N && placed < 3; j++)
        if (F.cells[f][i][j].t === TY.NODE && F.place(f, i, j, TY.MINER, 0)) placed++;
  await w(300);
  const f = window.__game.facts();
  return { face, alloy, placed, idx: f.goal_index, goal: f.goal, caps: f.upgrade_caps };
});
console.log('face/alloy: 2nd face -> tier', t5.face, '| alloy -> tier', t5.alloy,
            '| ' + t5.placed + ' rigs -> tier', t5.idx, '| yield cap', t5.caps.yield);

// 5. tier 6 rate -> rift; tier 7 a sale above 1.20 (a sale AT 1.0 does not count);
//    tier 8 the meltdown total; tier 9 a core hands out the heated drill
const t9 = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const g6 = F.GOALS[5]; g6.held = g6.hold - 0.5; F.rateNow = g6.rate + 100; await w(1200); F.rateNow = null;
  const rift = window.__game.facts();
  F.PRICE[TY.ALLOY] = 1.0; F.bank(TY.ALLOY); await w(300);
  const cheap = window.__game.facts().goal_index;
  F.PRICE[TY.ALLOY] = 1.3; F.bank(TY.ALLOY); await w(300);
  const dear = window.__game.facts();
  F.addValue(F.MELT_MIN + 10); await w(300);
  const melt = window.__game.facts();
  const frost = F.WORLDS.findIndex(x => x.needs === 'heated');
  const rowBefore = frost >= 0 && document.querySelector('#world .wr[data-world="' + frost + '"]').textContent;
  F.addCores(1); await w(400);
  const core = window.__game.facts();
  const rowAfter = frost >= 0 && document.querySelector('#world .wr[data-world="' + frost + '"]').textContent;
  return { riftIdx: rift.goal_index, riftUnlocked: rift.unlocked.includes('rift'),
           cheap, dearIdx: dear.goal_index, smeltCap: dear.upgrade_caps.smelt,
           meltIdx: melt.goal_index, meltUnlocked: melt.unlocked.includes('meltdown'),
           coreIdx: core.goal_index, caps: core.caps, rowBefore, rowAfter };
});
console.log('rate 2    : held out -> tier', t9.riftIdx, '| rift unlocked', t9.riftUnlocked);
console.log('market    : alloy at 1.00 -> tier', t9.cheap, '(no) | at 1.30 -> tier', t9.dearIdx,
            '| smelt cap', t9.smeltCap);
console.log('meltdown  : total -> tier', t9.meltIdx, '| unlocked', t9.meltUnlocked);
console.log('a core    : -> tier', t9.coreIdx, '| caps', t9.caps.join(','),
            '| frost row', JSON.stringify(t9.rowBefore), '->', JSON.stringify(t9.rowAfter));

// 6. tier 10 rate -> scrubber; tier 11 a repaid rift; tier 12 three cores opens the drift
const t12 = await p.evaluate(async () => {
  const F = window.__factory;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const g10 = F.GOALS[9]; g10.held = g10.hold - 0.5; F.rateNow = g10.rate + 100; await w(1200); F.rateNow = null;
  const scrub = window.__game.facts();
  F.riftsPaid = 1; await w(300);
  const stable = window.__game.facts();
  const drift = F.WORLDS.findIndex(x => x.needs === 'drift');
  const driftBefore = drift >= 0 && F.worldCapOk(F.WORLDS[drift]);
  F.addCores(2); await w(400);
  const done = window.__game.facts();
  const driftAfter = drift >= 0 && F.worldCapOk(F.WORLDS[drift]);
  return { scrubIdx: scrub.goal_index, scrubCaps: scrub.caps, stableIdx: stable.goal_index,
           stableCaps: stable.caps, doneIdx: done.goal_index, total: done.goal_total,
           goalText: document.querySelector('#goal b').textContent, drift, driftBefore, driftAfter,
           open: done.worlds_open, cores: done.cores };
});
console.log('rate 3    : -> tier', t12.scrubIdx, '| caps', t12.scrubCaps.join(','));
console.log('rift paid : -> tier', t12.stableIdx, '| caps', t12.stableCaps.join(','));
console.log('3 cores   : -> tier', t12.doneIdx, 'of', t12.total, '| card', JSON.stringify(t12.goalText),
            '| drift', t12.drift < 0 ? 'not offered here' : (t12.driftBefore ? 'open early (wrong)' : 'closed') +
            ' -> ' + (t12.driftAfter ? 'open' : 'still closed'), '| worlds open', t12.open);

// 7. rewards derive from the index: after a reload the caps and capabilities
//    are back without having been saved
await p.goto(URL, { waitUntil:'domcontentloaded' });
await wait(5000);
const back = await facts();
console.log('reloaded  :', at(back), '| unlocked', back.unlocked.length, '| caps',
            JSON.stringify(back.upgrade_caps), '| capabilities', back.caps.join(','));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'goals.png' });
await b.close();

const ok = f0.goal_index === 0 && f0.goal_total === 12 && !f0.unlocked.includes('forge')
  && f0.upgrade_caps.tick === 6
  && locked.toolAfter !== 'forge' && locked.dimmed && /locked/.test(locked.toast)
  && t1.goal_index === 1 && t1.unlocked.includes('splitter')
  && t2.money === 1 && t2.under === 0 && t2.over >= 1.5 && t2.dropped === 0
  && /held/.test(t2.readout || '') && t2.idx === 2 && t2.caps.tick === 8
  && t5.face === 3 && t5.alloy === 4 && t5.placed === 3 && t5.idx === 5 && t5.caps.yield === 8
  && t9.riftIdx === 6 && t9.riftUnlocked && t9.cheap === 6 && t9.dearIdx >= 7 && t9.smeltCap === 6   // the 5000 banked earlier clears tier 8 in the same frame
  && t9.meltIdx === 8 && t9.meltUnlocked && t9.coreIdx === 9 && t9.caps.includes('heated')
  && (t9.rowBefore === false || (/needs heated/.test(t9.rowBefore) && !/needs heated/.test(t9.rowAfter)))
  && t12.scrubIdx === 10 && t12.scrubCaps.includes('scrubber')
  && t12.stableIdx === 11 && t12.stableCaps.includes('stable')
  && t12.doneIdx === 12 && /ALL SYSTEMS/.test(t12.goalText)
  && (t12.drift < 0 || (!t12.driftBefore && t12.driftAfter))
  && back.goal_index === 12 && back.upgrade_caps.tick === 8 && back.upgrade_caps.yield === 8
  && back.upgrade_caps.smelt === 6 && back.caps.length === 3
  && errs.length === 0;
process.exit(ok ? 0 : 1);
