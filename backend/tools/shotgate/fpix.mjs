import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const c = window.__renderer.domElement;
  const o = document.createElement('canvas'); o.width=c.width; o.height=c.height;
  const g = o.getContext('2d'); g.drawImage(c,0,0);
  const at = (x,y) => { const d=g.getImageData(x,y,1,1).data;
    return '#'+[d[0],d[1],d[2]].map(v=>v.toString(16).padStart(2,'0')).join(''); };
  return { y100: at(640,100), y300: at(640,300), y450: at(640,450),
           y470: at(640,470), y500: at(640,500), y600: at(640,600), y740: at(200,740),
           canvasIsBlank: at(5,5) };
})));
await b.close();
