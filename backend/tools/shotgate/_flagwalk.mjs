// Can you walk Crystal Works? Holds W from the same spot on sixteen headings and says how far each got, and where a
// straight walk stopped dead. [URL=] [SECS=5] node _flagwalk.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', SECS = +(process.env.SECS || 5);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(URL + '?fresh=1&noguide=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__factory))) break; await w(500); }
await w(5000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(6000);
const start = await p.evaluate(() => { const q = window.__factory.player.pos; return [q.x, q.y, q.z]; });
const rows = [];
for (let k = 0; k < 16; k++) {
  const ang = k / 16 * Math.PI * 2;
  await p.evaluate((s, ang) => { const P = window.__factory.player; P.pos.set(s[0], s[1], s[2]); P.fwd.set(Math.cos(ang), 0, Math.sin(ang)); }, start, ang);
  await w(150);
  await p.keyboard.down('KeyW');
  const track = [];
  for (let t = 0; t < SECS * 4; t++) { await w(250); track.push(await p.evaluate(() => { const q = window.__factory.player.pos, f = window.__game.facts(); return [q.x, q.z, f.player_face]; })); }
  await p.keyboard.up('KeyW');
  let stalled = null, far = 0;
  for (let t = 0; t < track.length; t++) {
    far = Math.max(far, Math.hypot(track[t][0] - start[0], track[t][1] - start[2]));
    if (t > 1 && !stalled && track[t][2] === track[0][2] && Math.hypot(track[t][0] - track[t - 1][0], track[t][1] - track[t - 1][1]) < 0.05) stalled = [+track[t][0].toFixed(1), +track[t][1].toFixed(1)];
  }
  rows.push({ deg: Math.round(ang * 180 / Math.PI), far: +far.toFixed(1), stalled, face: track[track.length - 1][2] });
}
for (const r of rows) console.log(JSON.stringify(r));
const stops = rows.filter(r => r.stalled).length;
console.log(`stopped dead on ${stops} of ${rows.length} headings`, errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
