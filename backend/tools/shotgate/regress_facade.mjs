// Regression gate for the facade work.
//  - mansion (INTERIOR level): must be untouched — the facade pass and the
//    night-city env lift are both supposed to be gated off for it.
//  - city: stealing a car must still work, since the demo ends by driving away.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const [cityJob, intJob, tag] = process.argv.slice(2);
const out = `C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend/tools/shotgate/regress_${tag}`;
fs.mkdirSync(out, { recursive: true });

const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });

async function open(job) {
  const p = await b.newPage();
  await p.setViewport({ width: 1280, height: 720 });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message.slice(0, 250)));
  await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
  await new Promise(r => setTimeout(r, 5000));
  await p.click('#startbtn').catch(() => {});
  await new Promise(r => setTimeout(r, 6000));
  return { p, errs };
}

// ── interior: alive, lit the same way, guards patrolling
{
  const { p, errs } = await open(intJob);
  const alive = await p.evaluate(() => typeof window.__game);
  const env = await p.evaluate(() => ({
    envI: window.__scene.environmentIntensity,
    interior: !!(window.__game.view),
    npcs: window.__game.npcs().length,
    guards: window.__game.npcs().filter(n => n.behavior === 'guard').length,
    quest: window.__game.quest(),
  }));
  await p.screenshot({ path: `${out}/interior.png` });
  console.log('INTERIOR alive=' + alive, JSON.stringify(env), 'errs=' + errs.length, errs);
  await p.close();
}

// ── city: steal a car
{
  const { p, errs } = await open(cityJob);
  const alive = await p.evaluate(() => typeof window.__game);
  const cars = await p.evaluate(() => window.__game.cars());
  console.log('CITY alive=' + alive, 'cars=' + cars.length);
  let stole = false, before = null, after = null;
  if (cars.length) {
    const c = cars[0];
    await p.evaluate(([x, z]) => window.__game.tp(x, z), [c.x + 1.6, c.z + 1.6]);
    await new Promise(r => setTimeout(r, 2500));
    before = await p.evaluate(() => ({ driving: window.__game.driving(),
                                       near: window.__game.nearCar() }));
    await p.keyboard.press('KeyE');
    await new Promise(r => setTimeout(r, 2000));
    after = await p.evaluate(() => ({ driving: window.__game.driving() }));
    stole = after.driving === true;
    if (!stole) {   // nudge onto the car and retry once
      await p.evaluate(([x, z]) => window.__game.tp(x, z), [c.x, c.z]);
      await new Promise(r => setTimeout(r, 2000));
      await p.keyboard.press('KeyE');
      await new Promise(r => setTimeout(r, 2000));
      after = await p.evaluate(() => ({ driving: window.__game.driving() }));
      stole = after.driving === true;
    }
  }
  await p.screenshot({ path: `${out}/car.png` });
  console.log('CAR STEAL before=' + JSON.stringify(before), 'after=' + JSON.stringify(after),
              'STOLE=' + stole, 'errs=' + errs.length, errs);
  await p.close();
}
await b.close();
