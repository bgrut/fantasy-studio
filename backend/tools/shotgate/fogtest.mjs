// Live experiment: how much of "buildings look flat" is just noir's fog?
// Patches scene.fog.density on the running game and shoots the same corner.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const job = process.argv[2];
const out = 'C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend/tools/shotgate/fogtest';
fs.mkdirSync(out, { recursive: true });
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 5000));
await p.evaluate(() => window.__game.tp(117.7, -65.1));
await new Promise(r => setTimeout(r, 2500));

for (const d of [0.09, 0.035, 0.018, 0.010, 0.0]) {
  await p.evaluate(v => { window.__scene.fog.density = v; }, d);
  await new Promise(r => setTimeout(r, 900));
  await p.screenshot({ path: `${out}/fog_${String(d).replace('.', 'p')}.png` });
  console.log('shot fog density', d);
}
// and with fog sane + more ambient, to see how dark the walls really are
await p.evaluate(() => { window.__scene.fog.density = 0.014;
  window.__scene.environmentIntensity = 1.1; });
await new Promise(r => setTimeout(r, 900));
await p.screenshot({ path: `${out}/fog_sane_env11.png` });
console.log('shot fog sane + env 1.1');
await b.close();
