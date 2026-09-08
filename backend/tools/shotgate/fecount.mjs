import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,200)));
await p.goto('http://127.0.0.1:8789/games/job_'+process.argv[2]+'/dist/',{waitUntil:'networkidle2',timeout:90000});
await new Promise(r=>setTimeout(r,5000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const o=[];
  window.__scene.traverse(m=>{ if(m.isInstancedMesh) o.push({count:m.count,
    color:'#'+m.material.color.getHexString(), metal:m.material.metalness,
    geo:m.geometry.type, params:m.geometry.parameters?Object.values(m.geometry.parameters).slice(0,3):null}); });
  return o;
}),null,1));
await b.close();
