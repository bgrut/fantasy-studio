// NON-NEGOTIABLE regression: walk to every glowing door, go inside, come back.
// usage: node enter.mjs <jobid> <outdir>
import puppeteer from 'puppeteer-core';
import fs from 'fs';

const job = process.argv[2], out = process.argv[3] || ('enter_' + job);
fs.mkdirSync(out, { recursive: true });
const errs = [];
const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
});
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message.slice(0, 250)));
const sleep = ms => new Promise(r => setTimeout(r, ms));

await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await sleep(5500);
await p.click('#startbtn').catch(() => {});
await sleep(3000);
console.log('alive:', await p.evaluate(() => typeof window.__game));

const spec = await (await fetch(`http://127.0.0.1:8789/games/job_${job}/dist/spec.json`)).json();
const ents = spec.world.level.enterables || [];
console.log('enterables:', ents.length);

let ok = 0;
for (let i = 0; i < ents.length; i++) {
  const e = ents[i];
  // stand just outside the door, then walk in
  await p.evaluate(([x, z]) => window.__game.tp(x, z), [e.door[0], e.door[1] + 3.2]);
  await sleep(1200);
  const before = await p.evaluate(() => window.__game.pos());
  await p.screenshot({ path: `${out}/${i}a_door_${e.label.replace(/\W+/g, '_')}.jpg`, type: 'jpeg', quality: 82 });
  // step onto the door from each side — the trigger is a radius, and which
  // way "forward" points depends on where the camera happens to be looking
  for (const [dx, dz] of [[0, 0], [0.8, 0], [-0.8, 0], [0, 0.8], [0, -0.8]]) {
    if (Math.abs((await p.evaluate(() => window.__game.pos()))[0]) > 400) break;
    await p.evaluate(([x, z]) => window.__game.tp(x, z), [e.door[0] + dx, e.door[1] + dz]);
    await sleep(900);
  }
  const after = await p.evaluate(() => window.__game.pos());
  const inside = Math.abs(after[0] - before[0]) > 300;   // interiors live far off-map
  console.log(`${e.label}: before x=${before[0].toFixed(1)} after x=${after[0].toFixed(1)} INSIDE=${inside}`);
  if (inside) {
    ok++;
    await sleep(900);
    await p.screenshot({ path: `${out}/${i}b_inside_${e.label.replace(/\W+/g, '_')}.jpg`, type: 'jpeg', quality: 82 });
    // leave via the interior's own doorway (it sits at the room edge)
    for (const [dx, dz] of [[0, 0], [0, 1.2], [0, -1.2], [1.2, 0], [-1.2, 0]]) {
      await p.evaluate(([x, z]) => window.__game.tp(x, z), [e.ox + dx, dz]);
      await sleep(900);
      if (Math.abs((await p.evaluate(() => window.__game.pos()))[0]) < 400) break;
    }
    const back = await p.evaluate(() => window.__game.pos());
    console.log(`  exit -> x=${back[0].toFixed(1)} OUT=${Math.abs(back[0]) < 400}`);
    await p.screenshot({ path: `${out}/${i}c_out_${e.label.replace(/\W+/g, '_')}.jpg`, type: 'jpeg', quality: 82 });
  }
}
console.log('ENTERED OK:', ok, '/', ents.length);
console.log('objectives:', JSON.stringify(await p.evaluate(() => window.__game.objectives())).slice(0, 300));
console.log('ERRORS:', errs.length ? errs : 'clean');
await b.close();
