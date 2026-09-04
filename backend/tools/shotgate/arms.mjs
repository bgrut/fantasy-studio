import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,7000));
console.log(JSON.stringify(await p.evaluate(()=>{
  // find the player's skeleton
  let sk=null; const pos=window.__game.pos();
  window.__scene.traverse(o=>{ if(o.isSkinnedMesh && o.skeleton && !sk){
    const e=o.matrixWorld.elements;
    if(Math.hypot(e[12]-pos[0], e[14]-pos[2])<4) sk=o.skeleton; } });
  if(!sk) return {err:'no skeleton near player'};
  const names = sk.bones.map(x=>x.name);
  const find = re => sk.bones.find(x=>re.test(x.name));
  const out={bones:names.length, names:names.slice(0,24)};
  const up=[0,1,0];
  function dirOf(a,c){ // world direction from bone a to bone c
    if(!a||!c) return null;
    const A=a.matrixWorld.elements, C=c.matrixWorld.elements;
    const v=[C[12]-A[12], C[13]-A[13], C[14]-A[14]];
    const L=Math.hypot(...v)||1; return v.map(q=>+(q/L).toFixed(3));
  }
  const up_L=find(/uparm_L|upperarm_l|LeftArm/i), lo_L=find(/lowarm_L|forearm_l|LeftForeArm/i);
  const hd_L=find(/hand_L|LeftHand/i);
  out.shoulder_to_elbow = dirOf(up_L, lo_L);
  out.elbow_to_hand = dirOf(lo_L, hd_L);
  if(out.shoulder_to_elbow){
    const d=out.shoulder_to_elbow;
    out.downness = +(-d[1]).toFixed(3);       // 1.0 = straight down, 0 = horizontal
    out.sideness = +Math.abs(d[0]).toFixed(3);// 1.0 = straight out sideways
    out.verdict = out.downness>0.75 ? 'arms hang (good)'
                : out.downness>0.4 ? 'arms angled out (A-pose-ish)'
                : 'arms OUT (T-pose)';
  }
  out.clips = (window.__game.facts?window.__game.facts():{});
  return out;
}),null,1));
await b.close();
