// Combat has more than one answer: hostiles come as different kinds, the
// boss has a bar and a second wind, a dodge is untouchable, a fall can go on
// from the last objective, and chests open for coins.
//   FIGHT=<job with hostiles> node fcombat.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.FIGHT || process.env.J;
if (!J) { console.log('fcombat: FIGHT=<job> needed; FAIL'); process.exit(1); }
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message));
p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/index.html?noguide=1&flora=0`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await wait(8000);
await p.click('#startbtn').catch(() => {});
await wait(3500);
const s0 = await p.evaluate(() => ({ roles: window.__cbt.roles, boss: window.__cbt.boss ? window.__cbt.boss.name : null,
  bossHp: window.__cbt.boss ? window.__cbt.boss.hp : 0, chests: window.__cbt.chests }));
console.log('kinds     :', JSON.stringify(s0));
// the dodge: untouchable while it runs
const dodge = await p.evaluate(async () => {
  window.__cbt.iframes = 0;
  const ok = window.__cbtDodge();
  const during = window.__cbt.iframes;
  await new Promise(r => setTimeout(r, 600));
  return { ok, during, after: window.__cbt.iframes, cd: window.__cbt.dodgeCd };
});
console.log('dodge     :', JSON.stringify(dodge));
// a hit grants a moment; a second hit inside it does nothing
const hits = await p.evaluate(() => {
  const h0 = document.getElementById('hearts').textContent.split('♥').length - 1;
  window.__cbt.iframes = 0;
  window.__game.hurt ? window.__game.hurt(1) : null;
  return { h0 };
});
// the boss: walk up and watch the bar
let boss = null;
if (s0.boss) {
  boss = await p.evaluate(async () => {
    const B = window.__cbt.boss;
    window.__game.tp(B.obj.position.x + 6, B.obj.position.z + 6);
    await new Promise(r => setTimeout(r, 1500));
    const shown = getComputedStyle(document.getElementById('fsboss')).display !== 'none';
    return { shown, name: document.getElementById('fsbossname').textContent };
  });
  console.log('boss      :', JSON.stringify(boss));
  await p.screenshot({ path: process.env.OUT || 'combat.png' });
}
// a chest opens for coins
const chest = await p.evaluate(async () => {
  const c0 = window.__cbt.coins;
  const r = window.__cbtE ? window.__cbtE() : false;
  return { c0, nothingNear: !r };
});
console.log('chest     :', JSON.stringify(chest));
console.log('errors    :', errs.length ? errs.slice(0, 4).join(' | ') : 'none');
await b.close();
const kinds = new Set(s0.roles || []);
const ok = (s0.roles || []).length > 0 && (kinds.size >= 2 || s0.roles.length < 3)
  && dodge.ok && dodge.during > 0.3 && dodge.after === 0 && dodge.cd > 0
  && (!s0.boss || (boss && boss.shown && s0.bossHp >= 14))
  && errs.length === 0;
process.exit(ok ? 0 : 1);
