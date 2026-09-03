import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1100,700'] });
const p = await b.newPage();
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
// grab a foot bone on the hero
await p.evaluate(()=>{
  window.__scene.traverse(o=>{
    if(window.__FOOT||!o.isSkinnedMesh||!o.skeleton) return;
    let q=o; let isPlayer=false;
    while(q){ if(q.userData&&q.userData.fsTag&&q.userData.fsTag.type==='player'){isPlayer=true;break;} q=q.parent; }
    if(!isPlayer) return;
    for(const bn of o.skeleton.bones) if(/foot|ankle|toe/i.test(bn.name)) { window.__FOOT=bn; break; }
  });
});
console.log('foot bone:', await p.evaluate(()=>window.__FOOT? window.__FOOT.name : 'NOT FOUND'));
// walk forward; sample the foot's WORLD travel vs the body's ground travel.
// A planted foot should be momentarily STATIONARY in world space; if it
// slides backward slower than the body advances, the clip is under-cranked.
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,1500));
console.log(await p.evaluate(async ()=>{
  
  const samples = [];
  for (let i=0;i<90;i++){
    window.__FOOT.updateMatrixWorld(true);
    const m = window.__FOOT.matrixWorld.elements;
    samples.push({ fx:m[12], fz:m[14], px:window.__game.pos()[0], pz:window.__game.pos()[2], t:performance.now() });
    await new Promise(r=>setTimeout(r,16));
  }
  // foot travel relative to the BODY over the window
  let footRel=0, body=0;
  for(let i=1;i<samples.length;i++){
    const a=samples[i-1], c=samples[i];
    body += Math.hypot(c.px-a.px, c.pz-a.pz);
    const rax=a.fx-a.px, raz=a.fz-a.pz, rcx=c.fx-c.px, rcz=c.fz-c.pz;
    footRel += Math.hypot(rcx-rax, rcz-raz);
  }
  return JSON.stringify({ bodyTravel:+body.toFixed(2), footRelTravel:+footRel.toFixed(2),
    ratio:+(footRel/Math.max(body,0.001)).toFixed(2),
    note:'ratio ~1.0 = planted feet; <1 = feet under-cranked (skating forward)' });
}));
await p.keyboard.up('KeyW');
await b.close();
