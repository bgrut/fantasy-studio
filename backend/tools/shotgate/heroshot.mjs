// The hero as the player sees it: boot a job, walk three seconds, read the
// hero's name, box, gait and lean, and the bodies of the cast, and shoot.
//   J=<job id> node heroshot.mjs        writes hero_<J>.png beside this file
import puppeteer from 'puppeteer-core';
if (!process.env.J) { console.log('heroshot: J=<job> is needed'); process.exit(1); }
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?noguide=1', { waitUntil:'domcontentloaded', timeout:120000 });
await wait(9000);
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await wait(3000);
if (process.env.ORBIT) {   // drag to look: bring the camera round to the front, low, so the walk is seen as a player circling would see it
  await p.mouse.move(640, 380); await p.mouse.down(); await p.mouse.move(640 + Number(process.env.ORBIT), 300, { steps: 24 }); await p.mouse.up(); await wait(600);
}
await p.keyboard.down('KeyW'); await wait(2500);
const mid = await p.evaluate(() => { const f = window.__game.facts(); return { hero: f.hero, dims: f.player_dims, gait: f.gait, lean: f.lean, arms: f.arms, ride: f.ride, bodies: f.bodies, cast: (f.npc_weight || []).slice(0, 6) }; });
await p.screenshot({ path: 'hero_' + process.env.J + '.png' });
await p.keyboard.up('KeyW'); await wait(1200);
const still = await p.evaluate(() => { const f = window.__game.facts(); return { gait: f.gait, lean: f.lean }; });
console.log('hero      :', mid.hero, '| box', JSON.stringify(mid.dims), '| standing', mid.dims && mid.dims[1] >= Math.max(mid.dims[0], mid.dims[2]) * 0.9);
console.log('walking   :', JSON.stringify(mid.gait), '| lean', JSON.stringify(mid.lean), '| arms from down', JSON.stringify(mid.arms), '| hip ride', mid.ride);
console.log('still     :', JSON.stringify(still.gait));
console.log('bodies    :', JSON.stringify(mid.bodies), '| cast', JSON.stringify(mid.cast));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
