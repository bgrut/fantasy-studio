import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,150)));
await p.goto('http://127.0.0.1:8123/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,9000));
const samples=[];
for (let i=0;i<8;i++){
  samples.push(await p.evaluate(()=>+document.getElementById('rate').textContent));
  await new Promise(r=>setTimeout(r,1100));
}
const f = await p.evaluate(()=>({v:+document.getElementById('ore').textContent,
  i:+document.getElementById('ingot').textContent}));
console.log('rate samples:', samples.join(' '));
console.log('zeros:', samples.filter(x=>x===0).length, '/', samples.length,
            '| final value', f.v, 'ingots', f.i);
console.log('errors:', errs.length?errs.join('|'):'none');
await b.close();
