// Probe the live city: what is actually lighting (or not lighting) the walls.
import puppeteer from 'puppeteer-core';
const job = process.argv[2];
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'] });
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/job_${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 5000));

// three is a module import; reach the scene through any object's parent chain.
// __game.pos() gives the player object, but we need the scene graph itself —
// walk up from the renderer's DOM canvas via the exposed probe instead.
const info = await p.evaluate(() => {
  const out = { lights: [], fog: null, env: null, wallMats: [], exposure: null };
  const sc = window.__scene;
  if (!sc) return { err: 'no window.__scene' };
  out.exposure = window.__renderer ? window.__renderer.toneMappingExposure : null;
  out.envIntensity = sc.environmentIntensity;
  out.hasEnv = !!sc.environment;
  if (sc.fog) out.fog = { type: sc.fog.type, density: sc.fog.density,
                          color: '#' + sc.fog.color.getHexString() };
  sc.traverse(o => {
    if (o.isLight) out.lights.push({ t: o.type, i: o.intensity,
      c: '#' + (o.color ? o.color.getHexString() : '?'),
      pos: o.position.toArray().map(v => +v.toFixed(1)) });
    if (o.isMesh && o.material && o.material.map && o.material.map.image &&
        (o.material.map.image.src || '').includes('facade')) {
      out.wallMats.push({ src: o.material.map.image.src.split('/').pop(),
        rough: o.material.roughness, metal: o.material.metalness,
        color: '#' + o.material.color.getHexString(),
        vc: o.material.vertexColors,
        emiI: o.material.emissiveIntensity,
        emi: '#' + o.material.emissive.getHexString(),
        hasN: !!o.material.normalMap,
        nScale: o.material.normalMap ? o.material.normalScale.toArray() : null,
        hasRough: !!o.material.roughnessMap, hasAO: !!o.material.aoMap,
        hasUV1: !!(o.geometry.attributes.uv1),
        envI: o.material.envMapIntensity });
    }
  });
  return out;
});
console.log(JSON.stringify(info, null, 1));
await b.close();
