import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
const bad=[]; p.on('requestfailed',r=>bad.push(r.url().split('/').slice(-2).join('/')));
p.on('response',r=>{ if(r.status()>=400) bad.push(r.status()+' '+r.url().split('/').slice(-2).join('/')); });
await p.goto('http://127.0.0.1:8789/games/job_2/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,7000));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
console.log('failed requests:', bad.length?bad.join(', '):'none');
// INTERROGATE THE GROUND: what is actually on screen
console.log(JSON.stringify(await p.evaluate(()=>{
  const out={grounds:[],grassCounts:[]};
  window.__scene.traverse(o=>{
    if(!o.isMesh && !o.isInstancedMesh) return;
    const g=o.geometry, m=o.material;
    if(o.isInstancedMesh && o.count>500){ out.grassCounts.push({name:o.name||'(anon)',count:o.count,
      hasInstColor:!!o.instanceColor, matCol:m&&m.color?'#'+m.color.getHexString():null,
      vCol:m?!!m.vertexColors:null}); return; }
    if(!g||!g.attributes||!g.attributes.position) return;
    if(g.attributes.position.count<400) return;
    out.grounds.push({name:o.name||'(anon)', verts:g.attributes.position.count,
      matCol:m&&m.color?'#'+m.color.getHexString():null,
      map:m&&m.map?(m.map.image?(m.map.image.src||'canvas '+m.map.image.width):'no image'):'no map',
      vCol:m?!!m.vertexColors:null});
  });
  out.grounds=out.grounds.slice(0,6); out.grassCounts=out.grassCounts.slice(0,6);
  return out;
}),null,1));
await b.close();
