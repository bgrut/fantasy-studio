// A player's tour of a factory build, shot at the moments that sell it:
// the title card, the first-person start, the starter line running, the
// overhead, and a second face. Same script for the demo and a studio job.
//   URL=http://127.0.0.1:8790/ TAG=demo node tour.mjs   -> renders/tour_<tag>_<n>.png
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', TAG = process.env.TAG || 'demo';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const shot = async (n) => { await p.screenshot({ path: 'renders/tour_' + TAG + '_' + n + '.png' }); };
await p.goto(URL + '?fresh=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
await wait(7000); await shot('1_title');
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await wait(9000); await shot('2_reveal_or_start');
await p.evaluate(() => { document.getElementById('tutor')?.classList.remove('on'); const F = window.__factory; if (F && F.ageHints) F.ageHints(); });
await wait(12000); await shot('3_first_person');
// the nearest seam on the home face, up close, before leaving it
try {
  const near0 = await p.evaluate(() => { const F = window.__factory; const f = F.player.face; const cells = F.cells[f]; let best = null, bd = 1e9;
    for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (cells[i][j].t === F.TYPES.NODE) { const d = Math.abs(i - F.N / 2) + Math.abs(j - F.N / 2); if (d < bd) { bd = d; best = [f, i, j]; } }
    if (!best) return null; F.goFace(best[0], Math.max(0, best[1] - 3), best[2], 1.7); return best; });
  await wait(2500); await shot('3b_home_seam'); console.log('home seam :', JSON.stringify(near0));
} catch (e) { errs.push('home seam: ' + e.message.slice(0, 80)); }
await p.keyboard.press('Tab'); await wait(1500); await shot('4_overhead'); await p.keyboard.press('Tab'); await wait(800);
try { await p.evaluate(() => { const F = window.__factory; F.goFace(2, 4, Math.floor(F.N / 2), 2.4); }); await wait(2500); await shot('5_second_face'); } catch (e) { errs.push('goFace: ' + e.message.slice(0, 80)); }
// the seam up close: the nearest seam on the face the player stands on, looked at from a tile away
try {
  const near = await p.evaluate(() => { const F = window.__factory; const f = F.player.face; const cells = F.cells[f]; let best = null, bd = 1e9;
    for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (cells[i][j].t === F.TYPES.NODE) { const pi = Number.isFinite(F.player.i) ? F.player.i : F.N / 2, pj = Number.isFinite(F.player.j) ? F.player.j : F.N / 2; const d = Math.abs(i - pi) + Math.abs(j - pj); if (d < bd) { bd = d; best = [f, i, j]; } }
    if (!best) return null; F.goFace(best[0], Math.max(0, best[1] - 3), best[2], 1.7); return best; });   // three tiles back along the face's u axis, which is where goFace looks
  await wait(2500); await shot('6_seam'); console.log('seam      :', JSON.stringify(near));
} catch (e) { errs.push('seam: ' + e.message.slice(0, 80)); }
const facts = await p.evaluate(() => { const f = window.__game.facts(); return { fps: f.fps, plating: f.plating, warmed: f.warmed, weathered: f.weathered, runs: f.runs }; });
console.log('facts     :', JSON.stringify(facts).slice(0, 300));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
