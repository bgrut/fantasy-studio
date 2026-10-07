// THE SHOWREEL (2026-10-07). A game, filmed for a montage: the HUD hidden,
// the hero walking toward the goal, and a camera that moves like a film
// camera rather than a chase camera: a low orbit round the hero, a crane up
// and back over the world, and a slow push toward the goal or the building
// the sentence named. Recorded with the page's own screencast (ffmpeg, which
// is installed) and re-encoded to an H.264 MP4 a video editor takes.
//   J=job_N OUT=<dir> TAG=<name> [SECS=14] [W=1920 H=1080] [RUN=1] node reelshot.mjs
import puppeteer from 'puppeteer-core';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || 'reel';
const SECS = +(process.env.SECS || 14), W = +(process.env.W || 1920), H = +(process.env.H || 1080);
fs.mkdirSync(OUT, { recursive: true });
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', `--window-size=${W},${H}`] });
const p = await b.newPage(); await p.setViewport({ width: W, height: H });
const errs = []; p.on('pageerror', e => errs.push(e.message));
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await sleep(12000);
await p.click('#startbtn').catch(() => {}); await sleep(3500); await p.keyboard.press('g').catch(() => {}); await sleep(600);
// the film camera, driven from inside the page every frame
await p.evaluate((SECS) => {
  document.querySelectorAll('div,span,p,h1,h2,section,canvas.minimap').forEach(e => { if (!e.querySelector('canvas') && e.tagName !== 'CANVAS') e.style.opacity = 0; });
  const G = window.__game, L = window.__landmark || null;
  const t0 = performance.now();
  const ease = x => x < 0 ? 0 : x > 1 ? 1 : x * x * (3 - 2 * x);
  const goalAt = () => { if (L && L.at) return [L.at[0], (L.gy || 0) + (L.h || 6) * 0.35, L.at[1]];
    const s = window.__scene; let g = null; s.traverse(o => { if (!g && o.userData && o.userData.fsTag && (o.userData.fsTag.type === 'goal' || o.userData.fsTag.type === 'objective')) g = o; });
    if (g) { const v = g.getWorldPosition(g.position.clone()); return [v.x, v.y + 2, v.z]; } return null; };
  const goal = goalAt();
  const step = () => {
    const t = (performance.now() - t0) / 1000, u = t / SECS, pp = G.pos();
    let pos, look;
    if (u < 0.38) {                     // 1. a low orbit round the hero
      const k = u / 0.38, a = -0.9 + k * 1.6, r = 3.2 - k * 0.6;
      pos = [pp[0] + Math.sin(a) * r, pp[1] + 1.0 + k * 0.4, pp[2] + Math.cos(a) * r]; look = [pp[0], pp[1] + 1.1, pp[2]];
    } else if (u < 0.7) {               // 2. crane up and back over the world
      const k = ease((u - 0.38) / 0.32), a = 0.7, r = 3 + k * 26;
      pos = [pp[0] + Math.sin(a) * r, pp[1] + 1.4 + k * 16, pp[2] + Math.cos(a) * r]; look = [pp[0], pp[1] + 1 - k * 0.5, pp[2]];
    } else {                            // 3. a slow push toward the goal
      const k = ease((u - 0.7) / 0.3), g = goal || [pp[0], pp[1] + 2, pp[2] + 30];
      const dx = g[0] - pp[0], dz = g[2] - pp[2], d = Math.hypot(dx, dz) || 1;
      const sx = g[0] - dx / d * (34 - k * 16) + dz / d * 6, sz = g[2] - dz / d * (34 - k * 16) - dx / d * 6;
      pos = [sx, g[1] + 8 - k * 4, sz]; look = g;
    }
    window.__camPin = { pos, look };
    if (u < 1.05) requestAnimationFrame(step); else window.__camPin = null;
  };
  requestAnimationFrame(step);
}, SECS);
// the hero walks toward whatever the sentence is about
await p.keyboard.down('KeyW'); if (process.env.RUN) await p.keyboard.down('ShiftLeft');
const webm = `${OUT}/${TAG}.webm`, mp4 = `${OUT}/${TAG}.mp4`;
const rec = await p.screencast({ path: webm });
await sleep(SECS * 1000);
await rec.stop();
await p.keyboard.up('KeyW'); await p.keyboard.up('ShiftLeft');
await b.close();
try {
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'slow', '-movflags', '+faststart', mp4]);
  console.log(TAG, 'reel', mp4, (fs.statSync(mp4).size / 1e6).toFixed(1) + ' MB', 'errors', JSON.stringify(errs.slice(0, 3)));
} catch (e) { console.log(TAG, 'reel webm only', webm, 'ffmpeg:', String(e.message).slice(0, 200)); }
