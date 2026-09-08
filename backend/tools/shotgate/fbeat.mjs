// The reveal, the weather, and the sound. None of these change a number the
// sim reports, so each is checked at the level it exists on: the intro holds
// the camera in orbit and the card on screen, then hands over; weather puts
// particles in the air on every world and they fall the right way on the
// underside; the mixer wakes on a click and follows the factory.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760',
        '--autoplay-policy=no-user-gesture-required'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
p.on('console', m => { const u = (m.location() && m.location().url) || '';
  if (m.type()==='error' && !/favicon/i.test(u)) errs.push('console: '+m.text().slice(0,160)); });
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
await p.goto(URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });

// ── 1. the reveal: card up, camera out, then control ──────────────────────
// wait for BOOT, not for a clock: module load plus PMREM plus eight thumbnail
// renders is not a fixed cost, and the intro clock only starts once it is done
for (let k = 0; k < 60; k++) {
  if (await p.evaluate(()=>typeof window.__game === 'object')) break;
  await new Promise(r=>setTimeout(r,200));
}
await new Promise(r=>setTimeout(r,1200));                 // mid-intro
const mid = await p.evaluate(()=>({
  intro: window.__game.facts().intro,
  card: document.getElementById('title').classList.contains('on'),
  name: document.querySelector('#title b').textContent,
  camDist: +window.__camera.position.length().toFixed(1),
  HALF: window.__factory.HALF,
  hudDim: +getComputedStyle(document.getElementById('hud')).opacity < 0.5,
}));
console.log('reveal    : card', mid.card ? 'up' : 'DOWN', JSON.stringify(mid.name),
            '| camera', mid.camDist, 'out (world is', mid.HALF + ')',
            '| intro', mid.intro + 's left | hud stepped back:', mid.hudDim);
await new Promise(r=>setTimeout(r,3500));                 // it should be over
const after = await p.evaluate(()=>({
  intro: window.__game.facts().intro,
  card: document.getElementById('title').classList.contains('on'),
  camDist: +window.__camera.position.length().toFixed(1),
  // "handed over" means the camera is AT the player, not merely closer than
  // some multiple of HALF — a player standing off-centre on a face is farther
  // from the origin than that multiple, and the first assertion was wrong
  atPlayer: +window.__camera.position.distanceTo(window.__factory.player.pos).toFixed(2),
}));
console.log('handed off: card', after.card ? 'STILL UP' : 'down', '| intro', after.intro,
            '| camera', after.atPlayer, 'm from the player');
// and it skips on input: replay, press a key, check it ended
const skip = await p.evaluate(async ()=>{
  const F = window.__factory;
  F.playIntro('SKIP TEST', 'x');
  await new Promise(r => setTimeout(r, 300));
  const during = window.__game.facts().intro;
  dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW' }));
  await new Promise(r => setTimeout(r, 150));
  return { during, after: window.__game.facts().intro };
});
console.log('skippable : intro', skip.during, '-> key ->', skip.after);

// ── 2. weather: every world has some, and it falls toward the face ─────────
const wx = await p.evaluate(async ()=>{
  const F = window.__factory;
  F.addCores(20);
  const out = [];
  for (let k = 0; k < F.WORLDS.length; k++) {
    if (k !== F.worldIdx) F.travelTo(k);
    F.endIntro();
    // stand on the UNDERSIDE, so "down" is world +Y
    F.player.face = 1;
    await new Promise(r => setTimeout(r, 2200));
    const f = window.__game.facts();
    out.push({ world: f.world, alive: f.particles, fall: f.weather && f.weather.fall });
  }
  return out;
});
for (const w of wx) console.log('weather   :', w.world.padEnd(8), w.alive, 'particles in the air',
                                '| fall', w.fall);

// ── 3. sound: wakes on a click, follows the belts, mutes on M ─────────────
const snd = await p.evaluate(async ()=>{
  const F = window.__factory;
  const before = window.__game.facts().audio;
  document.querySelector('canvas').dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  const woke = window.__game.facts().audio;
  // the belt layer follows the belt count: build some and let a tick pass
  const TY = F.TYPES;
  for (let i = 4; i < Math.min(F.N - 4, 30); i++)
    if (F.cells[0][i][4].t === TY.EMPTY) F.place(0, i, 4, TY.BELT, 0);
  for (let k = 0; k < 3; k++) F.step();
  await new Promise(r => setTimeout(r, 1200));
  const beltGain = F.AUDIO.belts ? +F.AUDIO.belts.gain.value.toFixed(3) : null;
  let pinged = true;
  try { F.sfxSold(F.TYPES.INGOT); } catch (e) { pinged = false; }
  dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyM' }));
  await new Promise(r => setTimeout(r, 100));
  const muted = window.__game.facts().audio.muted;
  const masterGain = F.AUDIO.master ? F.AUDIO.master.gain.value : null;
  dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyM' }));
  return { before, woke, beltGain, pinged, muted, masterGain };
});
console.log('sound     : before click ready=' + snd.before.ready,
            '| after click ready=' + snd.woke.ready, 'state=' + snd.woke.state,
            '| belt layer', snd.beltGain, '| ping ok', snd.pinged,
            '| M mutes:', snd.muted, 'master', snd.masterGain);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'beat.png' });
await b.close();

const ok = mid.card && mid.intro > 0 && mid.camDist > mid.HALF * 2 && mid.hudDim
  && !after.card && after.intro === 0 && after.atPlayer < 0.5
  && skip.during > 0 && skip.after === 0
  && wx.length >= 4 && wx.every(w => w.alive > 3)
  && !snd.before.ready && snd.woke.ready && snd.beltGain !== null && snd.beltGain > 0
  && snd.pinged && snd.muted && snd.masterGain === 0
  && errs.length === 0;
process.exit(ok ? 0 : 1);
