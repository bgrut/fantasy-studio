import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror',e=>console.log('PAGEERROR:', e.message.slice(0,300)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))console.log('CONSOLE ERR:', m.text().slice(0,300));});
await p.goto('http://127.0.0.1:8789/games/job_12/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,5000));
console.log('__game defined:', await p.evaluate(()=>typeof window.__game));
await b.close();
