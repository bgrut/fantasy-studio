import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,860'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:860});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
const J = process.env.J;
const spec = await (await fetch(`http://127.0.0.1:8789/games/${J}/dist/spec.json`)).json();
const goal = (spec.world.level||{}).goal;
console.log('goal:', goal);
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/`,{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
// locate the escort holder via its inspector tag
const found = await p.evaluate(()=>{
  window.__ESC = null;
  window.__scene.traverse(o=>{ const t=o.userData&&o.userData.fsTag;
    if(!window.__ESC && t && t.type==='npc' && /escort/.test(t.detail||'')) window.__ESC=o; });
  return window.__ESC ? window.__ESC.position.toArray().map(v=>+v.toFixed(1)) : null;
});
console.log('escort found at:', JSON.stringify(found));
// TEST 1: player stays close -> escort walks toward the goal
const walk = await p.evaluate(async (goal)=>{
  const d0 = Math.hypot(goal[0]-window.__ESC.position.x, goal[1]-window.__ESC.position.z);
  for (let i=0;i<8;i++) {
    window.__game.tp(window.__ESC.position.x+2, window.__ESC.position.z+2);
    await new Promise(r=>setTimeout(r,1000));
  }
  const d1 = Math.hypot(goal[0]-window.__ESC.position.x, goal[1]-window.__ESC.position.z);
  return {before:+d0.toFixed(1), after:+d1.toFixed(1), progressed: d1 < d0-3};
}, goal);
console.log('TEST walk-toward-goal:', JSON.stringify(walk), walk.progressed?'PASS':'FAIL');
// TEST 2: player far away -> escort waits
const wait = await p.evaluate(async (goal)=>{
  window.__game.tp(window.__ESC.position.x-40, window.__ESC.position.z-40);
  const a=[window.__ESC.position.x, window.__ESC.position.z];
  await new Promise(r=>setTimeout(r,3000));
  const moved=Math.hypot(window.__ESC.position.x-a[0], window.__ESC.position.z-a[1]);
  return {moved:+moved.toFixed(2), waited: moved < 0.5};
}, goal);
console.log('TEST waits-when-far:', JSON.stringify(wait), wait.waited?'PASS':'FAIL');
// TEST 3: arrival completes the objective (teleport courier to the beacon)
const arrive = await p.evaluate(async (goal)=>{
  window.__game.tp(goal[0]-3, goal[1]-3);
  await new Promise(r=>setTimeout(r,400));
  window.__ESC.position.set(goal[0]-1.5, window.__ESC.position.y, goal[1]-1.5);
  await new Promise(r=>setTimeout(r,2500));
  return {won: document.body.innerText.includes('You') || /complete|won|victory/i.test(document.body.innerText),
          text: (document.querySelector('h1,#winbox') || {}).textContent || document.body.innerText.slice(0,80)};
}, goal);
console.log('TEST arrival:', JSON.stringify(arrive));
await p.screenshot({ path: process.env.SP + '/escort_done.jpg', type:'jpeg', quality:92 });
console.log('final errors:', errs.length?errs.join('|'):'none');
await b.close();
