import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,200)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errs.push('ERR: '+m.text().slice(0,150));});
await p.goto('http://127.0.0.1:8789/games/job_18/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,3500));
console.log('alive:', await p.evaluate(()=>typeof window.__game));
console.log('spotlights with cookie:', await p.evaluate(()=>{let n=0;window.__scene?0:0;
  return new Promise(res=>{let c=0;(function walk(){c=0;
    (window.__game&&0);res(document.querySelectorAll('canvas').length);})();});}));
// walk in to see the pools of light
for(let i=0;i<3;i++){await p.keyboard.down('KeyW');await new Promise(r=>setTimeout(r,900));await p.keyboard.up('KeyW');}
await new Promise(r=>setTimeout(r,800));
await p.screenshot({path:'../../cookies.jpg',type:'jpeg',quality:88,clip:{x:0,y:55,width:1280,height:625}});
console.log('fps-ish ok, errors:', errs.length?errs.slice(0,3).join(' | '):'none');
await b.close();
