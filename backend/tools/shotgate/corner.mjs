import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(async ()=>{
  const F = window.__factory, TY = F.TYPES;
  // clear a patch and draw an S: straight, right turn, straight, left turn
  const mid = Math.floor(F.N / 2);
  for (let i = mid - 8; i < mid + 8; i++) for (let j = mid - 8; j < mid + 8; j++)
    if (F.cells[0][i][j].t !== TY.EMPTY) F.removeAt(0, i, j);
  const put = (i, j, d) => F.place(0, i, j, TY.BELT, d);
  let i = mid - 5, j = mid;
  for (let k = 0; k < 4; k++) put(i + k, j, 0);        // east
  put(i + 4, j, 1);                                    // turn
  for (let k = 1; k < 4; k++) put(i + 4, j + k, 1);
  put(i + 4, j + 4, 0);                                // turn back
  for (let k = 1; k < 4; k++) put(i + 4 + k, j + 4, 0);
  F.place(0, i, j - 1, TY.MINER, 0);                   // a feeder, so shapes resolve
  F.cells[0][i][j - 1].t = TY.MINER;
  await new Promise(r => setTimeout(r, 700));
  const shapes = [];
  for (let k = 0; k < 4; k++) shapes.push(F.beltShape(0, i + k, j, F.cells[0][i + k][j]));
  shapes.push('|turn:', F.beltShape(0, i + 4, j, F.cells[0][i + 4][j]));
  // straight down at it, with the build ghost out of the way
  window.__game.inspect(true);
  F.orbit(0.35, 1.42, F.HALF * 2.15);   // near-vertical, so the top face fills the frame
  await new Promise(r => setTimeout(r, 900));
  const counts = F.beltFrames.map(m => m.count);
  return { shapes, batches: counts, calls: window.__game.stats().calls };
}), null, 1));
await new Promise(r=>setTimeout(r,600));
await p.screenshot({ path: process.env.OUT });
await b.close();
