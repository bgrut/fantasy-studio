import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const out={};
  // the spec's declared ground colour
  const sp = window.__game.facts();
  out.style = sp.style; out.ground_mat_color = sp.ground_color;
  // average colour of the ground's painted canvas
  let gm=null;
  window.__scene.traverse(o=>{ if(o.isMesh&&o.geometry&&o.geometry.attributes
    &&o.geometry.attributes.position&&o.geometry.attributes.position.count===2304) gm=o; });
  if(gm&&gm.material.map&&gm.material.map.image){
    const im=gm.material.map.image, c=document.createElement('canvas');
    c.width=c.height=48; const g=c.getContext('2d',{willReadFrequently:true});
    g.drawImage(im,0,0,48,48); const d=g.getImageData(0,0,48,48).data;
    let r=0,gg=0,bb=0,n=0; for(let i=0;i<d.length;i+=4){r+=d[i];gg+=d[i+1];bb+=d[i+2];n++;}
    out.canvas_avg='rgb('+Math.round(r/n)+','+Math.round(gg/n)+','+Math.round(bb/n)+')';
    const mx=Math.max(r/n,gg/n,bb/n), mn=Math.min(r/n,gg/n,bb/n);
    out.canvas_saturation=+((mx-mn)/Math.max(mx,1)).toFixed(3);
  }
  return out;
}),null,1));
// average colour of the actual rendered frame
const shot = await p.screenshot({encoding:'base64'});
console.log('frame bytes b64:', shot.length);
await b.close();
