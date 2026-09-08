import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,300)));
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_19/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
const local = () => p.evaluate(()=>{
  const F = window.__factory, f = F.FACES[F.player.face], q = F.player.pos;
  const a = q.x*f.u[0] + q.y*f.u[1] + q.z*f.u[2];
  const bb = q.x*f.v[0] + q.y*f.v[1] + q.z*f.v[2];
  const fwd = F.player.fwd;
  return { face: F.player.face, a: +a.toFixed(2), b: +bb.toFixed(2), HALF: F.HALF,
           fwd: [fwd.x, fwd.y, fwd.z].map(v=>+v.toFixed(2)),
           j: Math.floor(bb / F.T + F.N / 2) };
});
console.log('at rest  :', JSON.stringify(await local()));
await p.evaluate(()=>{ window.__factory.player.fwd.negate(); });
console.log('turned   :', JSON.stringify(await local()));
await p.keyboard.down('KeyW');
for (let k = 0; k < 10; k++) {
  await new Promise(r=>setTimeout(r,700));
  console.log('  +' + ((k+1)*0.7).toFixed(1) + 's:', JSON.stringify(await local()));
}
await p.keyboard.up('KeyW');
await b.close();
