// Rank perks and the ending. Each perk has to change the machines: a rig on a
// rich seam yields every tick at rank I, furnaces cook a tick faster at rank
// II, a contract pays two shards at rank III. The works have to play once,
// only when the chain, three cores, three worlds and a five-minute order are
// all done, carry their numbers, and survive a reload.
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

// 1. DEEP BITS: a rig on a rich seam yields every tick at rank I, not at rank 0
const deep = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  let pick = null;
  for (let f = 0; f < 6 && !pick; f++) for (let i = 1; i < F.N - 2 && !pick; i++) for (let j = 1; j < F.N - 1 && !pick; j++) {
    const s = F.cells[f][i][j]; if (s.t === TY.NODE && s.mesh && F.cells[f][i + 1][j].t === TY.EMPTY) pick = [f, i, j];
  }
  const c = F.cells[pick[0]][pick[1]][pick[2]];
  F.place(pick[0], pick[1], pick[2], TY.MINER, 0);
  const to = F.stepTile(pick[0], pick[1], pick[2], 0); F.place(to.face, to.i, to.j, TY.BELT, 0);
  const belt = F.cells[to.face][to.i][to.j];
  const run = () => { let n = 0; for (let k = 0; k < 40; k++) { belt.item = 0; c.rich = 0.9; F.step(); if (belt.item) n++; } return n; };
  const at0 = run();
  F.rank = 1;
  const at1 = run();
  const perks = window.__game.facts().perks;
  return { at0, at1, perks, rankText: document.getElementById('rank').textContent };
});
console.log('deep bits : rich seam yielded', deep.at0, 'of 40 at rank 0 |', deep.at1, 'of 40 at rank I | perks', deep.perks.join(','),
            '| panel', JSON.stringify(deep.rankText));

// 2. TWIN FURNACE: a tick off the cook at rank II; BROKER: two shards at rank III
const more = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const t1 = window.__game.facts().smelt_ticks;
  F.rank = 2;
  const t2 = window.__game.facts().smelt_ticks;
  F.rank = 3; F.shards = 0;
  F.addValue(60); await w(300);
  const c = F.offerContract(TY.INGOT); for (let k = 0; k < c.need; k++) F.bank(TY.INGOT);
  await w(300);
  return { t1, t2, shards: window.__game.facts().shards, said: document.getElementById('toast').textContent, perks: window.__game.facts().perks };
});
console.log('furnace   : smelt ticks', more.t1, '-> rank II', more.t2, '| broker: one contract paid', more.shards, 'shards | said:', JSON.stringify(more.said).slice(0, 90));

// 3. THE WORKS: not before every condition; once when all are met; with the numbers; kept on reload
const works = await p.evaluate(async () => {
  const F = window.__factory;
  const w = ms => new Promise(r => setTimeout(r, ms));
  F.goalIdx = F.GOALS.length; F.addCores(3);
  F.lifetime.longestHold = 320;
  await w(400);
  const early = { done: window.__game.facts().lifetime.works_done, played: window.__game.facts().lifetime.works, worlds: window.__game.facts().lifetime.worlds.length };
  F.visitedWorlds.add(1); F.visitedWorlds.add(2);
  await w(500);
  const f = window.__game.facts();
  const card = document.querySelector('#title b').textContent, sub = document.querySelector('#title small').textContent;
  const up = document.getElementById('title').classList.contains('on');
  F.endIntro();
  // the reveal comes down and the kit's end card stands, with the run on it
  await w(200);
  const endEl = document.getElementById('fs-end');
  const endCard = endEl && endEl.classList.contains('on') ? {
    title: endEl.querySelector('h2').textContent, stats: [...endEl.querySelectorAll('.stat')].map(x => x.textContent),
    buttons: [...endEl.querySelectorAll('button')].map(x => x.textContent), quoted: /\u201c.+\u201d/.test(endEl.querySelector('p').textContent) } : null;
  let linkCap = null, playedOn = null;
  if (endCard) {
    [...endEl.querySelectorAll('button')].find(x => /share/.test(x.textContent)).click();
    await w(100);
    linkCap = document.getElementById('facecap').textContent;
    [...endEl.querySelectorAll('button')].find(x => /play on/.test(x.textContent)).click();
    await w(100);
    playedOn = !endEl.classList.contains('on');
  }
  const goal = document.querySelector('#goal b').textContent;
  const edge = '#' + window.__scene.getObjectByName('worldEdge').material.color.getHexString();
  F.save();
  return { early, played: f.lifetime.works, card, sub, up, goal, edge, toast: document.getElementById('toast').textContent, endCard, linkCap, playedOn, worksCard: window.__game.facts().lifetime.works_card };
});
console.log('the works : before three worlds: done', works.early.done, 'played', works.early.played, '(worlds', works.early.worlds + ')');
console.log('            after: played', works.played, '| card', JSON.stringify(works.card), works.up ? 'up' : 'DOWN', '| under it:', JSON.stringify(works.sub));
console.log('            goal card', JSON.stringify(works.goal), '| edge', works.edge, '| said:', JSON.stringify(works.toast).slice(0, 80) + '...');
console.log('the card  :', JSON.stringify(works.endCard), '| share ->', JSON.stringify(works.linkCap), '| play on ->', works.playedOn ? 'away' : 'STILL UP', '| facts', works.worksCard);

await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const back = await p.evaluate(() => { const f = window.__game.facts(); return { works: f.lifetime.works, contracts: f.lifetime.contracts, hold: f.lifetime.longest_hold, worlds: f.lifetime.worlds.length, rank: f.rank, perks: f.perks.length, goal: document.querySelector('#goal b').textContent }; });
console.log('reloaded  :', JSON.stringify(back));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'works.png' });
await b.close();

const ok = deep.at0 < 40 && deep.at1 === 40 && deep.perks.join(',') === 'DEEP BITS' && /DEEP BITS/.test(deep.rankText)
  && more.t2 === more.t1 - 1 && more.shards === 2 && /two core shards/.test(more.said) && more.perks.length === 3
  && !works.early.done && !works.early.played && works.played && works.card === 'THE WORKS' && works.up && /contracts? kept/.test(works.sub)
  && /WORKS ARE YOURS/.test(works.goal) && works.edge === '#ffd479' && /THE WORKS ARE YOURS/.test(works.toast)
  && works.endCard && /WORKS ARE YOURS/i.test(works.endCard.title) && works.endCard.stats.length === 4 && works.endCard.buttons.length === 3
  && /LINK COPIED/.test(works.linkCap || '') && works.playedOn && works.worksCard
  && back.works && back.contracts >= 1 && back.hold >= 320 && back.worlds >= 3 && back.rank === 3 && back.perks === 3 && /WORKS ARE YOURS/.test(back.goal)
  && errs.length === 0;
process.exit(ok ? 0 : 1);
