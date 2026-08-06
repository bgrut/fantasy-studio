// Enter the first venue, then WALK back out. usage: node exitwalk.mjs <jobid>
import puppeteer from 'puppeteer-core';
const job = process.argv[2];
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 200)));
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await sleep(5500); await p.click('#startbtn').catch(() => {}); await sleep(3000);
const spec = await (await fetch(`http://127.0.0.1:8789/games/job_${job}/dist/spec.json`)).json();
const e = spec.world.level.enterables[0];
await p.evaluate(([x, z]) => window.__game.tp(x, z), e.door);
await sleep(1500);
let q = await p.evaluate(() => window.__game.pos());
console.log('after tp to door: x=', q[0].toFixed(1), 'INSIDE=', Math.abs(q[0]) > 400);
// wander the interior, then try every direction to find the way out
let out = false;
for (let round = 0; round < 24 && !out; round++) {
  const k = ['KeyW', 'KeyS', 'KeyA', 'KeyD'][round % 4];
  await p.keyboard.down(k); await sleep(900); await p.keyboard.up(k); await sleep(150);
  q = await p.evaluate(() => window.__game.pos());
  if (Math.abs(q[0]) < 400) out = true;
}
console.log('walked out:', out, 'final x=', q[0].toFixed(1), 'z=', q[2].toFixed(1));
console.log('jewels:', JSON.stringify(await p.evaluate(() => window.__game.objectives().collected)));
await p.screenshot({ path: `exitwalk_${job}.jpg`, type: 'jpeg', quality: 82 });
await b.close();
