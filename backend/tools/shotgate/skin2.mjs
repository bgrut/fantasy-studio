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
  window.__scene.traverse(o=>{ if(o.isSkinnedMesh&&o.skeleton&&!sm){
    const e=o.matrixWorld.elements; if(Math.hypot(e[12]-pos[0],e[14]-pos[2])<4) sm=o; } });
  if(!sm) return {err:'none'};
  const g=sm.geometry, sk=sm.skeleton;
  const hi=sk.bones.findIndex(x=>x.name==='hand_L');
  if(hi<0) return {err:'no hand_L'};
  const si=g.attributes.skinIndex, sw=g.attributes.skinWeight, ps=g.attributes.position;
  // vertices most influenced by hand_L
  const picks=[];
  for(let i=0;i<si.count && picks.length<400;i++){
    for(let k=0;k<4;k++) if(si.getComponent(i,k)===hi && sw.getComponent(i,k)>0.5){ picks.push(i); break; }
  }
  if(!picks.length) return {err:'no vertex is >50% weighted to hand_L', hand_index:hi};
  const V=sm.position.constructor; // Vector3
  const bind=[], skinned=[];
  const apply = sm.applyBoneTransform ? 'applyBoneTransform' : 'boneTransform';
  for(const i of picks){
    const v=new V().fromBufferAttribute(ps,i);
    bind.push(v.clone());
    const s=new V().fromBufferAttribute(ps,i);
    sm[apply](i,s); skinned.push(s);
  }
  const mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
  return {
    api: apply,
    hand_verts_sampled: picks.length,
    bind_x_mean:   +mean(bind.map(v=>v.x)).toFixed(3),
    skinned_x_mean:+mean(skinned.map(v=>v.x)).toFixed(3),
    bind_y_mean:   +mean(bind.map(v=>v.y)).toFixed(3),
    skinned_y_mean:+mean(skinned.map(v=>v.y)).toFixed(3),
    moved: +mean(skinned.map((v,i)=>v.distanceTo(bind[i]))).toFixed(4),
    note:'moved ~0 means the MESH is not following the skeleton'
  };
}),null,1));
await b.close();
