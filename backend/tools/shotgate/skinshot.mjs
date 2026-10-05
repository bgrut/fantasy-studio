// Character skin up close: the hero's face and chest, the hero full length,
// and the nearest NPC, from a pinned camera in daylight.
//   J=job_N OUT=<dir> TAG=<name> node skinshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 11000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1200));
const pin = (o) => p.evaluate((o) => {
  const g = window.__game, pp = g.pos(), yaw = g.heading();
  // in front of the hero, looking back at them
  const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
  window.__camPin = { pos: [pp[0] + fx * o.d + Math.cos(yaw) * o.s, pp[1] + o.h, pp[2] + fz * o.d - Math.sin(yaw) * o.s], look: [pp[0], pp[1] + o.lh, pp[2]] };
}, o);
await pin({ d: 1.05, s: 0.25, h: 1.55, lh: 1.45 });
await new Promise(r => setTimeout(r, 900));
await p.screenshot({ path: `${OUT}/${TAG}_face.jpg`, type: 'jpeg', quality: 92 });
await pin({ d: 2.6, s: 0.6, h: 1.2, lh: 0.95 });
await new Promise(r => setTimeout(r, 900));
await p.screenshot({ path: `${OUT}/${TAG}_body.jpg`, type: 'jpeg', quality: 92 });
const npc = await p.evaluate(() => {
  const g = window.__game, refs = g.npcRefs ? g.npcRefs() : [];
  const pp = g.pos();
  let best = null, bd = 1e9;
  for (const r of refs) { const q = r.pos || (r.obj && r.obj.position && r.obj.position.toArray()); if (!q) continue;
    const d = Math.hypot(q[0] - pp[0], q[2] - pp[2]); if (d < bd) { bd = d; best = { q, name: r.name || r.kind } }; }
  if (!best) return null;
  // from the animal's far side, so the hero is never between
  const q = best.q, ax = q[0] - pp[0], az = q[2] - pp[2], al = Math.hypot(ax, az) || 1;
  window.__camPin = { pos: [q[0] + ax / al * 1.8 + az / al * 0.8, q[1] + 1.1, q[2] + az / al * 1.8 - ax / al * 0.8], look: [q[0], q[1] + 0.7, q[2]] };
  return best.name;
});
await new Promise(r => setTimeout(r, 900));
if (npc) await p.screenshot({ path: `${OUT}/${TAG}_npc.jpg`, type: 'jpeg', quality: 92 });
console.log(TAG, 'npc', npc, JSON.stringify(errs.slice(0, 3)));
await b.close();
