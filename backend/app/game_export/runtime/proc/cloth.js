// CLOTH (2026-10-27): a cape is cloth, and cloth moves.
//
// "a knight in a red cape" came out in plate with no cape at all: the
// character model is one sculpted body, and anything that should hang and
// swing off it is either missing or baked in solid. A cape is now a verlet
// sheet pinned across the back of the shoulders. Gravity hangs it, the body's
// own motion swings it (it trails a walk, streams behind a run, swings round
// a turn and settles when you stop), the wind lifts its hem, and spheres on
// the rig's bones keep it off the back and the legs.
//
// makeCape(THREE, root, { H, color, lining, wind }) -> { mesh, update(dt, fwdX, fwdZ, groundY, windX, windZ), reset() }
// makeBanner(THREE, { w, h, color, map }) -> { mesh, update(dt, windX, windZ) } (pinned along its top, for poles and walls)

function fabricTexture(THREE, hex, hem) {
  const c = document.createElement('canvas'); c.width = 128; c.height = 256;
  const g = c.getContext('2d'), col = new THREE.Color(hex);
  const css = (k, a = 1) => `rgba(${Math.round(Math.min(1, col.r * k) * 255)},${Math.round(Math.min(1, col.g * k) * 255)},${Math.round(Math.min(1, col.b * k) * 255)},${a})`;
  g.fillStyle = css(1); g.fillRect(0, 0, 128, 256);
  // the weave: fine crossing threads, a little uneven, as wool is
  for (let y = 0; y < 256; y += 2) { g.fillStyle = css(0.9 + ((y * 37) % 7) / 60, 0.5); g.fillRect(0, y, 128, 1); }
  for (let x = 0; x < 128; x += 2) { g.fillStyle = css(1.06, 0.25); g.fillRect(x, 0, 1, 256); }
  for (let k = 0; k < 900; k++) { g.fillStyle = css(0.75 + Math.random() * 0.5, 0.18); g.fillRect(Math.random() * 128, Math.random() * 256, 1 + Math.random() * 2, 1); }
  // a band of trim along the hem and a stitched seam inside it
  if (hem) { g.fillStyle = hem; g.fillRect(0, 238, 128, 12); g.fillStyle = 'rgba(0,0,0,0.35)'; for (let x = 0; x < 128; x += 5) g.fillRect(x, 233, 3, 1); }
  // worn darker at the hem, where it drags
  const gr = g.createLinearGradient(0, 180, 0, 256); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(20,12,8,0.28)');
  g.fillStyle = gr; g.fillRect(0, 180, 128, 76);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

function sheet(THREE, C, R, W, L) {
  const N = C * R, P = new Float32Array(N * 3), O = new Float32Array(N * 3), pin = new Uint8Array(N);
  const cons = [];
  const id = (i, j) => j * C + i;
  const add = (a, b, r) => cons.push(a, b, r);
  const dx = W / (C - 1), dy = L / (R - 1);
  for (let j = 0; j < R; j++) for (let i = 0; i < C; i++) {
    if (i < C - 1) add(id(i, j), id(i + 1, j), dx);
    if (j < R - 1) add(id(i, j), id(i, j + 1), dy);
    if (i < C - 1 && j < R - 1) { const d = Math.hypot(dx, dy); add(id(i, j), id(i + 1, j + 1), d); add(id(i + 1, j), id(i, j + 1), d); }
    if (j < R - 2) add(id(i, j), id(i, j + 2), dy * 2);          // bend: a cape hangs in folds, not in creases
    if (i < C - 2) add(id(i, j), id(i + 2, j), dx * 2);
  }
  const geo = new THREE.PlaneGeometry(1, 1, C - 1, R - 1);
  return { C, R, N, P, O, pin, cons: Float32Array.from(cons), geo, id, dx, dy };
}

function relax(S, iters) {
  const { P, pin, cons } = S;
  for (let it = 0; it < iters; it++) {
    for (let k = 0; k < cons.length; k += 3) {
      const a = cons[k] * 3, b = cons[k + 1] * 3, r = cons[k + 2];
      const x = P[b] - P[a], y = P[b + 1] - P[a + 1], z = P[b + 2] - P[a + 2];
      const d = Math.sqrt(x * x + y * y + z * z) || 1e-6;
      // cloth stretches a little and does not compress much: only pull when long, push weakly when short
      const diff = d > r ? (d - r) / d : (d - r) / d * 0.35;
      const wa = pin[cons[k]] ? 0 : 1, wb = pin[cons[k + 1]] ? 0 : 1, ws = wa + wb;
      if (!ws) continue;
      const fa = diff * wa / ws, fb = diff * wb / ws;
      P[a] += x * fa; P[a + 1] += y * fa; P[a + 2] += z * fa;
      P[b] -= x * fb; P[b + 1] -= y * fb; P[b + 2] -= z * fb;
    }
  }
}

function integrate(S, h, ax, ay, az, damp, gust) {
  const { P, O, pin, N } = S;
  for (let n = 0; n < N; n++) {
    if (pin[n]) continue;
    const k = n * 3, g = gust ? gust(n) : 1;
    const vx = (P[k] - O[k]) * damp, vy = (P[k + 1] - O[k + 1]) * damp, vz = (P[k + 2] - O[k + 2]) * damp;
    O[k] = P[k]; O[k + 1] = P[k + 1]; O[k + 2] = P[k + 2];
    P[k] += vx + ax * g * h * h; P[k + 1] += vy + ay * h * h; P[k + 2] += vz + az * g * h * h;
  }
}

function writeGeo(S) {
  const pa = S.geo.attributes.position;
  pa.array.set(S.P); pa.needsUpdate = true;
  S.geo.computeVertexNormals();
  S.geo.computeBoundingSphere();
}

export function makeCape(THREE, root, opt = {}) {
  const B = {};
  root.traverse(o => { if (!o.isBone) return; const n = o.name.toLowerCase();
    for (const k of ['hips', 'spine', 'chest', 'neck', 'head', 'uparm_l', 'uparm_r', 'upleg_l', 'upleg_r', 'lowleg_l', 'lowleg_r'])
      if (!B[k] && (n === k || n.endsWith(':' + k) || n.replace(/[^a-z_]/g, '') === k)) B[k] = o; });
  if (!B.neck || !B.uparm_l || !B.uparm_r || !(B.spine || B.hips)) return null;
  const H = opt.H || 1.8, s = H / 1.8;
  const C = 9, R = 14, S = sheet(THREE, C, R, 0.7 * s, (opt.length || 0.62) * H);
  const mat = new THREE.MeshStandardMaterial({ map: fabricTexture(THREE, opt.color || 0x9a1c1c, opt.hem || null), color: 0xffffff,
    roughness: 0.82, side: THREE.DoubleSide, shadowSide: THREE.DoubleSide });
  mat.userData.noAutoTex = true;
  // the lining shows where the cape turns over: a second, darker colour on the inner face
  if (opt.lining != null) {
    const lin = new THREE.Color(opt.lining);
    mat.onBeforeCompile = (sh) => { sh.uniforms.uLining = { value: lin };
      sh.fragmentShader = 'uniform vec3 uLining;\n' + sh.fragmentShader.replace('#include <map_fragment>',
        '#include <map_fragment>\n if (!gl_FrontFacing) diffuseColor.rgb = uLining * (0.7 + 0.3 * diffuseColor.g);'); };
  }
  const mesh = new THREE.Mesh(S.geo, mat);
  mesh.frustumCulled = false; mesh.castShadow = true; mesh.receiveShadow = true;
  for (let i = 0; i < C; i++) S.pin[S.id(i, 0)] = 1;
  const v = new THREE.Vector3(), sl = new THREE.Vector3(), sr = new THREE.Vector3(), nk = new THREE.Vector3();
  // spheres on the body that the cloth lies over (not the neck: it sits under the pinned edge and pulled a V into it)
  const SPH = [['spine', 0.17], ['chest', 0.16], ['hips', 0.19], ['upleg_l', 0.12], ['upleg_r', 0.12], ['lowleg_l', 0.1], ['lowleg_r', 0.1]]
    .filter(([n]) => B[n]).map(([n, r]) => ({ b: B[n], r: r * s, p: new THREE.Vector3() }));
  // and the middles of the thighs, which the hips' sphere does not reach
  const MID = [['upleg_l', 'lowleg_l'], ['upleg_r', 'lowleg_r']].filter(([a, b]) => B[a] && B[b]).map(([a, b]) => ({ a: B[a], b: B[b], r: 0.11 * s, p: new THREE.Vector3() }));
  let t = 0, fresh = true, lx = 0, lz = 0;
  function anchors(fx, fz) {
    B.uparm_l.getWorldPosition(sl); B.uparm_r.getWorldPosition(sr); B.neck.getWorldPosition(nk);
    // pinned along the tops of the shoulders and across the back of the neck, the ends a little forward over them
    const back = 0.11 * s, y0 = Math.max(sl.y, sr.y) * 0.4 + nk.y * 0.6 + 0.01 * s;
    for (let i = 0; i < C; i++) {
      const u = i / (C - 1), w = 1 - Math.pow(2 * u - 1, 2);
      v.copy(sl).lerp(sr, -0.04 + u * 1.08);
      const k = S.id(i, 0) * 3;
      S.P[k] = v.x - fx * (back * (0.25 + 0.75 * w)); S.P[k + 1] = y0 + w * 0.025 * s; S.P[k + 2] = v.z - fz * (back * (0.25 + 0.75 * w));
    }
  }
  function hang(fx, fz) {
    anchors(fx, fz);
    for (let j = 1; j < R; j++) for (let i = 0; i < C; i++) {
      const k = S.id(i, j) * 3, k0 = S.id(i, 0) * 3;
      S.P[k] = S.P[k0] - fx * 0.05 * j / R; S.P[k + 1] = S.P[k0 + 1] - S.dy * j; S.P[k + 2] = S.P[k0 + 2] - fz * 0.05 * j / R;
    }
    S.O.set(S.P);
  }
  function collide(groundY) {
    for (const q of SPH) q.b.getWorldPosition(q.p);
    for (const q of MID) { q.a.getWorldPosition(q.p); q.b.getWorldPosition(v); q.p.lerp(v, 0.5); }
    const all = SPH.concat(MID);
    for (let n = C; n < S.N; n++) {
      const k = n * 3;
      for (const q of all) {
        const x = S.P[k] - q.p.x, y = S.P[k + 1] - q.p.y, z = S.P[k + 2] - q.p.z, d2 = x * x + y * y + z * z, rr = q.r + 0.025 * s;
        if (d2 < rr * rr) { const d = Math.sqrt(d2) || 1e-5, f = (rr - d) / d; S.P[k] += x * f; S.P[k + 1] += y * f; S.P[k + 2] += z * f; }
      }
      if (S.P[k + 1] < groundY + 0.015) S.P[k + 1] = groundY + 0.015;
    }
  }
  function update(dt, fx, fz, groundY, wx = 0, wz = 0) {
    if (!mesh.visible) return;
    const fl = Math.hypot(fx, fz) || 1; fx /= fl; fz /= fl;
    B.neck.getWorldPosition(nk);
    // a teleport or the first frame hangs it straight rather than flinging it across the map
    if (fresh || Math.hypot(nk.x - lx, nk.z - lz) > 2.5) { hang(fx, fz); fresh = false; }
    lx = nk.x; lz = nk.z;
    const steps = dt > 1 / 45 ? 3 : 2, h = Math.min(dt, 1 / 20) / steps;
    for (let st = 0; st < steps; st++) {
      t += h;
      anchors(fx, fz);
      // wind: a steady push and gusts that run down the cloth, stronger at the free hem
      integrate(S, h, wx * 3.2, -9.81, wz * 3.2, 0.986, (n) => { const j = Math.floor(n / C), i = n % C;
        return (j / R) * (0.6 + 0.6 * Math.sin(t * 3.1 + j * 0.55 + i * 0.4) * Math.sin(t * 1.3 + i * 0.2)); });
      relax(S, 5);
      collide(groundY);
    }
    writeGeo(S);
  }
  return { mesh, update, reset: () => { fresh = true; }, bones: Object.keys(B) };
}

export function makeBanner(THREE, opt = {}) {
  const w = opt.w || 1.2, h = opt.h || 2.4, C = opt.cols || 7, R = opt.rows || 10;
  const S = sheet(THREE, C, R, w, h);
  const mat = new THREE.MeshStandardMaterial({ map: opt.map || fabricTexture(THREE, opt.color || 0x8a1a1a, opt.hem || null), roughness: 0.85, side: THREE.DoubleSide });
  mat.userData.noAutoTex = true;
  const mesh = new THREE.Mesh(S.geo, mat); mesh.frustumCulled = false; mesh.castShadow = true;
  // a banner hangs from its top edge; a flag on a pole is held down its side
  if (opt.pinSide) for (let j = 0; j < R; j++) S.pin[S.id(0, j)] = 1;
  else for (let i = 0; i < C; i++) S.pin[S.id(i, 0)] = 1;
  // local space: the top edge along x from 0 to w at y 0, hanging down -y; the mesh is placed by the caller
  for (let j = 0; j < R; j++) for (let i = 0; i < C; i++) { const k = S.id(i, j) * 3; S.P[k] = i * S.dx; S.P[k + 1] = -j * S.dy; S.P[k + 2] = 0; }
  S.O.set(S.P);
  let t = Math.random() * 10;
  const ph = Math.random() * 6;
  function update(dt, wx = 0, wz = 0) {
    const h2 = Math.min(dt, 1 / 20) / 2;
    for (let st = 0; st < 2; st++) {
      t += h2;
      integrate(S, h2, wx * (opt.pinSide ? 9 : 2.5), opt.pinSide ? -2.5 : -9.81, wz * (opt.pinSide ? 9 : 2.5), 0.985, (n) => {
        const j = Math.floor(n / C), i = n % C; return 0.5 + 0.7 * Math.sin(t * 2.6 + ph + i * 0.7 + j * 0.3); });
      relax(S, 4);
      // a banner against a wall stays in front of it
      if (opt.zMax != null || opt.zMin != null) for (let n = 0; n < S.N; n++) { const k = n * 3 + 2;
        if (opt.zMax != null && S.P[k] > opt.zMax) S.P[k] = opt.zMax; if (opt.zMin != null && S.P[k] < opt.zMin) S.P[k] = opt.zMin; }
    }
    writeGeo(S);
  }
  return { mesh, update };
}
