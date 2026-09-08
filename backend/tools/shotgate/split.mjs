import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,160)));
await p.goto('http://127.0.0.1:8123/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,1500));
// Build: miner -> belt -> SPLITTER -> two belts -> two smelters -> two belts -> hub
const built = await p.evaluate(()=>{
  const F = window.__factory, C = F.cells, K = F.TYPES, N = F.N;
  // wipe, then find a node with room around it
  for (let x=0;x<N;x++) for (let z=0;z<N;z++) if (C[x][z].t!==K.NODE) F.removeAt(x,z);
  let node=null;
  for (let x=4;x<N-8&&!node;x++) for (let z=4;z<N-6&&!node;z++) if (C[x][z].t===K.NODE) node=[x,z];
  if (!node) return {ok:false};
  const [x,z]=node;
  F.place(x,z,K.MINER,0);
  F.place(x+1,z,K.BELT,0);
  F.place(x+2,z,K.SPLITTER,0);
  // north branch
  F.place(x+2,z-1,K.BELT,3); F.place(x+2,z-2,K.SMELTER,3);
  // south branch
  F.place(x+2,z+1,K.BELT,1); F.place(x+2,z+2,K.SMELTER,1);
  return {ok:true, x, z};
});
if (!built.ok) { console.log('no room for the test layout'); await b.close(); process.exit(0); }
await new Promise(r=>setTimeout(r,9000));
const r = await p.evaluate(o=>{
  const C=window.__factory.cells;
  return { north: C[o.x+2][o.z-2].buf + C[o.x+2][o.z-2].cook,
           south: C[o.x+2][o.z+2].buf + C[o.x+2][o.z+2].cook,
           northTot: C[o.x+2][o.z-2].buf, southTot: C[o.x+2][o.z+2].buf };
}, built);
console.log('errors:', errs.length?errs.join('|'):'none');
console.log('north smelter activity:', r.north, '| south smelter activity:', r.south);
await p.keyboard.press('Tab');
await new Promise(r=>setTimeout(r,900));
await p.screenshot({path:process.env.SP+'/splitter.jpg',type:'jpeg',quality:92});
console.log(r.north > 0 && r.south > 0
  ? 'BOTH branches fed — splitter alternates'
  : 'ONE-SIDED — round robin not working');
await b.close();
