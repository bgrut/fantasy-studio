// Verifies the walk -> drive -> walk bridge end to end (2026-08-05).
// Usage: node carsteal.mjs <jobId> [outDir]
import puppeteer from 'puppeteer-core';
import fs from 'fs';

const JOB = process.argv[2];
const OUT = process.argv[3] || './shots';
fs.mkdirSync(OUT, { recursive: true });

const errs = [];
const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
});
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => { errs.push('PAGEERROR: ' + e.message.slice(0, 300)); });
p.on('console', m => {
  const t = m.text();
  if (/VALIDATE_STATUS|Program Info Log|THREE.WebGLProgram|shader/i.test(t))
    errs.push('CONSOLE: ' + t.slice(0, 300));
});

const sleep = ms => new Promise(r => setTimeout(r, ms));
const shot = n => p.screenshot({ path: `${OUT}/${n}.png` });

await p.goto(`http://127.0.0.1:8789/games/job_${JOB}/dist/`,
  { waitUntil: 'networkidle2', timeout: 90000 });
await sleep(6000);
await p.click('#startbtn').catch(() => {});
await sleep(3000);

console.log('alive:', await p.evaluate(() => typeof window.__game));
const cars = await p.evaluate(() => window.__game.cars());
console.log('cars:', JSON.stringify(cars));
if (!cars.length) { console.log('NO CARS — abort'); await b.close(); process.exit(1); }

// stand next to the nearest car, facing it
const c = cars[0];
await p.evaluate(([x, z]) => window.__game.tp(x + 3.0, z + 3.0), [c.x, c.z]);
await sleep(2500);
console.log('near:', JSON.stringify(await p.evaluate(() => window.__game.nearCar())));
console.log('onfoot pos:', JSON.stringify(await p.evaluate(() => window.__game.pos())));
await shot('a_prompt_onfoot');

// press E -> get in
await p.keyboard.press('KeyE');
await sleep(2200);
const driving = await p.evaluate(() => window.__game.driving());
const posIn = await p.evaluate(() => window.__game.pos());
console.log('driving:', driving, 'pos in car:', JSON.stringify(posIn));
await shot('b_in_car');

// DRIVE: hold W for 4 s
await p.keyboard.down('KeyW');
await sleep(4200);
await p.keyboard.up('KeyW');
await sleep(600);
const posDrove = await p.evaluate(() => window.__game.pos());
const moved = Math.hypot(posDrove[0] - posIn[0], posDrove[2] - posIn[2]);
console.log('pos after drive:', JSON.stringify(posDrove), 'MOVED:', moved.toFixed(2), 'm');
await shot('c_after_driving');

// press E -> get out
await p.keyboard.press('KeyE');
await sleep(2500);
const drivingOut = await p.evaluate(() => window.__game.driving());
const posOut = await p.evaluate(() => window.__game.pos());
const carsOut = await p.evaluate(() => window.__game.cars());
console.log('driving after exit:', drivingOut, 'pos:', JSON.stringify(posOut));
console.log('car left at:', JSON.stringify(carsOut[0]));
await shot('d_back_on_foot');

// did the player end up stuck? walk 1.5 s and confirm displacement
await p.keyboard.down('KeyW');
await sleep(1500);
await p.keyboard.up('KeyW');
const posWalk = await p.evaluate(() => window.__game.pos());
const walked = Math.hypot(posWalk[0] - posOut[0], posWalk[2] - posOut[2]);
console.log('walked after exit:', walked.toFixed(2), 'm (>0.5 = not stuck)');
console.log('quest:', JSON.stringify(await p.evaluate(() => window.__game.quest())));
await shot('e_walking_after');

console.log('ERRORS:', errs.length ? JSON.stringify(errs, null, 1) : 'none');
await b.close();
