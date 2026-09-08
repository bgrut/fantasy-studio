import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,200)));
await p.goto('http://127.0.0.1:8789/games/job_11/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2500));
console.log('alive:', await p.evaluate(()=>typeof window.__game));
const c=await p.evaluate(()=>(window.__cars||[]).map(c=>({x:+c.obj.position.x.toFixed(1),z:+c.obj.position.z.toFixed(1)})));
console.log('parked cars:', JSON.stringify(c));
if(c.length){ await p.evaluate(c0=>window.__game.tp(c0.x+2.2,c0.z+2.2), c[0]);
  await new Promise(r=>setTimeout(r,1400));
  await p.screenshot({path:'../../car_ingame.jpg',type:'jpeg',quality:88,clip:{x:0,y:55,width:1280,height:625}});
  await p.keyboard.press('KeyE'); await new Promise(r=>setTimeout(r,1600));
  await p.screenshot({path:'../../car_ingame2.jpg',type:'jpeg',quality:88,clip:{x:0,y:55,width:1280,height:625}});
}
await b.close();
