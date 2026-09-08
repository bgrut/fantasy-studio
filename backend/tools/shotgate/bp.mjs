import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,220)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errs.push('ERR: '+m.text().slice(0,160));});
await p.goto('http://127.0.0.1:8789/games/job_15/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,3000));
console.log('game alive:', await p.evaluate(()=>typeof window.__game));
await p.keyboard.press('KeyB');
await new Promise(r=>setTimeout(r,900));
console.log('blueprint open:', await p.evaluate(()=>!!document.getElementById('fsbp')));
await p.screenshot({path:'../../blueprint.jpg',type:'jpeg',quality:88,clip:{x:0,y:55,width:1280,height:625}});
await p.keyboard.press('KeyB'); await new Promise(r=>setTimeout(r,500));
console.log('blueprint closes:', await p.evaluate(()=>!document.getElementById('fsbp')));
console.log('errors:', errs.length?errs.slice(0,3).join(' | '):'none');
await b.close();
