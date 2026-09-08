import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,180)));
await p.goto('http://127.0.0.1:8789/games/job_16/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2500));
const c=await p.evaluate(()=>window.__game.cars()[0]);
console.log('car0:', JSON.stringify(c).slice(0,120));
const x=c.x!==undefined?c.x:(c.pos?c.pos[0]:0), z=c.z!==undefined?c.z:(c.pos?c.pos[2]:0);
await p.evaluate(([X,Z])=>window.__game.tp(X+3.5,Z+3.5),[x,z]);
await new Promise(r=>setTimeout(r,1600));
await p.screenshot({path:'../../car_ingame.jpg',type:'jpeg',quality:88,clip:{x:0,y:55,width:1280,height:625}});
console.log('shot taken near', x.toFixed(1), z.toFixed(1));
await b.close();
