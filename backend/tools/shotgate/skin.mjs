import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,7000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const pos=window.__game.pos(); let sm=null;
  window.__scene.traverse(o=>{ if(o.isSkinnedMesh && o.skeleton && !sm){
    const e=o.matrixWorld.elements;
    if(Math.hypot(e[12]-pos[0], e[14]-pos[2])<4) sm=o; } });
  if(!sm) return {err:'none'};
  const sk=sm.skeleton, f=n=>sk.bones.find(x=>x.name===n);
  const wp=o=>{const e=o.matrixWorld.elements;return [e[12],e[13],e[14]];};
  const hips=f('hips'), hL=f('hand_L'), hR=f('hand_R'), head=f('head');
  const H=wp(hips), L=wp(hL), R=wp(hR), HD=wp(head);
  const height=Math.abs(HD[1]-H[1])*2;   // rough full height
  // how far apart are the HAND BONES
  const boneSpan=Math.hypot(L[0]-R[0], L[2]-R[2]);
  // how wide is the actual MESH
  const g=sm.geometry; g.computeBoundingBox();
  const bb=g.boundingBox, sc=sm.getWorldScale(new (sm.position.constructor)());
  const meshW=(bb.max.x-bb.min.x)*Math.abs(sc.x);
  const meshH=(bb.max.y-bb.min.y)*Math.abs(sc.y);
  // weights: how much of each vertex's weight lands on the arm chain
  const skIdx=g.attributes.skinIndex, skW=g.attributes.skinWeight;
  const armIds=['clav_L','uparm_L','lowarm_L','hand_L','clav_R','uparm_R','lowarm_R','hand_R']
    .map(n=>sk.bones.findIndex(x=>x.name===n)).filter(i=>i>=0);
  let armW=0, tot=0, nVert=skIdx.count;
  for(let i=0;i<nVert;i++){
    for(let k=0;k<4;k++){
      const bi=skIdx.getComponent(i,k), w=skW.getComponent(i,k);
      tot+=w; if(armIds.includes(bi)) armW+=w;
    }
  }
  return {
    hand_bone_span:+boneSpan.toFixed(3),
    mesh_width:+meshW.toFixed(3), mesh_height:+meshH.toFixed(3),
    mesh_width_over_height:+(meshW/meshH).toFixed(3),
    verts:nVert,
    pct_weight_on_arm_chain:+(100*armW/Math.max(tot,1e-6)).toFixed(2),
    note:'arms-down human is ~0.30 wide/tall; T-pose is ~0.95+'
  };
}),null,1));
await b.close();
