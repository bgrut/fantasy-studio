import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_34/dist/?fresh=1&debug=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(()=>{
  let sun = null;
  window.__scene.traverse(o => { if (o.isDirectionalLight && o.castShadow) sun = o; });
  const F = window.__factory;
  const cubeR = F.HALF * Math.sqrt(3);
  return {
    shadowMapEnabled: window.__renderer.shadowMap.enabled,
    sunPos: sun.position.toArray(),
    sunDist: +sun.position.length().toFixed(1),
    cubeCornerDist: +cubeR.toFixed(1),
    // a directional light's shadow camera sits AT the light looking at the
    // target: anything farther from the target than the light is behind it
    behindTheLight: cubeR > sun.position.length(),
    frustum: [sun.shadow.camera.left, sun.shadow.camera.right,
              sun.shadow.camera.near, sun.shadow.camera.far],
    needsToCover: +(cubeR).toFixed(1),
  };
}), null, 1));
// and does anything actually darken? sample across a machine's base
const lum = await p.evaluate(async ()=>{
  const F = window.__factory, TY = F.TYPES;
  // clear a patch and stand one tall machine in it, viewed from above
  for (let i = 8; i < 20; i++) for (let j = 8; j < 20; j++)
    if (F.cells[0][i][j].t !== TY.EMPTY) F.removeAt(0, i, j);
  F.place(0, 14, 14, TY.SMELTER, 0);
  const w = F.tileWorld(0, 14, 14);
  F.player.face = 0;
  F.player.pos.set(w[0], F.HALF + 1.68, w[2] + 9);
  F.player.fwd.set(0, 0, -1);
  F.player.pitch = -0.5;
  await new Promise(r => setTimeout(r, 900));
  const c = document.querySelector('canvas');
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  const row = Math.floor(c.height * 0.34);          // ground just past the machine
  const out = [];
  for (const fx of [0.30, 0.40, 0.50, 0.60, 0.70]) {
    const px = new Uint8Array(4);
    gl.readPixels(Math.floor(c.width * fx), row, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    out.push(Math.round((px[0] + px[1] + px[2]) / 3));
  }
  return out;
});
console.log('ground luminance across the machine base:', lum.join(' '));
await p.screenshot({ path: process.env.OUT });
await b.close();
