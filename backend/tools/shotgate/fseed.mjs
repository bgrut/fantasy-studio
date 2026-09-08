// The starter line always exists. Seed 7 of the red-moon prompt at grid 20
// scattered its seams so none on the top face had a clear run east, and the
// studio build opened on bare ground with nothing moving. seedLine now grows a
// seam at the head of the first clear run when the scatter left none, and
// this proves it holds across the sizes a spec can ask for and a spread of
// seeds — every world opens with seven machines and a rig on a seam.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';

const rows = [];
for (const grid of [12, 20, 40]) {
  for (const seed of [1, 7, 42, 1337]) {
    await p.goto(URL + q + 'fresh=1&nointro=1&grid=' + grid + '&seed=' + seed,
      { waitUntil:'domcontentloaded', timeout:90000 });
    await new Promise(r => setTimeout(r, 3500));
    const r = await p.evaluate(() => {
      const F = window.__factory, TY = F.TYPES, g = window.__game.facts();
      let rigOnSeam = 0, hubs = 0;
      F.cells.forEach(face => face.forEach(col => col.forEach(c => {
        if (c.t === TY.MINER && c.mesh) rigOnSeam++;
        if (c.t === TY.HUB) hubs++;
      })));
      return { N: F.N, nodes: g.nodes, machines: g.machines, rigOnSeam, hubs };
    });
    rows.push({ grid, seed, ...r });
    console.log('grid ' + String(grid).padStart(2) + ' seed ' + String(seed).padStart(4) + ' : N', r.N,
                '| seams', r.nodes, '| machines', r.machines, '| rig on a seam', r.rigOnSeam, '| hubs', r.hubs);
  }
}
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
const ok = rows.length === 12
  && rows.every(r => r.N === r.grid && r.machines === 7 && r.rigOnSeam >= 1 && r.hubs >= 1 && r.nodes >= 6)
  && errs.length === 0;
process.exit(ok ? 0 : 1);
