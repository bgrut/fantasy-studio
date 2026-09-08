// Is the factory standing ON the world, or hovering above it?
//
// Measured the only way that means anything: sample the ring of ground around
// a tile, put a machine on it, and sample the same pixels again. If the ground
// does not darken, the machine is floating — whatever the scene graph says
// about castShadow.
//
// Checked on a LIT face and an UNLIT one, because a single directional light
// can only shadow three of six and the contact shadows exist for the rest.
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
await p.goto(URL + '?fresh=1&debug=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,6000));

const probe = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const THREE_V = F.player.pos.constructor;               // Vector3
  window.__game.inspect(true);                            // orbit, so a face fills frame
  await new Promise(r => setTimeout(r, 900));

  const cv = document.querySelector('canvas');
  const gl = cv.getContext('webgl2') || cv.getContext('webgl');
  const px = new Uint8Array(4);
  const sample = (sx, sy) => {
    // readPixels is bottom-origin; every screen coordinate here is too
    gl.readPixels(sx | 0, sy | 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return (px[0] + px[1] + px[2]) / 3;
  };

  // the ring of ground around a tile, in screen space
  function ringOf(face, i, j) {
    const f = F.FACES[face], w = F.tileWorld(face, i, j), T = F.T;
    const pts = [];
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * Math.PI * 2;
      // Between the machine's own footprint and the outer edge of its contact
      // shadow. 0.85 sat past the shadow entirely; 0.55 landed on the machine
      // once every machine grew a skirt, and a sample on the machine reads the
      // same with the shadowing on or off. The band is narrow and it moves
      // when the art does — which is the point of measuring rather than
      // asserting a constant.
      const du = Math.cos(a) * T * 0.75, dv = Math.sin(a) * T * 0.75;
      const v = new THREE_V(
        w[0] + f.u[0] * du + f.v[0] * dv + f.n[0] * 0.05,
        w[1] + f.u[1] * du + f.v[1] * dv + f.n[1] * 0.05,
        w[2] + f.u[2] * du + f.v[2] * dv + f.n[2] * 0.05);
      v.project(window.__camera);
      const sx = (v.x * 0.5 + 0.5) * cv.width;
      const sy = (v.y * 0.5 + 0.5) * cv.height;         // already bottom-origin
      if (sx > 2 && sy > 2 && sx < cv.width - 2 && sy < cv.height - 2 && v.z < 1)
        pts.push([sx, sy]);
    }
    return pts;
  }
  const readAll = pts => pts.map(q => sample(q[0], q[1]));
  // THE STRONGEST POINTS, not the average. Some of the ring is behind the
  // machine and reads its body in both states, which contributes a zero to the
  // mean and drags a real shadow below any sensible threshold. The question is
  // "does a shadow land anywhere around this machine", and that is a max.
  const topDelta = (a, b, n) => {
    const d = a.map((v, k) => v - b[k]).sort((x, y) => y - x);
    return d.slice(0, n).reduce((s2, v) => s2 + v, 0) / n;
  };

  // aim the orbit camera down the face's own normal, or the ring projects onto
  // a face the camera cannot see and samples whatever is in front of it
  async function aimAt(face) {
    const n = F.FACES[face].n;
    F.orbit(Math.atan2(n[0], n[2]), Math.asin(Math.max(-0.99, Math.min(0.99, n[1]))),
            F.HALF * 2.6);
    await new Promise(r => setTimeout(r, 700));
  }

  async function testFace(face, label) {
    // FROM THE CENTRE OUT. Scanning from a corner picked a tile that projects
    // to the very edge of the frame, where the ring samples land on a
    // neighbouring face or on empty sky — and two identical readings of the
    // sky look exactly like a shadow that is not being drawn.
    let spot = null;
    const mid = Math.floor(F.N / 2);
    for (let r = 0; r < mid - 2 && !spot; r++)
      for (let a = -r; a <= r && !spot; a++)
        for (let c = -r; c <= r && !spot; c++) {
          if (Math.max(Math.abs(a), Math.abs(c)) !== r) continue;
          const i = mid + a, j = mid + c;
          if (i < 2 || j < 2 || i >= F.N - 2 || j >= F.N - 2) continue;
          let ok = true;
          for (let x = -1; x <= 1; x++) for (let y = -1; y <= 1; y++)
            if (F.cells[face][i + x][j + y].t !== TY.EMPTY) ok = false;
          if (ok) spot = [i, j];
        }
    if (!spot) return { label, skipped: true };
    await aimAt(face);
    const pts = ringOf(face, spot[0], spot[1]);
    if (pts.length < 4) return { label, skipped: 'off screen' };
    F.place(face, spot[0], spot[1], TY.SMELTER, 0);
    await new Promise(r => setTimeout(r, 700));
    // TOGGLE THE SHADOWING, not the machine. Adding a machine also adds its own
    // bright body to the frame, which on the first attempt made the ground read
    // BRIGHTER when a smelter was placed on it. Turning the shadowing off with
    // the machine still standing isolates exactly the thing being measured.
    const litAll = readAll(pts);
    const contact = window.__scene.getObjectByName('contact');
    window.__renderer.shadowMap.enabled = false;
    contact.visible = false;
    window.__scene.traverse(o => { if (o.material)
      (Array.isArray(o.material) ? o.material : [o.material])
        .forEach(m => { m.needsUpdate = true; }); });
    await new Promise(r => setTimeout(r, 700));
    const flatAll = readAll(pts);
    window.__renderer.shadowMap.enabled = true;
    contact.visible = true;
    window.__scene.traverse(o => { if (o.material)
      (Array.isArray(o.material) ? o.material : [o.material])
        .forEach(m => { m.needsUpdate = true; }); });
    F.removeAt(face, spot[0], spot[1]);
    await new Promise(r => setTimeout(r, 400));
    const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
    return { label, spot, samples: pts.length,
             before: +mean(flatAll).toFixed(1), after: +mean(litAll).toFixed(1),
             darkened: +topDelta(flatAll, litAll, 3).toFixed(1) };
  }

  // face 0 is lit by the key light; face 1 is the underside, which only the
  // fill reaches and where the contact shadow is the whole story
  const lit = await testFace(0, 'lit face (top)');
  const dark = await testFace(1, 'unlit face (bottom)');
  return { lit, dark,
           decals: (() => { const o = window.__scene.getObjectByName('contact');
                            return o ? o.count : -1; })() };
});

for (const r of [probe.lit, probe.dark]) {
  if (r.skipped) { console.log(r.label.padEnd(20), 'skipped:', r.skipped); continue; }
  console.log(r.label.padEnd(20),
    'ring mean', r.before, '-> ', r.after, '| strongest darkening', r.darkened,
    r.darkened > 4 ? '  GROUNDED' : '  FLOATING');
}
console.log('contact shadows drawn:', probe.decals);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'ground.png' });
await b.close();
const ok = probe.lit.darkened > 4 && probe.dark.darkened > 4
  && probe.decals > 0 && errs.length === 0;
process.exit(ok ? 0 : 1);
