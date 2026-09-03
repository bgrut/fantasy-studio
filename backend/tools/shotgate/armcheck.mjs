import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1000,640'] });
const p = await b.newPage();
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,1200));
// WORLD direction of the upper arm: shoulder -> elbow. A hanging arm points
// mostly DOWN (-Y). A splayed arm points mostly sideways.
console.log(await p.evaluate(()=>{
  let sk=null;
  window.__scene.traverse(o=>{ if(!sk&&o.isSkinnedMesh&&o.skeleton){ let q=o;
    while(q){ if(q.userData&&q.userData.fsTag&&q.userData.fsTag.type==='player'){sk=o;break;} q=q.parent; } } });
  if(!sk) return 'no hero';
  const by = {}; for(const bn of sk.skeleton.bones) by[bn.name]=bn;
  const out={};
  for (const side of ['L','R']) {
    const ua = by['uparm_'+side], lo = by['lowarm_'+side];
    if(!ua||!lo) continue;
    ua.updateMatrixWorld(true); lo.updateMatrixWorld(true);
    const a=ua.matrixWorld.elements, c=lo.matrixWorld.elements;
    const dx=c[12]-a[12], dy=c[13]-a[13], dz=c[14]-a[14];
    const L=Math.hypot(dx,dy,dz)||1;
    out['uparm_'+side] = { down:+(-dy/L).toFixed(2), lateral:+(Math.abs(dx)/L).toFixed(2),
                           fwd:+(Math.abs(dz)/L).toFixed(2) };
  }
  return JSON.stringify(out);
}));
await p.keyboard.up('KeyW');
await b.close();
