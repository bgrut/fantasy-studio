import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const U = 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/';
await p.goto(U + '?fresh=1', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));

// a real working line laid out in front of the camera, on seams, so smelters
// cook and drills throw sparks
await p.evaluate(()=>{
  const F = window.__factory, TY = F.TYPES;
  F.addValue(400); F.addCores(1);
  const N = F.N, T = F.T, HALF = F.HALF, face = 0;
  const pz = F.player.pos.z, px = F.player.pos.x;
  const bi = Math.floor(px / T + N / 2), bj = Math.floor(-pz / T + N / 2);
  // three parallel lines running away from the camera
  for (let lane = -1; lane <= 1; lane++) {
    const i = bi + lane * 3;
    let j = bj - 3;
    if (i < 2 || i > N - 3) continue;
    F.cells[face][i][j].t = TY.NODE;                 // a seam to stand a rig on
    F.place(face, i, j, TY.MINER, 1);
    for (let k = 1; k <= 3; k++) F.place(face, i, j - k, TY.BELT, 1);
    F.place(face, i, j - 4, TY.SMELTER, 1);
    for (let k = 5; k <= 7; k++) F.place(face, i, j - k, TY.BELT, 1);
    F.place(face, i, j - 8, TY.HUB, 1);
  }
  F.player.pitch = -0.12;
});
await new Promise(r=>setTimeout(r,9000));
const f = await p.evaluate(()=>window.__game.facts());
console.log('particles alive:', f.particles, '| machines', f.machines,
            '| ingots', f.ingots, '| calls', (await0 => 0)(0) || '');
console.log('stats:', JSON.stringify(await p.evaluate(()=>window.__game.stats())));
await p.screenshot({ path: process.env.OUT + '_line.png' });

// and a close look at a single smelter with its stack going
await p.evaluate(()=>{ const F = window.__factory; F.player.pitch = 0.02; });
await new Promise(r=>setTimeout(r,900));
await p.screenshot({ path: process.env.OUT + '_close.png' });
await b.close();
