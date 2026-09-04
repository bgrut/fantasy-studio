import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1920,1080'] });
const p = await b.newPage(); await p.setViewport({width:1920,height:1080,deviceScaleFactor:1});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,9000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const r = window.__renderer, o = {};
  o.hasRenderer = !!r;
  if (r) { o.pixelRatio = r.getPixelRatio(); o.toneMapping = r.toneMapping;
           o.outputColorSpace = r.outputColorSpace;
           o.maxAniso = r.capabilities.getMaxAnisotropy();
           o.antialias = !!(r.getContext && r.getContext().getContextAttributes
                            && r.getContext().getContextAttributes().antialias); }
  o.dpr = window.devicePixelRatio;
  o.facts = window.__game ? window.__game.facts() : null;
  return o;
}),null,1));
await p.screenshot({path:process.env.SP+'/hires.png'});
console.log('saved');
await b.close();
