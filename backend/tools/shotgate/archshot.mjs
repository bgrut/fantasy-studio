import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,7000));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
// pull the camera up and back to read the LANDFORM, not the grass
await p.evaluate(()=>{
  const c = window.__camera, s = window.__game.pos();
  c.position.set(s[0]+70, s[1]+95, s[2]+90);
  c.lookAt(s[0], s[1], s[2]);
});
await new Promise(r=>setTimeout(r,1500));
await p.screenshot({path:process.env.SP+'/arch_'+(process.env.NAME||'x')+'.jpg',type:'jpeg',quality:92});
console.log('shot saved');
await b.close();
