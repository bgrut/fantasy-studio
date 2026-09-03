import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1000,640'] });
const p = await b.newPage();
p.on('pageerror',e=>console.log('PAGEERROR:',e.message.slice(0,240)));
p.on('console',m=>{ const t=m.text();
  if(m.type()==='error'||/stride|calibration/i.test(t)) console.log(m.type()+':',t.slice(0,200)); });
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000));
console.log('before start __game:', await p.evaluate(()=>typeof window.__game));
await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log('after start __game:', await p.evaluate(()=>typeof window.__game));
const a = await p.evaluate(()=>window.__game? window.__game.pos() : null);
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,1500)); await p.keyboard.up('KeyW');
const c = await p.evaluate(()=>window.__game? window.__game.pos() : null);
console.log('moved:', a && c ? Math.hypot(c[0]-a[0], c[2]-a[2]).toFixed(2)+'m' : 'n/a');
await b.close();
