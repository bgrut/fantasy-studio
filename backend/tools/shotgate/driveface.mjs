import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,860'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:860});
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,2200));
await p.screenshot({path:process.env.SP+'/driveface_W.jpg',type:'jpeg',quality:93});
await p.keyboard.up('KeyW');
await b.close();
