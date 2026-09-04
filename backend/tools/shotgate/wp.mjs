import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=800,600'] });
const p = await b.newPage();
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,160)));
await p.goto('http://127.0.0.1:8789/games/job_16/dist/wprobe.html',{waitUntil:'networkidle2',timeout:90000});
await p.waitForFunction('window.__ready===true',{timeout:90000}).catch(()=>{});
console.log('errors:', errs.join('|')||'none');
console.log(JSON.stringify(await p.evaluate(()=>window.__w||null)));
await b.close();
