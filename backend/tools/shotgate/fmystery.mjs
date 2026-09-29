// A MYSTERY (MY=<job>), held to its deduction (2026-09-29).
//
// The case is sound: three or more suspects standing apart, one culprit, every
// innocent missing at least one clue and every clue ruling someone out, so the
// game can be solved from what it shows. Then it is played with the keys a
// player has: E questions a suspect and shows what you notice, Y names nobody
// before the clues are in, the numbered markers are the clues, J opens the
// casebook with them in it, naming an innocent loses and says who it was, and
// on a fresh page (the same case, from the same seed) naming the one who fits
// every clue wins.
//
//   MY=<job> node fmystery.mjs
import puppeteer from 'puppeteer-core';
const MY = process.env.MY;
if (!MY) { console.log('fmystery: MY=<job> needed; FAIL'); process.exit(1); }
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const wait = ms => new Promise(r => setTimeout(r, ms));
const url = 'http://127.0.0.1:8789/games/job_' + MY + '/dist/?noguide=1';
const fails = [];
const check = (ok, what) => { console.log((ok ? '  ok   ' : '  FAIL ') + what); if (!ok) fails.push(what); };
async function open() {
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
  await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 120000 });
  for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(1000); }
  const btn = await p.$('#startbtn'); if (btn) await btn.click();
  await wait(2000);
  return { p, errs };
}
const M = p => p.evaluate(() => window.__game.facts().mystery);
// stand a pace in front of a suspect, then use the keys
async function walkUpTo(p, i) {
  await p.evaluate(i => {
    const [x, z] = window.__game.facts().mystery.where[i];
    const [px, , pz] = window.__game.pos();
    const L = Math.hypot(px - x, pz - z) || 1;
    window.__game.tp(x + (px - x) / L * 1.6, z + (pz - z) / L * 1.6);
  }, i);
  await wait(700);
}
async function key(p, code) { await p.keyboard.press(code); await wait(350); }
async function collectAll(p) {
  const left = await p.evaluate(() => window.__game.objectives().left);
  for (const [x, , z] of left) { await p.evaluate((x, z) => window.__game.tp(x, z), x, z); await wait(700); }
  return left.length;
}

console.log('mystery, job ' + MY);
const { p, errs } = await open();
const m0 = await M(p);
check(!!m0, 'the game is a mystery (facts carry a case)');
if (m0) {
  const S = m0.suspects.length, K = m0.clueCount;
  check(S >= 3 && new Set(m0.suspects).size === S, `${S} suspects, each their own person: ${m0.suspects.join(', ')}`);
  check(K >= 2 && K <= 4, `${K} clues to find`);
  const fit = m0.traits.map(t => t.every((v, c) => v === m0.killerTraits[c]));
  const ci = m0.suspects.indexOf(m0.culprit);
  check(fit.filter(Boolean).length === 1 && fit[ci], `exactly one suspect fits every clue, and it is the culprit (${m0.culprit})`);
  const everyClueCounts = m0.killerTraits.every((v, c) => m0.traits.some((t, i) => i !== ci && t[c] !== v));
  check(everyClueCounts, 'every clue rules at least one innocent out');
  let minGap = 1e9, far = 0;
  const [sx, , sz] = await p.evaluate(() => window.__game.pos());
  for (let i = 0; i < S; i++) {
    far = Math.max(far, Math.hypot(m0.where[i][0] - sx, m0.where[i][1] - sz));
    for (let j = i + 1; j < S; j++) minGap = Math.min(minGap, Math.hypot(m0.where[i][0] - m0.where[j][0], m0.where[i][1] - m0.where[j][1]));
  }
  check(minGap > 3 && far < 45, `the suspects stand apart (closest two ${minGap.toFixed(1)} m) and within reach (farthest ${far.toFixed(0)} m)`);

  // questioning, and no verdict before the clues
  const inn = m0.suspects.findIndex((_, i) => i !== ci);
  await walkUpTo(p, inn);
  await key(p, 'KeyE');
  const said = await p.evaluate(() => { const d = document.getElementById('fsdlgtxt'); return d ? d.textContent : ''; });
  const m1 = await M(p);
  check(m1.questioned.includes(m0.suspects[inn]) && /You notice:/.test(said), `E questions ${m0.suspects[inn]}: "${said.slice(0, 70)}..."`);
  await key(p, 'KeyY');
  check(!(await M(p)).over, 'Y names nobody before the clues are in');

  // the clues
  const n = await collectAll(p);
  const m2 = await M(p);
  check(n === K && m2.clues.length === K && m2.clues.every(c => c.length > 20), `${n} evidence markers picked up, ${m2.clues.length} clues read`);
  check(m2.accusing, 'with the clues in, the last step is to name the killer');
  await key(p, 'KeyJ');
  const book = await p.evaluate(() => ({ open: window.__game.reading().open, text: (document.getElementById('fs_read_b') || {}).textContent || '' }));
  check(book.open && m2.clues.every(c => book.text.includes(c)) && book.text.includes(m0.suspects[inn]), 'J opens the casebook, with every clue and the suspect questioned');
  await key(p, 'KeyJ');

  // the wrong name loses, and says who it was
  await walkUpTo(p, inn);
  await key(p, 'KeyE'); await key(p, 'KeyY');
  const m3 = await M(p);
  check(m3.over === 'lost' && (m3.verdict || '').includes(m0.culprit), `naming an innocent loses: "${(m3.verdict || '').slice(0, 90)}"`);
  check(errs.length === 0, 'no page errors' + (errs.length ? ': ' + errs[0] : ''));
  await p.close();

  // a fresh page: the same case, and the right name wins
  const { p: p2, errs: errs2 } = await open();
  const n0 = await M(p2);
  check(n0 && n0.culprit === m0.culprit, 'the same game is the same case');
  await collectAll(p2);
  await walkUpTo(p2, ci);
  await key(p2, 'KeyE'); await key(p2, 'KeyY');
  const n1 = await M(p2);
  check(n1.over === 'won', `naming the one who fits wins: "${(n1.verdict || '').slice(0, 90)}"`);
  check(errs2.length === 0, 'no page errors on the second page' + (errs2.length ? ': ' + errs2[0] : ''));
}
await b.close();
console.log(fails.length ? `${fails.length} failed; FAIL` : 'PASS');
process.exit(fails.length ? 1 : 0);
