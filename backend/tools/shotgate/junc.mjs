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
  const mid = Math.floor(F.N / 2);
  for (let i = mid - 9; i < mid + 9; i++) for (let j = mid - 9; j < mid + 9; j++)
    if (F.cells[0][i][j].t !== TY.EMPTY) F.removeAt(0, i, j);
  // two lines converging on one, then a curve away from the merge
  const put = (i, j, d) => F.place(0, i, j, TY.BELT, d);
  const M = { i: mid, j: mid };
  for (let k = 1; k <= 4; k++) put(M.i - k, M.j, 0);           // from the west
  for (let k = 1; k <= 4; k++) put(M.i, M.j - k, 1);           // from the north
  put(M.i, M.j, 0);                                            // the junction
  for (let k = 1; k <= 3; k++) put(M.i + k, M.j, 0);
  put(M.i + 4, M.j, 1);                                        // and a corner
  for (let k = 1; k <= 3; k++) put(M.i + 4, M.j + k, 1);
  F.place(0, M.i - 5, M.j, TY.MINER, 0);
  F.cells[0][M.i - 5][M.j].t = TY.MINER;
  F.place(0, M.i, M.j - 5, TY.MINER, 1);
  F.cells[0][M.i][M.j - 5].t = TY.MINER;
  await new Promise(r => setTimeout(r, 900));
  window.__game.inspect(true);
  F.orbit(0.4, 1.40, F.HALF * 1.7);
  await new Promise(r => setTimeout(r, 900));
  return { shapeAtMerge: F.beltShape(0, M.i, M.j, F.cells[0][M.i][M.j]),
           batches: F.beltFrames.map(m => m.count),
           calls: window.__game.stats().calls };
}), null, 1));
await p.screenshot({ path: process.env.OUT });
await b.close();
