// The flagship on a sofa: a controller drives the game, Start pauses it, and
// the settings it pauses into are kept. The pad is a fake injected before the
// page runs (navigator.getGamepads), driven like a player would drive a real
// one, so every check goes through the same poll the real pad does.
//   URL=http://127.0.0.1:8790/ node fpad.mjs      (or J=<job> for a studio build)
import puppeteer from 'puppeteer-core';
const URL = process.env.J ? 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/' : (process.env.URL || 'http://127.0.0.1:8790/');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.evaluateOnNewDocument(() => {
  const btn = () => ({ pressed: false, value: 0, touched: false });
  window.__fakePad = { id: 'fake pad', index: 0, connected: true, mapping: 'standard', timestamp: 0,
                       axes: [0, 0, 0, 0], buttons: Array.from({ length: 17 }, btn) };
  navigator.getGamepads = () => [window.__fakePad];
});
const wait = ms => new Promise(r => setTimeout(r, ms));
const press = (i, on) => p.evaluate((i, on) => { const B = window.__fakePad.buttons[i]; B.pressed = on; B.value = on ? 1 : 0; }, i, on);
const tap = async i => { await press(i, true); await wait(180); await press(i, false); await wait(180); };
const axis = (i, v) => p.evaluate((i, v) => { window.__fakePad.axes[i] = v; }, i, v);
const fails = [];
const check = (ok, what) => { console.log((ok ? '  ok   ' : '  FAIL ') + what); if (!ok) fails.push(what); };
const st = () => p.evaluate(() => ({ pad: window.__pad.state(), pos: window.__factory.player.pos.toArray(),
  fwd: window.__factory.player.fwd.toArray(), f: window.__game.facts() }));

await p.goto(URL + '?fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
for (let i = 0; i < 40; i++) { if (await p.evaluate(() => !!(window.__pad && window.__factory && window.__game))) break; await wait(500); }
await wait(2500);
await p.evaluate(() => { try { window.__factory.tutIdx = 99; } catch (e) {} });   // the foreman steps back
let s0 = await st();
check(s0.pad.active, 'the controller is seen');

// walk and look
await axis(1, -1); await wait(1200); await axis(1, 0); await wait(300);
let s1 = await st();
const moved = Math.hypot(s1.pos[0] - s0.pos[0], s1.pos[1] - s0.pos[1], s1.pos[2] - s0.pos[2]);
check(moved > 2, `the left stick walks: ${moved.toFixed(1)} m`);
await axis(2, 1); await wait(600); await axis(2, 0); await wait(200);
let s2 = await st();
const dot = s1.fwd[0] * s2.fwd[0] + s1.fwd[1] * s2.fwd[1] + s1.fwd[2] * s2.fwd[2];
const turned = Math.acos(Math.max(-1, Math.min(1, dot))) * 180 / Math.PI;
check(turned > 20, `the right stick turns: ${turned.toFixed(0)} degrees`);

// the bumpers change tool
await p.evaluate(() => window.__factory.pickTool('miner'));
await tap(5);
let s3 = await st();
check(s3.pad.tool && s3.pad.tool !== 'miner', `RB changes the tool: miner -> ${s3.pad.tool}`);
await tap(4);
check((await st()).pad.tool === 'miner', 'LB changes it back');

// the triggers build and erase at the crosshair, aimed at open ground: find a
// face tile whose neighbours are all empty and stand on it looking along the face
await p.evaluate(() => {
  const F = window.__factory, E = F.TYPES.EMPTY;
  for (let f = 1; f < 6; f++) for (let i = 4; i < F.N - 4; i++) for (let j = 4; j < F.N - 4; j++) {
    let clear = true;
    for (let a = -3; a <= 3 && clear; a++) for (let c = -3; c <= 3 && clear; c++) if (F.cells[f][i + a][j + c].t !== E) clear = false;
    if (clear) { F.goFace(f, i, j); F.player.pitch = -0.7; return; }
  }
});
await wait(600);
await p.evaluate(() => window.__factory.pickTool('belt'));
const m0 = (await st()).f.machines;
await press(7, true); await wait(250); await press(7, false); await wait(300);
const m1 = (await st()).f.machines;
check(m1 > m0, `RT builds at the crosshair: ${m0} -> ${m1} machines`);
await press(6, true); await wait(250); await press(6, false); await wait(300);
const s4 = await st();
check(s4.f.machines < m1 && s4.pad.tool === 'belt', `LT erases and hands the tool back: ${m1} -> ${s4.f.machines}, tool ${s4.pad.tool}`);

// Y looks from above, B comes back down
await tap(3);
const ov = await p.evaluate(() => window.__pad.state().overhead);
await tap(1);
const back = await p.evaluate(() => window.__pad.state().overhead);
check(ov && !back, 'Y opens the overhead, B leaves it');

// Start pauses: nothing moves and nothing is earned
await wait(1500);
await tap(9);
const pz = await st();
await axis(1, -1); await wait(1500); await axis(1, 0);
const pz2 = await st();
const drift = Math.hypot(pz2.pos[0] - pz.pos[0], pz2.pos[1] - pz.pos[1], pz2.pos[2] - pz.pos[2]);
check(pz.pad.paused && drift < 0.01 && pz2.f.value === pz.f.value, `Start pauses: moved ${drift.toFixed(3)} m, value ${pz.f.value} -> ${pz2.f.value}`);
const shown = await p.evaluate(() => getComputedStyle(document.getElementById('pause')).display !== 'none');
check(shown, 'the pause menu is on screen');
await p.evaluate(() => { const v = document.getElementById('pz-vol'); v.value = '0.3'; v.dispatchEvent(new Event('input', { bubbles: true })); });
await tap(9);
const up = await st();
check(!up.pad.paused, 'Start again resumes');
await wait(2500);
const later = await st();
check(later.f.value >= up.f.value, 'time runs again after the pause');

// the settings are kept
await p.reload({ waitUntil: 'domcontentloaded' });
for (let i = 0; i < 40; i++) { if (await p.evaluate(() => !!window.__pad)) break; await wait(500); }
const kept = await p.evaluate(() => window.__pad.state().settings.vol);
check(Math.abs(kept - 0.3) < 1e-6, `the volume setting survives a reload: ${kept}`);
check(errs.length === 0, 'no page errors' + (errs.length ? ': ' + errs[0] : ''));
await b.close();
console.log(fails.length ? `${fails.length} failed; FAIL` : 'PASS');
process.exit(fails.length ? 1 : 0);
