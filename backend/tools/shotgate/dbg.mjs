import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.goto('http://127.0.0.1:8789/games/job_1/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,4000));
console.log(await p.evaluate(()=>{
  const S=window.__GAME_SPEC__||{};
  const lv=(S.world||{}).level||{};
  return JSON.stringify({
    hasInterior: !!lv.interior,
    rooms: lv.interior? lv.interior.rooms.length : 0,
    roomCenters: lv.interior? lv.interior.rooms.slice(0,3).map(r=>[r[0],r[1]]) : null,
    entBehaviors: (S.entities||[]).map(e=>e.behavior),
  },null,1);
}));
await b.close();
