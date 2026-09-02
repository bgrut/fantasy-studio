import puppeteer from 'puppeteer-core';
import { pathToFileURL } from 'url';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--allow-file-access-from-files','--window-size=1060,800'] });
const p = await b.newPage(); await p.setViewport({width:1060,height:800});
p.on('pageerror',e=>console.log('ERR',e.message.slice(0,200)));
p.on('console',m=>{ if(m.type()==='error') console.log('CERR',m.text().slice(0,160)); });
await p.goto(pathToFileURL(process.cwd()+'/index.html').href + (process.env.HASH||''));
await p.waitForFunction(()=>window.__ready,{timeout:30000});
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({path:process.env.OUT||'render.png'});
// articulation proof: steer + spin, then second shot
await p.evaluate(()=>{ window.__animate=true; });
await new Promise(r=>setTimeout(r,700));
await p.evaluate(()=>{ window.__animate=false; window.__car.userData.drive.setSteer(0.45); });
await new Promise(r=>setTimeout(r,300));
await p.screenshot({path:(process.env.OUT||'render.png').replace('.png','_steered.png')});
console.log('shots done');
await b.close();
