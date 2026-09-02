import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,860'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:860});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
console.log(await p.evaluate(()=>{
  const pr = window.__procDrive;
  if (!pr) return 'NO procDrive';
  const names=[]; pr.traverse(o=>{ if(/^wheel-/.test(o.name)) names.push(o.name); });
  return 'proc hero loaded, pivots: ' + names.join(', ');
}));
// drive forward + steer, sample spin rotation and steer yaw
const before = await p.evaluate(()=>{
  const out={};
  window.__procDrive.traverse(o=>{ if(/^wheel-(RL|FL)/.test(o.name)) out[o.name]= (o.name.includes('steer')? o.rotation.y : o.rotation.x); });
  return out;
});
await p.keyboard.down('KeyW'); await p.keyboard.down('KeyA');
await new Promise(r=>setTimeout(r,2000));
await p.screenshot({path:process.env.SP+'/proc_driving.jpg',type:'jpeg',quality:93});
const after = await p.evaluate(()=>{
  const out={ speed: window.__pSpeed || (window.__game.state||{}).speed };
  window.__procDrive.traverse(o=>{ if(/^wheel-(RL|FL)/.test(o.name)) out[o.name]= (o.name.includes('steer')? o.rotation.y : o.rotation.x); });
  return out;
});
await p.keyboard.up('KeyW'); await p.keyboard.up('KeyA');
console.log('before:', JSON.stringify(before));
console.log('after :', JSON.stringify(after));
await b.close();
