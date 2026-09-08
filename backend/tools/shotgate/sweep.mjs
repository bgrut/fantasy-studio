// Live sweep of the night-city brightness dials, so the values get chosen
// from renders instead of guessed one rebuild at a time.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const job = process.argv[2];
const out = 'C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend/tools/shotgate/sweep';
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
await new Promise(r => setTimeout(r, 6000));
await p.evaluate(() => window.__game.tp(117.7, -65.1));
await new Promise(r => setTimeout(r, 1800));
await p.evaluate(() => window.__game.aim(1.57, 0.05));
await new Promise(r => setTimeout(r, 1200));

for (const [env, emi, exp] of [[1.15, 0.85, 0.72], [1.8, 1.1, 0.72],
                               [2.4, 1.3, 0.72], [1.8, 1.1, 0.95],
                               [2.4, 1.3, 0.95], [3.0, 1.4, 0.95]]) {
  await p.evaluate(([e, m, x]) => {
    window.__scene.environmentIntensity = e;
    window.__renderer.toneMappingExposure = x;
    window.__scene.traverse(o => {
      if (o.isMesh && o.material && o.material.map && o.material.map.image &&
          (o.material.map.image.src || '').includes('facade')) {
        o.material.emissiveIntensity = m;
      }
    });
  }, [env, emi, exp]);
  await new Promise(r => setTimeout(r, 900));
  const n = `env${env}_emi${emi}_exp${exp}`.replace(/\./g, 'p');
  await p.screenshot({ path: `${out}/${n}.png` });
  console.log('shot', n);
}
await b.close();
