// FACADE GATE — the before/after measurement for the OSM building look.
// Loads a built city, teleports to a street corner, and reports the two numbers
// that decide whether a facade change is shippable: FPS and draw calls.
// usage: node facadegate.mjs <jobId> <tag>
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';

const job = process.argv[2], tag = process.argv[3] || 'run';
const outDir = `C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend/tools/shotgate/facade_${tag}`;
fs.mkdirSync(outDir, { recursive: true });

const b = await puppeteer.launch({
  headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', `--window-size=${process.env.VW||1280},${process.env.VH||720}`],
});
const p = await b.newPage();
const VW=+(process.env.VW||1280), VH=+(process.env.VH||720);
await p.setViewport({ width: VW, height: VH });
const errs = [];
p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message.slice(0, 300)));
p.on('console', m => { const t = m.text();
  if (/VALIDATE_STATUS|shader|link|WebGL.*error/i.test(t)) errs.push('CONSOLE: ' + t.slice(0, 300)); });

await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 6000));

const alive = await p.evaluate(() => typeof window.__game);
console.log('alive:', alive);
if (alive !== 'object') { console.log('DEAD RUNTIME', errs); await b.close(); process.exit(1); }

// street corner: pick a spot on an OSM road so the camera sits between facades
const shots = JSON.parse(process.env.SHOTS || '[]');
async function measure(label) {
  // sample fps over ~3s of real frames, then read draw calls for one frame
  const m = await p.evaluate(() => new Promise(res => {
    let n = 0; const t0 = performance.now();
    const tick = () => { n++;
      if (performance.now() - t0 < 3000) requestAnimationFrame(tick);
      else res({ fps: n / ((performance.now() - t0) / 1000),
                 calls: window.__game.stats ? window.__game.stats().calls : -1,
                 tris: window.__game.stats ? window.__game.stats().tris : -1,
                 progs: window.__game.stats ? window.__game.stats().programs : -1, tex: window.__game.stats ? window.__game.stats().textures : -1 }); };
    requestAnimationFrame(tick);
  }));
  console.log(`[${label}] fps=${m.fps.toFixed(1)} calls=${m.calls} tris=${m.tris} programs=${m.progs}`);
  return m;
}

const results = {};
for (const s of shots) {
  await p.evaluate(([x, z]) => window.__game.tp(x, z), [s.x, s.z]);
  await new Promise(r => setTimeout(r, 2000));
  if (s.yaw !== undefined) {
    await p.evaluate(([y, pi]) => window.__game.aim(y, pi), [s.yaw, s.pitch ?? 0.06]);
    await new Promise(r => setTimeout(r, 900));
  }
  await new Promise(r => setTimeout(r, 600));
  results[s.name] = await measure(s.name);
  await p.screenshot({ path: `${outDir}/${s.name}.png` });
  console.log('shot ->', `${outDir}/${s.name}.png`);
}
if (!shots.length) { results.spawn = await measure('spawn');
  await p.screenshot({ path: `${outDir}/spawn.png` }); }

console.log('ERRORS:', errs.length ? JSON.stringify(errs, null, 1) : 'none');
fs.writeFileSync(`${outDir}/metrics.json`, JSON.stringify({ results, errs }, null, 2));
await b.close();
