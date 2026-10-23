// Drive forward and compare the direction of travel with the vehicle's nose:
//   J=job_N OUT=prefix node _drivecheck.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(2500);
const a = await p.evaluate(() => window.__game.pos());
await wait(+(process.env.PRE || 0)); const a2 = await p.evaluate(() => window.__game.pos()); a.splice(0, 3, ...a2); await p.keyboard.down('KeyW'); await wait(3000);
await p.screenshot({ path: `${process.env.OUT}_drive.jpg`, type: 'jpeg', quality: 85 });
await p.keyboard.up('KeyW');
const r = await p.evaluate((a) => { const q = window.__game.pos(); let rv = null; window.__scene.traverse(o => { if (o.userData && (o.userData.rover || o.userData.kart)) rv = o; });
  const T = window.__THREE || null; const m = rv ? rv.matrixWorld.elements : null;
  // the model's local +Z axis in the world (matrix column 2)
  const nose = m ? [m[8], m[10]] : null; const mv = [q[0] - a[0], q[2] - a[2]];
  const L = Math.hypot(...mv) || 1, N = nose ? Math.hypot(...nose) : 1;
  return { moved: +L.toFixed(2), cos_travel_vs_plusZ: nose ? +((mv[0] * nose[0] + mv[1] * nose[1]) / L / N).toFixed(2) : null }; }, a);
console.log(JSON.stringify(r)); await b.close();
