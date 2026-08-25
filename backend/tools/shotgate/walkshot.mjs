import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:760});
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
// walk AWAY from the camera for 2.5s and shoot mid-stride: with a follow cam
// we must see his BACK. Then walk TOWARD the camera (S) and shoot again.
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,2500));
await p.screenshot({ path: process.env.SP + '/walk_W.jpg', type:'jpeg', quality:95 });
await p.keyboard.up('KeyW');
await new Promise(r=>setTimeout(r,600));
await p.keyboard.down('KeyS');
await new Promise(r=>setTimeout(r,2000));
await p.screenshot({ path: process.env.SP + '/walk_S.jpg', type:'jpeg', quality:95 });
await p.keyboard.up('KeyS');
await b.close();
