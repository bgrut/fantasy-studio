// The art pass, checked the way art has to be checked: is the thing on screen,
// is it moving, and did it cost what it was supposed to cost.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
// debug=1 makes the framebuffer readable so a pixel can be asserted on
await p.goto(URL + '?fresh=1&debug=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

// 1. every tool in the bar carries an icon, and a locked one is dimmed
const icons = await p.evaluate(()=>{
  const t = [...document.querySelectorAll('.tool')];
  // an icon is a RENDER of the machine now, not a drawing of one — so it is an
  // <img> with a data URL, and only ERASE is still a glyph
  return { tools: t.length,
           withIcon: t.filter(o => o.querySelector('img,svg')).length,
           rendered: t.filter(o => { const i = o.querySelector('img');
             return i && i.src.startsWith('data:image/png') && i.src.length > 4000; }).length,
           locked: t.filter(o => o.classList.contains('locked')).length };
});
console.log('tool bar  :', icons.withIcon, 'of', icons.tools, 'have an icon |',
            icons.rendered, 'are rendered machines |', icons.locked, 'locked');

// 2. belts are instanced: many belts, few draw calls
const inst = await p.evaluate(async ()=>{
  const F = window.__factory, TY = F.TYPES;
  let n = 0;
  for (let j = 4; j < Math.min(F.N - 4, 24); j += 2)
    for (let i = 4; i < Math.min(F.N - 4, 24); i++)
      if (F.cells[0][i][j].t === TY.EMPTY && F.place(0, i, j, TY.BELT, 0)) n++;
  await new Promise(r => setTimeout(r, 900));
  return { belts: n, calls: window.__game.stats().calls };
});
console.log('instanced :', inst.belts, 'belts ->', inst.calls, 'draw calls total');

// 3. THE TREAD MOVES. A conveyor whose surface is static is a green plank, and
//    nothing in the scene graph would show that — only the pixels do.
const moving = await p.evaluate(async ()=>{
  const F = window.__factory;
  const a = F.TREAD ? F.TREAD.offset.x : null;
  await new Promise(r => setTimeout(r, 400));
  const c = F.TREAD ? F.TREAD.offset.x : null;
  return { from: a, to: c, moved: a !== null && Math.abs(c - a) > 0.05 };
});
console.log('tread     :', moving.moved ? 'scrolls' : 'STATIC',
            '(offset', (moving.from||0).toFixed(2), '->', (moving.to||0).toFixed(2) + ')');

// 3b. the post pipeline is on, and it is what puts the picture on the screen.
//     A composite that forgot to tone map and encode renders a nearly black
//     world, which looks exactly like a lighting bug and is not one — so the
//     mid-grey of a lit surface is checked directly.
const post = await p.evaluate(async ()=>{
  const F = window.__factory;
  const on = F.POST && F.POST.on;
  const c = window.__renderer.domElement;
  // sample the framebuffer through a fresh readback, since a WebGL canvas
  // cannot be drawn into a 2D context after compositing
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  const px = new Uint8Array(4);
  let lum = -1;
  if (gl) {
    gl.readPixels(Math.floor(c.width / 2), Math.floor(c.height * 0.25),
                  1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    lum = (px[0] + px[1] + px[2]) / 3;
  }
  return { on, lum, px: [px[0], px[1], px[2]] };
});
console.log('post      :', post.on ? 'on' : 'OFF', '| a lit floor pixel reads',
            JSON.stringify(post.px));

// 3c. machines that are working are visibly working
const smoke = await p.evaluate(async ()=>{
  const F = window.__factory, TY = F.TYPES;
  // force a smelter to cook so there is something to emit
  let lit = 0;
  F.cells.forEach((face, f) => face.forEach((col, i) => col.forEach((c, j) => {
    if (c.t === TY.SMELTER) { c.cook = 30; lit++; }
  })));
  await new Promise(r => setTimeout(r, 1400));
  return { lit, alive: window.__game.facts().particles };
});
console.log('particles :', smoke.alive, 'alive from', smoke.lit, 'cooking smelters');

// 3d. the worldlet has an outline and something to be lit by
const sil = await p.evaluate(()=>({
  edges: window.__scene.getObjectByName('worldEdge') ? 1 : 0,
  sun: window.__scene.getObjectByName('sun') ? 1 : 0,
}));
console.log('silhouette:', sil.edges, 'edge outline |', sil.sun, 'sun');

// 3e. something is in your hands, showing what you are about to build — and
//     it goes away when you are not standing on the world
const held = await p.evaluate(async ()=>{
  const cam = window.__camera;
  const rig = cam.children.find(o => o.isGroup);
  const holo = rig && rig.children.find(o => o.isMesh && o.material.transparent
                                        && o.material.blending === 2);
  const F = window.__factory;
  const before = holo ? holo.geometry : null;
  // pick a different unlocked tool and the hologram has to change shape
  document.querySelector('.tool[data-tool="belt"]').dispatchEvent(
    new PointerEvent('pointerdown', { bubbles: true }));
  await new Promise(r => setTimeout(r, 150));
  const changed = holo && holo.geometry !== before;
  const fpVisible = rig && rig.visible;
  window.__game.inspect(true);
  await new Promise(r => setTimeout(r, 300));
  const orbitVisible = rig && rig.visible;
  window.__game.inspect(false);
  await new Promise(r => setTimeout(r, 200));
  return { hasRig: !!rig, hasHolo: !!holo, changed, fpVisible, orbitVisible };
});
console.log('held rig  :', held.hasRig ? 'present' : 'MISSING',
            '| hologram follows the tool:', held.changed,
            '| shown in first person:', held.fpVisible,
            '| hidden from orbit:', !held.orbitVisible);

// 3f. a jammed belt is amber. Build a two-belt line into a hub, then stop the
//     hub by turning it into a full smelter and watch the deck change colour.
const jam = await p.evaluate(async ()=>{
  const F = window.__factory, TY = F.TYPES;
  let spot = null;
  for (let i = 4; i < F.N - 6 && !spot; i++)
    for (let j = 4; j < F.N - 4 && !spot; j++)
      if ([0,1,2,3].every(k => F.cells[0][i + k][j].t === TY.EMPTY)) spot = [i, j];
  const [i, j] = spot;
  F.place(0, i, j, TY.BELT, 0);
  F.place(0, i + 1, j, TY.BELT, 0);
  F.place(0, i + 2, j, TY.SMELTER, 0);
  F.cells[0][i + 2][j].buf = 99;                 // full: it will not accept
  F.cells[0][i][j].item = TY.CRYSTAL;
  F.cells[0][i + 1][j].item = TY.CRYSTAL;
  await new Promise(r => setTimeout(r, 1200));
  // find the second belt's instance and read its colour
  const dk = F.beltDecks[F.beltShape(0, i + 1, j, F.cells[0][i + 1][j])];
  const idx = F.beltIndexOf ? F.beltIndexOf(0, i + 1, j) : null;
  let col = null;
  if (idx != null) col = [dk.instanceColor.getX(idx), dk.instanceColor.getY(idx),
                          dk.instanceColor.getZ(idx)].map(v => +v.toFixed(2));
  return { col, stuck: !!F.cells[0][i + 1][j].item };
});
console.log('jam       :', jam.stuck ? 'belt is holding' : 'belt drained (?)',
            '| deck colour', JSON.stringify(jam.col));

// 4. the starfield is actually drawn, i.e. inside the far plane
const sky = await p.evaluate(()=>{
  // BY NAME. "the last Points in the scene" was the starfield right up until
  // the particle system was added, at which point this silently started
  // measuring smoke and reporting 420 stars at a radius of 32.
  const pts = window.__scene.getObjectByName('stars');
  if (!pts) return { found: false };
  pts.geometry.computeBoundingSphere();
  return { found: true, stars: pts.geometry.attributes.position.count,
           radius: Math.round(pts.geometry.boundingSphere.radius),
           far: window.__camera.far };
});
console.log('starfield :', sky.found ? sky.stars + ' stars at r=' + sky.radius +
            ', camera far ' + sky.far : 'MISSING');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'art.png' });
await b.close();
const ok = icons.withIcon === icons.tools && icons.tools >= 9
  && icons.rendered >= 8            // every machine; ERASE stays a glyph
  && inst.belts > 60 && inst.calls < 120     // a 20-grid lays 72; a 40-grid 199
  && moving.moved
  && sky.found && sky.radius < sky.far && sky.stars > 500
  && post.on && post.lum > 6 && post.lum < 250   // lit, not black, not blown
  && smoke.alive > 0 && sil.edges === 1 && sil.sun === 1
  && held.hasRig && held.hasHolo && held.changed && held.fpVisible && !held.orbitVisible
  && jam.stuck && jam.col && jam.col[0] > 1.2 && jam.col[2] < 0.5   // amber
  && errs.length === 0;
process.exit(ok ? 0 : 1);
