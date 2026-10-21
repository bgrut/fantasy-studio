// One benchmark game, played: J=job_N OUT=prefix node _benchprobe.mjs
// Prints one JSON line: errors, frame rate, does the hero move, what the
// maker and the designer chose, the frame's light, and writes three shots
// (opening card, the hero's view, from above) for the judge.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
const O = process.env.OUT;
const wait = ms => new Promise(r => setTimeout(r, ms));
const out = { job: process.env.J };
try {
  await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
  for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
  await wait(5000);
  await p.screenshot({ path: `${O}_open.jpg`, type: 'jpeg', quality: 80 });
  await p.click('#startbtn').catch(() => {}); await wait(4500);
  Object.assign(out, await p.evaluate(() => {
    const f = window.__game.facts();
    return { mode: f.mode, vibe: window.__vibe || null, design: window.__design ? window.__design() : null,
             places: (window.__places || []).map(q => q.kind), objectives: (window.__spec.objectives || []).map(o => o.kind + ':' + o.label) };
  }));
  // frame rate over two seconds, and the worst frame: once just after the start (the
  // cold-start hitch, reported) and once settled (the frame rate that is judged)
  const fpsWin = () => p.evaluate(() => new Promise(res => { let n = 0, worst = 0, last = performance.now(); const t0 = last;
    const f = () => { const t = performance.now(); worst = Math.max(worst, t - last); last = t; n++; if (t - t0 < 2000) requestAnimationFrame(f); else res([+(n / ((t - t0) / 1000)).toFixed(1), Math.round(worst)]); }; requestAnimationFrame(f); }));
  const [f0, w0] = await fpsWin(); out.fps_start = f0; out.hitch_ms = w0;
  await wait(6000);
  const [f1, w1] = await fpsWin(); out.fps = f1; out.worst_ms = w1;
  // the hero's view, and the frame's light (mean and spread of luminance); the judged
  // shots are the world alone: every overlay hidden, so the HUD is not what is marked
  const bare = (on) => p.evaluate((on) => { let st = document.getElementById('bench-bare');
    if (on && !st) { st = document.createElement('style'); st.id = 'bench-bare'; st.textContent = 'body > *:not(canvas):not(#app):not(script):not(style){visibility:hidden !important} #app > *:not(canvas){visibility:hidden !important}'; document.head.appendChild(st); }
    if (!on && st) st.remove(); }, on);
  await bare(true); await wait(300);
  await p.screenshot({ path: `${O}_eye.jpg`, type: 'jpeg', quality: 80 });
  await bare(false);
  out.light = await p.evaluate(() => { const c = document.querySelector('canvas'); const g = document.createElement('canvas'); g.width = 64; g.height = 36;
    const x = g.getContext('2d'); try { x.drawImage(c, 0, 0, 64, 36); } catch (e) { return null; }
    const d = x.getImageData(0, 0, 64, 36).data; let s = 0, s2 = 0, n = 0;
    for (let i = 0; i < d.length; i += 4) { const l = (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) / 255; s += l; s2 += l * l; n++; }
    const m = s / n; return { mean: +m.toFixed(3), sd: +Math.sqrt(Math.max(0, s2 / n - m * m)).toFixed(3) }; });
  // does the hero move: hold forward for a second and a half
  const p0 = await p.evaluate(() => window.__game.pos());
  await p.keyboard.down('KeyW'); await wait(1500); await p.keyboard.up('KeyW'); await wait(300);
  const p1 = await p.evaluate(() => window.__game.pos());
  out.moved = +Math.hypot(p1[0] - p0[0], p1[2] - p0[2]).toFixed(2);
  // from above, toward the goal
  await p.evaluate(() => { const L = window.__spec.world.level || {}, q = window.__game.pos(), g = L.goal || [q[0] + 40, q[2]];
    const dx = g[0] - q[0], dz = g[1] - q[2], dl = Math.hypot(dx, dz) || 1;
    window.__camPin = { pos: [q[0] - dx / dl * 26, q[1] + 52, q[2] - dz / dl * 26], look: [q[0] + dx * 0.5, q[1], q[2] + dz * 0.5] }; });   // (52 m: a jungle's kapoks reach past 35)
  await wait(1800); await bare(true); await wait(200);
  await p.screenshot({ path: `${O}_high.jpg`, type: 'jpeg', quality: 80 });
  // and what the sentence is about: the first place it named, or else the goal, from
  // twenty metres off and a little above (the two views above never showed a temple
  // half a map away)
  await p.evaluate(() => { const L = window.__spec.world.level || {}, q = window.__game.pos();
    const pl = (window.__places || []).find(x => !x.start);
    const t = pl ? pl.at : (L.goal || [q[0] + 30, q[2]]);
    const y = window.__hAt ? window.__hAt(t[0], t[1]) : 0;
    const dx = t[0] - q[0], dz = t[1] - q[2], dl = Math.hypot(dx, dz) || 1;
    window.__camPin = { pos: [t[0] - dx / dl * 22, y + 9, t[1] - dz / dl * 22], look: [t[0], y + 3, t[1]] }; });
  await wait(1600);
  await p.screenshot({ path: `${O}_goal.jpg`, type: 'jpeg', quality: 80 });
} catch (e) { out.crash = String(e.message || e).slice(0, 200); }
out.errors = errs;
console.log(JSON.stringify(out));
await b.close();
