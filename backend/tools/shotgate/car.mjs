import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,820']});
const p=await b.newPage(); await p.setViewport({width:1400,height:820});
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,220)));
p.on('console',m=>{if(m.type()==='error')console.log('ERR:',m.text().slice(0,180));});
await p.goto('http://127.0.0.1:8791/',{waitUntil:'networkidle2',timeout:30000});
await new Promise(r=>setTimeout(r,2500));
console.log('sliders:', await p.evaluate(()=>document.querySelectorAll('#ctrls input').length));
console.log('params json len:', await p.evaluate(()=>document.getElementById('out').value.length));
await p.screenshot({path:'../../carlab.jpg',type:'jpeg',quality:90});
await b.close();
