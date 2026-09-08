import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto('http://127.0.0.1:8789/games/job_13/dist/',{waitUntil:'networkidle2',timeout:90000});
await new Promise(r=>setTimeout(r,5000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
await p.evaluate(()=>window.__game.tp(117.7,-65.1));
await new Promise(r=>setTimeout(r,1800));
await p.evaluate(()=>window.__game.aim(1.15,0.22));
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({path:'femark/plain.png'});
const n=await p.evaluate(()=>{let k=0;
  window.__scene.traverse(m=>{ if(!m.isInstancedMesh||!m.geometry.parameters)return;
    const q=m.geometry.parameters;
    const isFE=(Math.abs(q.width-2.7)<0.01&&Math.abs(q.height-0.09)<0.01&&Math.abs(q.depth-1.15)<0.01)
             ||(Math.abs(q.width-2.7)<0.01&&Math.abs(q.height-0.85)<0.01)
             ||(Math.abs(q.width-0.85)<0.01&&Math.abs(q.depth-3.0)<0.01);
    if(isFE){ m.material=new m.material.constructor({color:0xff0000,emissive:0xff0000,emissiveIntensity:3}); k+=m.count; }});
  return k;});
console.log('marked FE instances:',n);
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({path:'femark/marked.png'});
await b.close();
