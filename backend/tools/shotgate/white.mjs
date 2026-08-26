import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1100,650'] });
const p = await b.newPage();
const errs=[]; p.on('console',m=>{ const t=m.text();
  if(/texture|blob|GLTF|404/i.test(t)) errs.push(m.type()+': '+t.slice(0,180)); });
await p.goto('http://127.0.0.1:8789/games/job_' + (process.env.J||'2') + '/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
console.log(await p.evaluate(()=>{
  const out=[];
  let hero=null;
  window.__scene.traverse(o=>{ if(hero||!o.isSkinnedMesh) return;
    let q=o; while(q){ if(q.userData&&q.userData.fsTag&&q.userData.fsTag.type==='player'){hero=o;break;} q=q.parent; } });
  if(!hero) return 'no hero skinnedmesh';
  for (const m of (Array.isArray(hero.material)?hero.material:[hero.material])) {
    out.push({ name:m.name||'?', hasMap:!!m.map,
      img: m.map&&m.map.image ? (m.map.image.width+'x'+m.map.image.height+' '+(m.map.image.constructor&&m.map.image.constructor.name)) : null,
      color:'#'+m.color.getHexString(), emissive:'#'+m.emissive.getHexString(),
      emissiveMap: !!m.emissiveMap, emissiveIntensity: m.emissiveIntensity,
      metal:m.metalness, rough:m.roughness, envInt:m.envMapIntensity });
  }
  return JSON.stringify(out, null, 1);
}));
console.log('texture errors:', errs.length? errs.slice(0,6).join('\n') : 'NONE');
await p.evaluate(()=>window.__game && window.__game.tp(-58,10)); await new Promise(r=>setTimeout(r,3000)); await p.screenshot({path:(process.env.SP||'.')+'/white_fixed.jpg',type:'jpeg',quality:92}); await b.close();
