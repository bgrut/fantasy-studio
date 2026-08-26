import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
const J = process.env.J;
const spec = await (await fetch(`http://127.0.0.1:8789/games/${J}/dist/spec.json`)).json();
const goal = (spec.world.level||{}).goal;
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/`,{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
const res = await p.evaluate(async (goal)=>{
  // hoover every remaining collectible, then walk the beacon
  for (let k=0;k<12;k++) {
    const ob = window.__game.objectives();
    if (!ob.left || !ob.left.length) break;
    window.__game.tp(ob.left[0][0], ob.left[0][2]);
    await new Promise(r=>setTimeout(r,900));
  }
  window.__game.tp(goal[0], goal[1]);
  await new Promise(r=>setTimeout(r,1500));
  let won = window.__game.quest().won;
  if (!won) {
    // second lap: pickups have a radius; a tp can land a hair outside it
    for (let k=0;k<12;k++) {
      const ob = window.__game.objectives();
      if (!ob.left || !ob.left.length) break;
      window.__game.tp(ob.left[0][0]+0.4, ob.left[0][2]+0.4);
      await new Promise(r=>setTimeout(r,1200));
    }
    window.__game.tp(goal[0]+0.5, goal[1]+0.5);
    await new Promise(r=>setTimeout(r,2500));
    won = window.__game.quest().won;
  }
  const dbg = { quest: window.__game.quest(), left: (window.__game.objectives()||{}).left };
  // sample the camera during the flyover: an orbit means the bearing MOVES
  const pp = window.__game.pos();
  const bear = () => Math.atan2(window.__camera.position.x - pp[0],
                                window.__camera.position.z - pp[2]);
  const a0 = bear();
  await new Promise(r=>setTimeout(r,1600));
  const a1 = bear();
  return { won, dbg, orbitDeg: +((a1 - a0) * 180 / Math.PI).toFixed(1) };
}, goal);
console.log('flyover:', JSON.stringify(res),
  res.won && Math.abs(res.orbitDeg) > 20 ? 'PASS — camera orbits the win' : 'CHECK');
await p.screenshot({ path: process.env.SP + '/flyover.jpg', type:'jpeg', quality:92 });
await b.close();
