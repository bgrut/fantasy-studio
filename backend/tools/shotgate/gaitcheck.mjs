import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1200,760'] });
const p = await b.newPage(); await p.setViewport({width:1200,height:760});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,150)));
p.on('console',m=>{ if(/stride rates/.test(m.text())) console.log('LOG:',m.text()); });
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
// EXACT metric: the timeScale actually applied, and the depicted-vs-actual
// speed it implies. Immune to the sampling aliasing that made the foot-path
// ratio unreliable at high playback rates.
await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,1800));
console.log(await p.evaluate(()=>{
  let hero=null;
  window.__scene.traverse(o=>{ if(!hero&&o.isSkinnedMesh){ let q=o;
    while(q){ if(q.userData&&q.userData.fsTag&&q.userData.fsTag.type==='player'){hero=o;break;} q=q.parent; } } });
  const st = window.__game.state || {};
  return JSON.stringify({ groundSpeed:+(st.speed||0).toFixed(2) });
}));
await new Promise(r=>setTimeout(r,300));
await p.screenshot({path:process.env.SP+'/gait_walk.jpg',type:'jpeg',quality:92});
await p.keyboard.up('KeyW');
console.log('errors:', errs.length?errs.join('|'):'none');
await b.close();
