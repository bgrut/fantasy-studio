import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage();
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
await p.evaluate(()=>{ window.__scene.traverse(o=>{
  if(o.userData&&o.userData.fsTag&&o.userData.fsTag.type==='player') window.__PL=o; }); });
const a = await p.evaluate(()=>window.__game.pos());
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,1200)); await p.keyboard.up('KeyW');
const res = await p.evaluate(()=>{
  const o=window.__PL; o.updateMatrixWorld(true);
  const m=o.matrixWorld.elements, f=[m[8],m[10]];
  const L=Math.hypot(f[0],f[1])||1;
  return { pos:window.__game.pos(), fwd:[f[0]/L,f[1]/L] };
});
const dx=res.pos[0]-a[0], dz=res.pos[2]-a[2], L=Math.hypot(dx,dz);
const dot=(dx/L)*res.fwd[0]+(dz/L)*res.fwd[1];
console.log(`moved ${L.toFixed(2)}m  dot=${dot.toFixed(2)}  ` + (dot>0.7?'FACING TRAVEL':dot<-0.7?'*** BACKWARDS ***':'ambiguous'));
await b.close();
