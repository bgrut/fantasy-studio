// The music bed. After the first gesture the world has a room tone from the
// kit: four pad voices in the world's family, a progression that moves on a
// slow clock, a high line over it. It changes key with the world, and it
// is one gain under the master, so mute takes it with everything else.
//   URL=<demo or job dist>
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760','--autoplay-policy=no-user-gesture-required'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const URL = process.env.URL || (process.env.J ? 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/' : null);
const q = URL.includes('?') ? '&' : '?';

await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(3500);
// 1. the gesture starts the audio; the bed is there, in the home world's family
const s1 = await p.evaluate(async () => {
  const F = window.__factory;
  const before = window.__game.facts().audio;
  F.audioStart();
  await new Promise(r => setTimeout(r, 400));
  const a = window.__game.facts().audio;
  return { before: before.bed, bed: a.bed, state: a.state, fam: F.WORLDS[F.worldIdx].fam };
});
console.log('the bed   :', JSON.stringify(s1.bed), '| context', s1.state, '| world family', s1.fam);

// 2. the progression moves on its clock: push the clock and the chord advances
const s2 = await p.evaluate(async () => {
  const F = window.__factory, bed = F.AUDIO.bed;
  const c0 = bed.chord;
  bed.next = 0; bed.gap = 0;
  await new Promise(r => setTimeout(r, 300));
  const c1 = bed.chord;
  bed.next = 0;
  await new Promise(r => setTimeout(r, 300));
  return { c0, c1, c2: bed.chord, hz: bed.voices.map(v => Math.round(v.o.frequency.value)), wave: bed.voices[0].o.type };
});
console.log('the clock :', 'chord', s2.c0, '->', s2.c1, '->', s2.c2, '| voices at', JSON.stringify(s2.hz), '| wave', s2.wave);

// 3. mute is one gain: the master goes to zero and the bed stays built
const s3 = await p.evaluate(async () => {
  const F = window.__factory;
  F.audioMute(true);
  const m = F.AUDIO.master.gain.value;
  F.audioMute(false);
  return { mutedMaster: m, bedOn: F.AUDIO.bed.on };
});
console.log('mute      :', JSON.stringify(s3));

// 4. another world, another key: the cold world plays in sine at a higher cutoff
await p.goto(URL + q + 'fresh=1&nointro=1&world=2', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(3500);
const s4 = await p.evaluate(async () => {
  const F = window.__factory;
  F.audioStart();
  await new Promise(r => setTimeout(r, 400));
  const bed = F.AUDIO.bed;
  return { fam: bed.fam, wave: bed.voices[0].o.type, cut: Math.round(bed.lp.frequency.value), worldFam: F.WORLDS[F.worldIdx].fam };
});
console.log('world 2   :', JSON.stringify(s4));

// 5. it makes sound. Render six seconds of the bed offline, from the kit
// itself, and read the level: not silent, not hot.
const s5 = await p.evaluate(async () => {
  const kit = await import('./vendor/kit/kit.js');
  const octx = new OfflineAudioContext(1, 44100 * 6, 44100);
  const bed = new kit.Bed(octx, octx.destination);
  bed.family('void', false);
  // six seconds of stepping at the frame rate, all scheduled at t=0 since
  // an offline clock does not move until it renders: the chord lands, the
  // bells fire on their gaps
  for (let k = 0; k < 360; k++) bed.step(1 / 60);
  const buf = await octx.startRendering();
  const d = buf.getChannelData(0);
  let sum = 0, peak = 0;
  for (let i = 0; i < d.length; i++) { sum += d[i] * d[i]; peak = Math.max(peak, Math.abs(d[i])); }
  return { rms: +Math.sqrt(sum / d.length).toFixed(4), peak: +peak.toFixed(3) };
});
console.log('rendered  : rms', s5.rms, '| peak', s5.peak);

// 6. the adventure runtime plays the same bed after START, in its own family
let adv = null;
if (process.env.A) {
  await p.goto('http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/', { waitUntil:'domcontentloaded', timeout:120000 });
  await wait(8000);
  const btn = await p.$('#startbtn');
  if (btn) await btn.click();
  await wait(1500);
  adv = await p.evaluate(() => (window.__audio ? window.__audio().bed : 'no __audio'));
  console.log('adventure :', JSON.stringify(adv), '| mood', await p.evaluate(() => document.body.dataset.mood));
}
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();

const ok = s1.before === null && s1.bed && s1.bed.voices === 4 && s1.bed.level > 0 && s1.bed.on && s1.bed.fam === s1.fam
  && s2.c1 !== s2.c0 && s2.c2 !== s2.c1 && s2.hz.every(h => h > 60)
  && s3.mutedMaster === 0 && s3.bedOn
  && s4.fam === s4.worldFam && s4.fam !== s1.fam
  && s5.rms > 0.004 && s5.peak < 0.6
  && (!process.env.A || (adv && adv.voices === 4 && adv.on))
  && errs.length === 0;
process.exit(ok ? 0 : 1);
