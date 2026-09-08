import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
await p.goto('http://127.0.0.1:8789/job_1/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>({
  playerY:+window.__game.pos()[1].toFixed(2),
  camY:+window.__camera.position.y.toFixed(2),
  spec_water: window.__SPEC ? window.__SPEC.world.water_level : 'n/a',
}))));
// camera well above the waterline, looking down at a shallow angle
await p.evaluate(()=>{ const c=window.__camera,s=window.__game.pos();
  c.position.set(s[0]+9,s[1]+4.5,s[2]+9); c.lookAt(s[0],s[1]+0.6,s[2]); });
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({path:process.env.SP+'/boat_final.jpg',type:'jpeg',quality:92});
console.log('shot saved');
await b.close();
