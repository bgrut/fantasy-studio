import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
p.on('console', m => { if (m.type()==='error') console.log('CONSOLE:', m.text().slice(0,200)); });
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const t = document.querySelector('.tool[data-tool="miner"]');
  const img = t.querySelector('img');
  const svg = t.querySelector('svg');
  return { hasImg: !!img, hasSvg: !!svg,
           srcLen: img ? img.src.length : 0,
           srcHead: img ? img.src.slice(0, 40) : null,
           natural: img ? [img.naturalWidth, img.naturalHeight] : null,
           box: img ? (r => [r.width|0, r.height|0])(img.getBoundingClientRect()) : null };
}), null, 1));
// re-render one and inspect the raw float buffer
console.log('raw:', JSON.stringify(await p.evaluate(()=>{
  const THREEC = window.__scene.constructor;
  const F = window.__factory;
  // reach the internals the way the runtime does
  const out = {};
  try {
    const url = window.__renderThumbProbe ? window.__renderThumbProbe() : null;
    out.probe = url ? url.slice(0, 40) : 'no probe';
  } catch (e) { out.err = String(e).slice(0, 160); }
  return out;
})));
await b.close();
