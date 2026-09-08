import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,820']});
const p=await b.newPage(); await p.setViewport({width:1400,height:820});
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,220)));
p.on('console',m=>{if(m.type()==='error')console.log('ERR:',m.text().slice(0,160));});
await p.goto('http://127.0.0.1:8792/',{waitUntil:'networkidle2',timeout:30000});
await new Promise(r=>setTimeout(r,2500));
console.log('families:', await p.evaluate(()=>document.querySelectorAll('#fams button').length));
console.log('sliders:',  await p.evaluate(()=>document.querySelectorAll('#ctrls input').length));
// BEFORE: flat, dusk
await p.evaluate(()=>{document.querySelector('#tod button[data-t="dusk"]').click();});
await new Promise(r=>setTimeout(r,700));
await p.evaluate(()=>{document.querySelector('#cmp button[data-c="off"]').click();});
await new Promise(r=>setTimeout(r,900));
await p.screenshot({path:'../../fac_before.jpg',type:'jpeg',quality:90});
// AFTER: facade, dusk
await p.evaluate(()=>{document.querySelector('#cmp button[data-c="on"]').click();});
await new Promise(r=>setTimeout(r,1100));
await p.screenshot({path:'../../fac_after.jpg',type:'jpeg',quality:90});
// NIGHT emissive windows
await p.evaluate(()=>{document.querySelector('#tod button[data-t="night"]').click();});
await new Promise(r=>setTimeout(r,1100));
await p.screenshot({path:'../../fac_night.jpg',type:'jpeg',quality:90});
await b.close();
