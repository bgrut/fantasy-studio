import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,4000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const out = { lights: [], big: [], tone: window.__renderer.toneMapping,
                exposure: window.__renderer.toneMappingExposure,
                outColorSpace: window.__renderer.outputColorSpace };
  window.__scene.traverse(o => {
    if (o.isLight) out.lights.push({ t:o.type, col:'#'+o.color.getHexString(),
      int:o.intensity, gnd: o.groundColor ? '#'+o.groundColor.getHexString() : null });
    if (!o.isMesh) return;
    o.geometry.computeBoundingSphere();
    const r = o.geometry.boundingSphere.radius * Math.max(o.scale.x,o.scale.y,o.scale.z);
    if (r > 8) out.big.push({ geo:o.geometry.type, r:+r.toFixed(1),
      pos:o.position.toArray().map(v=>+v.toFixed(1)),
      col: o.material.color ? '#'+o.material.color.getHexString() : '?',
      emis: o.material.emissive ? '#'+o.material.emissive.getHexString() : null,
      mat: o.material.type, side: o.material.side, vis:o.visible });
  });
  return out;
}), null, 1));
await b.close();
