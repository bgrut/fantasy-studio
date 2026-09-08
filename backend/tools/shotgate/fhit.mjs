import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(async () => {
  const THREE = await import('three');
  const out = { camKids: window.__camera.children.length };
  const rc = new THREE.Raycaster();
  for (const [sx, sy] of [[640,600],[640,700],[300,550],[640,300]]) {
    rc.setFromCamera(new THREE.Vector2(sx/1280*2-1, -(sy/760*2-1)), window.__camera);
    const h = rc.intersectObjects(window.__scene.children, true)[0];
    out['px_'+sx+'_'+sy] = h ? { d:+h.distance.toFixed(2), geo:h.object.geometry.type,
      col: h.object.material.color ? '#'+h.object.material.color.getHexString() : '?',
      y:+h.point.y.toFixed(2) } : 'sky';
  }
  return out;
}), null, 1));
await b.close();
