// Walk the clock tower's stair from the floor to the clock room, flight by flight: J=job_N node _ctclimb.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(3000); await p.click('#startbtn').catch(() => {}); await wait(3000);
for (let i = 0; i < 120; i++) { if (await p.evaluate(() => { const f = window.__game.facts(); return !f.intro && !f.paused; })) break; await wait(500); }
await wait(1500);
const CT = await p.evaluate(() => ({ w: window.__clockTower.w, top: window.__clockTower.top }));
const L = CT.w / 2 - 0.5;
if (!process.env.NOTP) { await p.evaluate((L) => window.__game.tp3(L, 1.0, -L), L); await wait(1500); }
console.log("start", JSON.stringify(await p.evaluate(() => window.__game.bpos().map(v => +v.toFixed(2)))), JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return { intro: f.intro, paused: f.paused, won: f.won, lost: f.lost }; })));
const bp = () => p.evaluate(() => window.__game.bpos().map(v => +v.toFixed(2)));
// [yaw, test]: walk +z, -x, -z, +x round the tower, then +z onto the clock room floor
const legs = [[Math.PI, q => q[2] > L - 0.1], [Math.PI / 2, q => q[0] < -L + 0.1], [0, q => q[2] < -L + 0.1], [-Math.PI / 2, q => q[0] > L - 0.1], [Math.PI, q => q[2] > 0]];
for (const [i, [yaw, done]] of legs.entries()) {
  await p.evaluate((y) => window.__game.look(y), yaw); await wait(300);
  await p.keyboard.down('KeyW'); let q = await bp(), t = 0;
  for (; t < 60 && !done(q); t++) { await wait(250); q = await bp(); await p.evaluate((y) => window.__game.look(y), yaw); }
  await p.keyboard.up('KeyW'); await wait(400);
  console.log('leg', i, 'at', JSON.stringify(await bp()), t >= 60 ? 'STUCK' : 'ok in ' + (t * 0.25).toFixed(1) + 's', JSON.stringify(await p.evaluate(() => window.__repair ? window.__repair().fixed : null)));
  if (process.env.MEND && i < 3) { await p.keyboard.down('KeyE'); await wait(2800); await p.keyboard.up('KeyE'); await wait(600);
    console.log('  mended', JSON.stringify(await p.evaluate(() => window.__repair().fixed))); }
  await p.screenshot({ path: `${process.env.OUT || 'ctclimb'}_${i}.jpg`, type: 'jpeg', quality: 80 });
}
if (process.env.MEND) {
  await p.evaluate(() => { window.__game.tp3(-0.6, 18.6, -0.9); window.__game.look(Math.PI); }); await wait(1200);
  await p.keyboard.down('KeyE'); await wait(2800); await p.keyboard.up('KeyE'); await wait(600);
  console.log('  movement mended', JSON.stringify(await p.evaluate(() => window.__repair().fixed)));
  await wait(4000); await p.screenshot({ path: `${process.env.OUT || 'ctclimb'}_strike.jpg`, type: 'jpeg', quality: 80 });
  console.log('  after', JSON.stringify(await p.evaluate(() => { const f = window.__game.facts(); return { won: f.won, step: f.step, steps: f.steps }; })));
}
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
