import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1200,700'] });
const p = await b.newPage();
p.on('console',m=>{ const t=m.text(); if(m.type()==='error'||m.type()==='warning'||/fail|escort|courier/i.test(t)) console.log(m.type().toUpperCase()+':', t.slice(0,220)); });
await p.goto('http://127.0.0.1:8789/games/job_4/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,9000));
console.log('npcs:', await p.evaluate(()=> (window.__game && window.__game.npcs()||[]).map(n=>n.name+':'+n.behavior).join(', ')));
await b.close();
