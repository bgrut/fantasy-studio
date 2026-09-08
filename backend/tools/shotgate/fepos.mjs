import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto('http://127.0.0.1:8789/games/job_'+process.argv[2]+'/dist/',{waitUntil:'networkidle2',timeout:90000});
await new Promise(r=>setTimeout(r,5000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const res=[];
  window.__scene.traverse(m=>{
    if(!m.isInstancedMesh||!m.geometry.parameters) return;
    const q=m.geometry.parameters;
    if(Math.abs(q.width-2.7)>0.01||Math.abs(q.height-0.09)>0.01) return;
    const a=m.instanceMatrix.array;
    for(let i=0;i<m.count;i++){
      // column-major: translation is elements 12,13,14 of each 16-float block
      res.push([+a[i*16+12].toFixed(1),+a[i*16+13].toFixed(1),+a[i*16+14].toFixed(1)]);
    }
  });
  return res;
})));
await b.close();
