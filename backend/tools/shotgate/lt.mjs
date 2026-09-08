import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,200)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errs.push('ERR: '+m.text().slice(0,140));});
await p.goto('http://127.0.0.1:8789/games/job_3/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,3000));
console.log('alive:', await p.evaluate(()=>typeof window.__game));
console.log('torches total/lit:', await p.evaluate(()=>{const t=window.__torches||[];
  return t.length+' / '+t.filter(L=>L.visible).length;}));
for(let i=0;i<4;i++){await p.keyboard.down('KeyW');await new Promise(r=>setTimeout(r,700));await p.keyboard.up('KeyW');}
await new Promise(r=>setTimeout(r,600));
console.log('after walking, lit:', await p.evaluate(()=>(window.__torches||[]).filter(L=>L.visible).length));
await p.screenshot({path:'../../lights.jpg',type:'jpeg',quality:86,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length?errs.slice(0,2).join(' | '):'none');
await b.close();
