import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
await p.goto('http://127.0.0.1:8789/job_1/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const pos=window.__game.pos(); const out={playerPos:pos.map(v=>+v.toFixed(2))};
  const near=[];
  window.__scene.traverse(o=>{
    if(!o.isMesh) return;
    const e=o.matrixWorld.elements, wx=e[12],wy=e[13],wz=e[14];
    const d=Math.hypot(wx-pos[0],wz-pos[2]);
    if(d<8){
      // extract euler-ish tilt: how far the object's local +Y is from world +Y
      const uy=[e[4],e[5],e[6]]; const L=Math.hypot(...uy)||1;
      const tiltDeg=+(Math.acos(Math.max(-1,Math.min(1,uy[1]/L)))*180/Math.PI).toFixed(1);
      near.push({name:o.name||'(anon)',y:+wy.toFixed(2),tiltFromUpright:tiltDeg});
    }
  });
  out.near=near.slice(0,12); return out;
}),null,1));
for (const [n,c] of [['side',[16,2,0]],['top',[0,20,3]],['front',[0,2,16]]]) {
  await p.evaluate(o=>{ const cm=window.__camera,s=window.__game.pos();
    cm.position.set(s[0]+o[0],s[1]+o[1],s[2]+o[2]); cm.lookAt(s[0],s[1],s[2]); }, c);
  await new Promise(r=>setTimeout(r,900));
  await p.screenshot({path:process.env.SP+'/boat_'+n+'.jpg',type:'jpeg',quality:90});
}
console.log('shots saved');
await b.close();
