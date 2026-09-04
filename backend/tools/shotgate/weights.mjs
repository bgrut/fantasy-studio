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
  const g=sm.geometry, sk=sm.skeleton, nm=sk.bones.map(x=>x.name);
  const si=g.attributes.skinIndex, sw=g.attributes.skinWeight, ps=g.attributes.position;
  g.computeBoundingBox(); const bb=g.boundingBox;
  // vertices in the OUTER 18% of the bind-pose X extent = the hands/forearms
  const xr=bb.max.x-bb.min.x, cut=bb.min.x+xr*0.18;
  const acc={}, influences=[]; let n=0;
  for(let i=0;i<ps.count;i++){
    if(ps.getX(i) > cut) continue;             // far LEFT side only
    n++; let inf=0;
    for(let k=0;k<4;k++){
      const w=sw.getComponent(i,k); if(w<=0.001) continue;
      inf++; const bn=nm[si.getComponent(i,k)]||'?';
      acc[bn]=(acc[bn]||0)+w;
    }
    influences.push(inf);
  }
  const tot=Object.values(acc).reduce((a,c)=>a+c,0)||1;
  const top=Object.entries(acc).sort((a,c)=>c[1]-a[1]).slice(0,7)
    .map(([k,v])=>[k, +(100*v/tot).toFixed(1)]);
  influences.sort((a,c)=>a-c);
  return { outer_arm_verts:n,
           weight_share_pct: top,
           median_bones_per_vertex: influences[Math.floor(influences.length/2)],
           note:'these are the OUTERMOST arm/hand vertices; weight on chest/spine/hips = the arm is glued to the torso' };
}),null,1));
await b.close();
