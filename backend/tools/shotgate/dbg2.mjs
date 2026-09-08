import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
const logs=[]; p.on('console',m=>logs.push(m.type()+': '+m.text().slice(0,180)));
p.on('pageerror',e=>logs.push('PAGEERROR: '+e.message.slice(0,250)));
await p.goto('http://127.0.0.1:8789/games/job_1/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log(await p.evaluate(()=>{
  const n=(window.__game?.npcs?.()||[]);
  return JSON.stringify({count:n.length, all:n.map(x=>({b:x.behavior,p:x.pos.map(v=>+v.toFixed(1))}))});
}));
console.log('--- console ---'); console.log(logs.filter(l=>!l.includes('favicon')).slice(0,10).join('\n'));
await b.close();
