// The progression frame. Two things have to be true: locked machines actually
// refuse to build, and the chain advances on the thing it says it wants — a
// goal list that unlocks everything on the first frame is decoration.
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

const f0 = await p.evaluate(()=>window.__game.facts());
console.log('at start  : goal', JSON.stringify(f0.goal), '| unlocked',
            f0.unlocked.join(','));

// 1. a locked machine must actually refuse to be built
const locked = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let spot = null;
  for (let i = 4; i < F.N - 4 && !spot; i++)
    for (let j = 4; j < F.N - 4 && !spot; j++)
      if (F.cells[0][i][j].t === TY.EMPTY) spot = [i, j];
  // through the UI path, the way a player would: pick the tool, then apply
  const before = window.__game.facts().machines;
  document.querySelector('.tool[data-tool="forge"]').dispatchEvent(
    new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 120));
  const toolAfter = F.tool;
  return { spot, before, toolAfter,
           dimmed: document.querySelector('.tool[data-tool="forge"]').classList.contains('locked'),
           toast: document.getElementById('toast').textContent };
});
console.log('locked    : forge tool selected?', locked.toolAfter === 'forge' ? 'YES (wrong)' : 'no',
            '| dimmed', locked.dimmed, '| said:', JSON.stringify(locked.toast));

// 2. the first goal is a value target, and hitting it unlocks the splitter
const g1 = await p.evaluate(async () => {
  const F = window.__factory;
  F.addValue(60);
  await new Promise(r => setTimeout(r, 500));
  const f = window.__game.facts();
  return { goal: f.goal, idx: f.goal_index, unlocked: f.unlocked,
           toast: document.getElementById('toast').textContent };
});
console.log('banked 60 : goal ->', JSON.stringify(g1.goal), '| unlocked', g1.unlocked.join(','));

// 3. the second goal is the one that matters: it is only satisfied by walking
//    onto another face, not by any amount of value
const g2 = await p.evaluate(async () => {
  const F = window.__factory;
  F.addValue(2000);                       // money cannot buy this one
  await new Promise(r => setTimeout(r, 400));
  const stalled = window.__game.facts();
  F.player.face = 2;                      // now stand somewhere else
  await new Promise(r => setTimeout(r, 400));
  const moved = window.__game.facts();
  return { stalledAt: stalled.goal, stalledUnlocked: stalled.unlocked.length,
           afterWalk: moved.goal, unlocked: moved.unlocked, faces: moved.faces_visited };
});
console.log('with 2000 : still', JSON.stringify(g2.stalledAt),
            '- money does not buy it');
console.log('2nd face  : goal ->', JSON.stringify(g2.afterWalk),
            '| unlocked', g2.unlocked.join(','));

// 3b. a locked control must be invisible on EVERY frame, not most of them:
//     classList.toggle with an undefined force flips instead of clearing, which
//     renders as permanently on
const meltVis = await p.evaluate(async () => {
  let seen = 0;
  for (let k = 0; k < 20; k++) {
    if (document.getElementById('melt').classList.contains('on')) seen++;
    await new Promise(r => requestAnimationFrame(r));
  }
  return { seen, unlocked: window.__game.facts().unlocked.includes('meltdown'),
           value: window.__game.facts().value };
});
console.log('meltdown  : locked, and visible on', meltVis.seen, 'of 20 frames',
            '(value ' + meltVis.value.toFixed(0) + ')');

// 4. and the unlocks survive a reload
await p.goto(URL, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,5000));
const back = await p.evaluate(()=>window.__game.facts());
console.log('reloaded  : goal', JSON.stringify(back.goal), '| unlocked',
            back.unlocked.join(','), '| faces seen', back.faces_visited);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'goals.png' });
await b.close();
const ok = f0.goal_index === 0 && !f0.unlocked.includes('forge')
  && locked.toolAfter !== 'forge' && locked.dimmed && /locked/.test(locked.toast)
  && g1.unlocked.includes('splitter') && g1.idx === 1
  && g2.stalledAt === 'stand on a second face'      // 2000 value did not buy it
  && g2.unlocked.includes('forge') && g2.faces >= 2
  && meltVis.seen === 0 && !meltVis.unlocked
  && back.unlocked.includes('forge') && back.faces_visited >= 2
  && errs.length === 0;
process.exit(ok ? 0 : 1);
