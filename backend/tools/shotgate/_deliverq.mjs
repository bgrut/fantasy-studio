// A delivery can be made: J=job_N node _deliverq.mjs. Walks to each drop (a doorstep, a
// bench under a lantern, a roof pad), holds E, and checks the drop counts as done and the
// parcel is left there. Prints PASS or FAIL.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts && document.getElementById('startbtn')))) break; await w(500); }
await w(2500); await p.click('#startbtn').catch(() => {}); await w(3500);
const panels = () => p.evaluate(() => window.__repair ? window.__repair().panels : null);
const P0 = await panels();
if (!P0) { console.log('no repair panels; FAIL'); await b.close(); process.exit(1); }
const drops = await p.evaluate(() => { const out = []; window.__scene.traverse(o => { const t = o.userData && o.userData.fsTag; if (t && /doorstep|drop|landing/.test(t.name)) out.push([o.position.x, o.position.y, o.position.z, o.rotation.y, t.name]); }); return out; });
console.log('drops', drops.length, drops.map(d => d[4]).join(','));
let made = 0;
for (const [x, y, z, ry, name] of drops.slice(0, 2)) {
  const before = (await panels()).filter(q => q[2]).length;
  // a teleport can be lost on a starved frame: again until the hero is there
  for (let a = 0; a < 4; a++) {
    await p.evaluate((x, y, z, ry, roof) => {
      const tx = x + Math.sin(ry) * 0.9, tz = z + Math.cos(ry) * 0.9;
      if (roof && window.__game.tpy) window.__game.tpy(x, y + 1.2, z); else window.__game.tp(tx, tz);
    }, x, y, z, ry, name === 'landing pad');
    await w(900);
    if (await p.evaluate((x, z) => { const q = window.__game.pos(); return Math.hypot(q[0] - x, q[2] - z) < 2.2; }, x, z)) break;
  }
  if (process.env.DBG) console.log('   at', JSON.stringify(await p.evaluate((x, z) => { const q = window.__game.pos(); const st = window.__game.objectives ? window.__game.objectives() : null; return { pos: q.map(v => +v.toFixed(2)), d: +Math.hypot(q[0] - x, q[2] - z).toFixed(2), bar: (document.getElementById('fsrpT') || {}).textContent, step: st && st.step }; }, x, z)));
  await p.keyboard.down('KeyE'); await w(2600); await p.keyboard.up('KeyE'); await w(600);
  const after = (await panels()).filter(q => q[2]).length;
  const parcel = await p.evaluate((x, z) => { let shown = false; window.__scene.traverse(o => { const t = o.userData && o.userData.fsTag; if (t && /doorstep|drop|landing/.test(t.name) && Math.hypot(o.position.x - x, o.position.z - z) < 0.1) o.traverse(c => { if (c.isGroup && c !== o && c.visible && c.children.length === 3) shown = true; }); }); return shown; }, x, z);
  console.log((after > before && parcel ? '  ok   ' : '  FAIL ') + name + ' at ' + x.toFixed(1) + ',' + z.toFixed(1) + ': done ' + before + ' -> ' + after + ', parcel left ' + parcel);
  if (after > before && parcel) made++;
}
console.log(errs.length ? 'page errors: ' + errs[0] : 'no page errors');
const ok = made === Math.min(2, drops.length) && drops.length > 0 && !errs.length;
console.log(ok ? 'PASS' : 'FAIL');
await b.close(); process.exit(ok ? 0 : 1);
