import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=800,600'] });
const p = await b.newPage();
await p.goto('http://127.0.0.1:8789/games/job_2/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  let g=null;
  window.__scene.traverse(o=>{ if(o.isMesh && o.geometry && o.geometry.attributes
    && o.geometry.attributes.position && o.geometry.attributes.position.count===2304) g=o; });
  if(!g) return {found:false};
  const m=g.material;
  return { found:true, color:'#'+m.color.getHexString(),
    map: m.map ? m.map.image.src.split('/').pop() : null,
    hasOBC: !!m.onBeforeCompile,
    tintInShader: !!(m.userData && m.userData.shader
      ? /uWorld/.test(m.userData.shader.fragmentShader) : null),
    progFrag: (()=>{ try{ const pr=window.__renderer.info.programs
        .find(x=>x.cacheKey && /uWorld/.test(x.cacheKey)); return !!pr; }catch(e){return 'n/a';} })(),
    groundColorSpec: window.__spec ? window.__spec.world.ground_color : 'n/a' };
}),null,1));
await b.close();
