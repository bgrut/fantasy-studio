import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
 args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,200)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))console.log('ERR:',m.text().slice(0,140));});
await p.goto('http://127.0.0.1:8789/games/job_1/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2500));
console.log('alive:', await p.evaluate(()=>typeof window.__game));
// DROP FALLBACK: aim at the sky (top of screen) — must now answer, not hang
const sky=await p.evaluate(()=>new Promise(res=>{
  const h=e=>{if(e.data&&e.data.type==='fs-pick'){window.removeEventListener('message',h);res(e.data.kind+':'+(e.data.x??'-'))}};
  window.addEventListener('message',h);
  window.postMessage({type:'fs-dropat',cx:640,cy:40},'*');
  setTimeout(()=>res('NO REPLY (hung)'),2500);}));
console.log('drop at sky  ->', sky);
const grd=await p.evaluate(()=>new Promise(res=>{
  const h=e=>{if(e.data&&e.data.type==='fs-pick'){window.removeEventListener('message',h);res(e.data.kind+' @ '+e.data.x+','+e.data.z)}};
  window.addEventListener('message',h);
  window.postMessage({type:'fs-dropat',cx:640,cy:600},'*');
  setTimeout(()=>res('NO REPLY (hung)'),2500);}));
console.log('drop at ground ->', grd);
// CAR: screenshot next to one
const c=await p.evaluate(()=>{const cs=window.__game.cars?window.__game.cars():[];return cs.length?cs[0]:null;});
console.log('car0:', JSON.stringify(c));
if(c){await p.evaluate(q=>window.__game.tp(q.x+4,q.z+4),c); await new Promise(r=>setTimeout(r,1500));
  await p.screenshot({path:'../../car_r7.jpg',type:'jpeg',quality:90,clip:{x:0,y:55,width:1280,height:625}});}
await b.close();
