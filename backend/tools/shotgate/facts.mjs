import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>window.__game.facts()),null,1));
console.log(JSON.stringify(await p.evaluate(()=>{
  const o=[]; window.__scene.traverse(x=>{ if(x.isMesh&&x.material&&x.material.color)
    o.push({n:x.name||'(anon)',c:'#'+x.material.color.getHexString(),
            map:x.material.map?(x.material.map.image&&x.material.map.image.src?x.material.map.image.src.split('/').pop():'canvas'):null}); });
  return o.slice(0,8);
}),null,1));
await b.close();
