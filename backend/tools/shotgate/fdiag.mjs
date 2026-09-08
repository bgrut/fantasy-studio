import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const s = window.__scene, out = { children: s.children.length, byType: {}, sample: [] };
  for (const c of s.children) {
    out.byType[c.type] = (out.byType[c.type]||0)+1;
    if (out.sample.length < 12) out.sample.push({
      type: c.type, name: c.name||'',
      pos: c.position.toArray().map(v=>+v.toFixed(1)),
      vis: c.visible, kids: c.children.length });
  }
  out.player = window.__game.pos().map(v=>+v.toFixed(1));
  out.spec_size = window.__SPEC.world && window.__SPEC.world.size_m;
  out.fog = window.__scene.fog ? [window.__scene.fog.near, window.__scene.fog.far] : null;
  out.far = window.__camera.far;
  return out;
}), null, 1));
await b.close();
