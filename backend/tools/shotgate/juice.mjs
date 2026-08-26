import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,160)));
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
const res = await p.evaluate(async ()=>{
  const baseFov = window.__camera.fov;
  // find an uncollected relic and stand on it
  let spot=null;
  window.__scene.traverse(o=>{ const t=o.userData&&o.userData.fsTag;
    if(!spot && t && /collect|relic|orb|pickup/i.test((t.type||'')+(t.name||''))) spot=o.position; });
  if(!spot){
    // fall back: objectives() may expose remaining positions
    const ob=window.__game.objectives&&window.__game.objectives();
    if(ob&&ob.left&&ob.left.length) spot={x:ob.left[0][0],z:ob.left[0][1]};
  }
  if(!spot) return {found:false, baseFov};
  window.__game.tp(spot.x, spot.z);
  // sample fov at 60Hz for a second: the punch is a dip and recovery
  let minFov=baseFov;
  for(let i=0;i<70;i++){
    await new Promise(r=>setTimeout(r,16));
    minFov=Math.min(minFov, window.__camera.fov);
  }
  await new Promise(r=>setTimeout(r,700));
  return {found:true, baseFov, minFov, backTo:window.__camera.fov,
          collected:(window.__game.objectives()||{}).collected};
});
console.log('pickup punch:', JSON.stringify(res),
  res.found && res.minFov < res.baseFov - 2 && Math.abs(res.backTo - res.baseFov) < 0.5 ? 'PASS' : 'CHECK');
console.log('final errors:', errs.length?errs.join('|'):'none');
await b.close();
