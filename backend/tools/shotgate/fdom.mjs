import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,4000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const hits = [];
  document.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 600 || r.height < 100) return;
    const cs = getComputedStyle(el);
    hits.push({ tag: el.tagName, id: el.id, cls: el.className.toString().slice(0,30),
      rect:[r.left|0,r.top|0,r.width|0,r.height|0], bg: cs.backgroundColor,
      bgImg: cs.backgroundImage.slice(0,40), z: cs.zIndex });
  });
  return { hits, atPoint: (document.elementFromPoint(640,600)||{}).tagName };
}), null, 1));
await b.close();
