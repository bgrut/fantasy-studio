// ── THE CAVE (2026-10-03) ───────────────────────────────────────────────────
// "Explore a glowing crystal cave deep underground" built an open field at
// night under the stars. Underground is a different kind of place: no sky,
// a roof over you, walls close on either side, and the only light what the
// cave makes itself and what you carry. level.py carves the floor into a
// tunnel that opens into chambers (its walls are the ground, so they are
// solid); this hangs the rest of the cave over it:
//
//   roof       a rock ceiling ten-odd metres up, lower and lumpier between
//              chambers, curtained with stalactites; stalagmites rise at the
//              foot of the walls
//   crystals   clusters of glowing shards along the walls in the cave's own
//              colours, the light of the place: six coloured lights follow
//              the hero from cluster to cluster so the walls and the hero are
//              lit by them
//   life       glow-worms speckle the roof and twinkle; water drips from it
//              into small still puddles that ring when a drop lands; dust
//              hangs in the hero's lamp light
//   air        black beyond the light, a short cold fog, no sky at all
//
// The camera is kept under the roof and out of the walls. Procedural, no
// assets except the ground's own rock photo.
import * as THREE from 'three';
import { waterMaterial } from './water.js';

function mulberry(a) {
  return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
function vnoise(seed) {
  const P = new Uint8Array(512), r = mulberry(seed);
  for (let i = 0; i < 256; i++) P[i] = i;
  for (let i = 255; i > 0; i--) { const j = Math.floor(r() * (i + 1)); const t = P[i]; P[i] = P[j]; P[j] = t; }
  for (let i = 0; i < 256; i++) P[i + 256] = P[i];
  return (x, z) => {
    const xi = Math.floor(x), zi = Math.floor(z), xf = x - xi, zf = z - zi;
    const h = (a, b) => P[(P[a & 255] + b) & 511] / 255;
    const u = xf * xf * (3 - 2 * xf), v = zf * zf * (3 - 2 * zf);
    const A = h(xi, zi), B = h(xi + 1, zi), C = h(xi, zi + 1), D = h(xi + 1, zi + 1);
    return A + (B - A) * u + (C - A) * v + (A - B - C + D) * u * v;
  };
}

/** the cave's crystal colours, from the sentence */
function crystalColours(words) {
  const w = words || '';
  if (/amethyst|purple|violet/.test(w)) return [0xa46cff, 0xd08cff];
  if (/emerald|green|jade/.test(w)) return [0x3dff9a, 0x9cffd0];
  if (/ruby|red|crimson|fire/.test(w)) return [0xff4a5e, 0xff9a6a];
  if (/gold|amber|topaz/.test(w)) return [0xffb43c, 0xffe08a];
  if (/ice|frozen|sapphire|blue/.test(w)) return [0x4ab8ff, 0xa8e6ff];
  return [0x4fd6ff, 0xb27cff];                       // the classic: cyan and violet
}

export function createCave({ scene, level, gsize, hAt, camera, seed = 1, words = '', clock = { value: 0 },
                             lights = {} }) {
  const rnd = mulberry(seed * 13 + 5);
  const n1 = vnoise(seed + 101), n2 = vnoise(seed + 202);
  const half = gsize / 2;
  const C0 = (level.cave && level.cave.ceiling) || 11;
  const chambers = [[0, 0, 17], [level.goal[0], level.goal[1], 18]];
  const facts = { roof: false, stalactites: 0, stalagmites: 0, clusters: 0, shards: 0, lights: 0, glowworms: 0, drips: 0 };

  // the roof's height: higher in the chambers, lumpy, pulled down into curtains
  const ceilAt = (x, z) => {
    let ch = 0;
    for (const [cx, cz, r] of chambers) ch = Math.max(ch, 1 - Math.min(1, Math.hypot(x - cx, z - cz) / (r * 1.6)));
    const lump = (n1(x * 0.06, z * 0.06) - 0.5) * 5 + (n2(x * 0.21, z * 0.21) - 0.5) * 1.6;
    const curtain = Math.pow(Math.abs(Math.sin(x * 0.17 + n2(x * 0.05, z * 0.05) * 6)), 8) * 1.8;
    return C0 - 2 + ch * 3.5 + lump - curtain;
  };
  const isOpen = (x, z) => Math.abs(x) < half * 0.97 && Math.abs(z) < half * 0.97 && hAt(x, z) < 1.2;

  // ── the atmosphere: no sky ────────────────────────────────────────────────
  scene.background = new THREE.Color(0x020305);
  if (scene.fog && scene.fog.isFog) { scene.fog.color.set(0x06080d); scene.fog.near = 8; scene.fog.far = 75; }
  if ('environmentIntensity' in scene) scene.environmentIntensity = 0.08;
  if (lights.hemi) { lights.hemi.intensity *= 0.35; lights.hemi.color.set(crystalColours(words)[0]).multiplyScalar(0.5); lights.hemi.groundColor.set(0x0a0a10); }
  if (lights.sun) lights.sun.intensity *= 0.08;
  if (lights.csm) for (const l of lights.csm.lights || []) l.intensity *= 0.08;
  if (lights.heroFill) { lights.heroFill.intensity = 22; lights.heroFill.distance = 15; lights.heroFill.color.set(0xffd9a8); }   // the hero's lamp

  // ── the roof ──────────────────────────────────────────────────────────────
  const tl = new THREE.TextureLoader();
  const rmap = tl.load('textures/cliff.jpg'), rnrm = tl.load('textures/cliff_n.jpg');
  rmap.colorSpace = THREE.SRGBColorSpace;
  for (const t of [rmap, rnrm]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; }
  {
    const N = 120, pos = new Float32Array((N + 1) * (N + 1) * 3), uv = new Float32Array((N + 1) * (N + 1) * 2), idx = [];
    for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
      const x = (j / N - 0.5) * gsize, z = (i / N - 0.5) * gsize, k = i * (N + 1) + j;
      pos[k * 3] = x; pos[k * 3 + 1] = ceilAt(x, z); pos[k * 3 + 2] = z;
      uv[k * 2] = x / 7; uv[k * 2 + 1] = z / 7;
    }
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
      const a = i * (N + 1) + j, b = a + N + 1;
      idx.push(a, a + 1, b, a + 1, b + 1, b);              // wound to face down
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    g.setIndex(idx);
    g.computeVertexNormals();
    const m = new THREE.MeshStandardMaterial({ color: 0x5a5550, map: rmap, normalMap: rnrm, roughness: 0.75, side: THREE.DoubleSide });
    m.userData.noAutoTex = true;
    const roof = new THREE.Mesh(g, m);
    roof.name = 'caveRoof';
    roof.castShadow = true; roof.receiveShadow = true;
    scene.add(roof);
    facts.roof = true;
  }

  // ── stalactites and stalagmites ───────────────────────────────────────────
  const wetRock = new THREE.MeshStandardMaterial({ color: 0x7a7068, map: rmap, roughness: 0.32, metalness: 0.05 });
  wetRock.userData.noAutoTex = true;
  const spikeG = new THREE.ConeGeometry(0.5, 1, 9, 3);
  {
    const pa = spikeG.attributes.position;               // a little irregular, like dripped stone
    for (let v = 0; v < pa.count; v++) {
      const y = pa.getY(v), k = 1 + 0.18 * Math.sin(y * 9 + pa.getX(v) * 4);
      pa.setX(v, pa.getX(v) * k); pa.setZ(v, pa.getZ(v) * k);
    }
    spikeG.computeVertexNormals();
  }
  const M4 = new THREE.Matrix4(), Q = new THREE.Quaternion(), E = new THREE.Euler(), V = new THREE.Vector3(), S = new THREE.Vector3();
  {
    const spots = [];
    for (let t = 0; t < 6000 && spots.length < 320; t++) {
      const x = (rnd() - 0.5) * gsize, z = (rnd() - 0.5) * gsize;
      if (!isOpen(x, z)) continue;
      spots.push([x, z]);
    }
    const im = new THREE.InstancedMesh(spikeG, wetRock, spots.length);
    spots.forEach(([x, z], k) => {
      const hgt = 0.8 + Math.pow(rnd(), 2) * 4.2, rad = hgt * (0.12 + rnd() * 0.08);
      E.set(Math.PI + (rnd() - 0.5) * 0.12, rnd() * 6.28, (rnd() - 0.5) * 0.12);
      M4.compose(V.set(x, ceilAt(x, z) - hgt / 2 + 0.2, z), Q.setFromEuler(E), S.set(rad * 2, hgt, rad * 2));
      im.setMatrixAt(k, M4);
    });
    im.castShadow = true; im.receiveShadow = true; im.name = 'stalactites';
    scene.add(im);
    facts.stalactites = spots.length;
  }
  const path = level.path || [[0, 0], level.goal];
  const segD = (x, z) => {
    let best = 1e9;
    for (let k = 0; k < path.length - 1; k++) {
      const [ax, az] = path[k], [bx, bz] = path[k + 1];
      const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz || 1;
      const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2));
      best = Math.min(best, Math.hypot(x - ax - dx * t, z - az - dz * t));
    }
    return best;
  };
  // the foot of a wall: open ground (or nearly) with rock rising close by
  const wallFoot = (x, z) => {
    const h = hAt(x, z);
    if (h > 2.2 || h < -0.5) return false;
    for (const [dx, dz] of [[3, 0], [-3, 0], [0, 3], [0, -3]]) if (hAt(x + dx, z + dz) > h + 1.6) return true;
    return false;
  };
  {
    const spots = [];
    for (let t = 0; t < 8000 && spots.length < 160; t++) {
      const x = (rnd() - 0.5) * gsize, z = (rnd() - 0.5) * gsize;
      if (Math.abs(x) > half * 0.95 || Math.abs(z) > half * 0.95 || segD(x, z) < 6 || !wallFoot(x, z)) continue;
      spots.push([x, z]);
    }
    const im = new THREE.InstancedMesh(spikeG, wetRock, spots.length);
    spots.forEach(([x, z], k) => {
      const hgt = 0.6 + Math.pow(rnd(), 1.6) * 3.2, rad = hgt * (0.18 + rnd() * 0.1);
      E.set((rnd() - 0.5) * 0.1, rnd() * 6.28, (rnd() - 0.5) * 0.1);
      M4.compose(V.set(x, hAt(x, z) + hgt / 2 - 0.15, z), Q.setFromEuler(E), S.set(rad * 2, hgt, rad * 2));
      im.setMatrixAt(k, M4);
    });
    im.castShadow = true; im.receiveShadow = true; im.name = 'stalagmites';
    scene.add(im);
    facts.stalagmites = spots.length;
  }

  // ── crystals ──────────────────────────────────────────────────────────────
  const cols = crystalColours(words).map(h => new THREE.Color(h));
  const shardG = new THREE.CylinderGeometry(0.06, 0.5, 1, 6, 1);
  shardG.translate(0, 0.5, 0);                          // grows from its base
  const clusters = [];
  for (let t = 0; t < 12000 && clusters.length < 64; t++) {
    const x = (rnd() - 0.5) * gsize, z = (rnd() - 0.5) * gsize;
    if (Math.abs(x) > half * 0.95 || Math.abs(z) > half * 0.95 || segD(x, z) < 4.5 || !wallFoot(x, z)) continue;
    if (clusters.some(c => Math.hypot(c.x - x, c.z - z) < 7)) continue;
    // lean away from the wall: toward the lowest neighbour
    let lx = 0, lz = 0;
    for (const [dx, dz] of [[2, 0], [-2, 0], [0, 2], [0, -2]]) { const dh = hAt(x + dx, z + dz) - hAt(x, z); lx -= dx * dh; lz -= dz * dh; }
    const ll = Math.hypot(lx, lz) || 1;
    clusters.push({ x, z, y: hAt(x, z), lx: lx / ll, lz: lz / ll, col: cols[clusters.length % cols.length].clone().offsetHSL((rnd() - 0.5) * 0.04, 0, 0) });
  }
  const shards = [];
  for (const c of clusters) {
    const n = 5 + Math.floor(rnd() * 6), big = 0.8 + rnd() * 1.6;
    for (let k = 0; k < n; k++) {
      const hgt = big * (0.35 + rnd() * 0.75), rad = hgt * (0.16 + rnd() * 0.08);
      const ox = (rnd() - 0.5) * 1.6, oz = (rnd() - 0.5) * 1.6;
      // tilt: outward from the cluster's centre and away from the wall
      const tx = ox * 0.35 + c.lx * 0.45, tz = oz * 0.35 + c.lz * 0.45;
      shards.push({ x: c.x + ox, y: c.y - 0.1, z: c.z + oz, hgt, rad, rx: tz * 0.9, rz: -tx * 0.9, ry: rnd() * 6.28, col: c.col });
    }
  }
  const crystalMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 1.6,
    roughness: 0.12, metalness: 0.0, transparent: true, opacity: 0.92 });
  crystalMat.userData.noAutoTex = true;
  crystalMat.onBeforeCompile = (sh) => {
    sh.uniforms.uTime = clock;
    sh.fragmentShader = 'uniform float uTime;\n' + sh.fragmentShader.replace('#include <emissivemap_fragment>',
      `#include <emissivemap_fragment>
      totalEmissiveRadiance *= vColor * (0.85 + 0.15 * sin(uTime * 0.9 + vViewPosition.x * 0.3));
      diffuseColor.rgb *= 0.35;`);
  };
  crystalMat.customProgramCacheKey = () => 'cave-crystal';
  {
    const im = new THREE.InstancedMesh(shardG, crystalMat, Math.max(1, shards.length));
    shards.forEach((s, k) => {
      E.set(s.rx, s.ry, s.rz);
      M4.compose(V.set(s.x, s.y, s.z), Q.setFromEuler(E), S.set(s.rad * 2, s.hgt, s.rad * 2));
      im.setMatrixAt(k, M4);
      im.setColorAt(k, s.col);
    });
    im.count = shards.length;
    im.name = 'crystals';
    scene.add(im);
    facts.clusters = clusters.length; facts.shards = shards.length;
  }
  // six coloured lights that walk with the hero from cluster to cluster
  const glows = [];
  for (let k = 0; k < 6; k++) {
    const L = new THREE.PointLight(0xffffff, 0, 22, 1.4);
    scene.add(L);
    glows.push({ L, base: 0, ph: rnd() * 6.28 });
  }
  const roofLight = new THREE.PointLight(0x9fb8d8, 16, 20, 1.3);
  scene.add(roofLight);
  facts.lights = glows.length + 1;
  let glowT = 0;
  function placeGlows(px, pz) {
    const near = clusters.map(c => [c, (c.x - px) ** 2 + (c.z - pz) ** 2]).sort((a, b) => a[1] - b[1]);
    glows.forEach((g, k) => {
      const c = near[k] && near[k][1] < 70 * 70 ? near[k][0] : null;
      if (!c) { g.base = 0; return; }
      g.L.position.set(c.x + c.lx * 1.4, c.y + 2.6, c.z + c.lz * 1.4);
      g.L.color.copy(c.col);
      g.base = 48;
    });
  }

  // ── glow-worms on the roof ────────────────────────────────────────────────
  const dotTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 32;
    const g = c.getContext('2d'), gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.3, 'rgba(255,255,255,0.5)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 32, 32);
    return new THREE.CanvasTexture(c);
  })();
  const worms = [];
  for (let grp = 0; grp < 2; grp++) {
    const pos = [];
    for (let t = 0; t < 20000 && pos.length < 1400 * 3; t++) {
      const x = (rnd() - 0.5) * gsize, z = (rnd() - 0.5) * gsize;
      if (!isOpen(x, z) || n1(x * 0.04 + 9, z * 0.04) < 0.45) continue;    // they gather in colonies
      pos.push(x, ceilAt(x, z) - 0.08, z);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    const m = new THREE.PointsMaterial({ map: dotTex, size: 0.14, color: new THREE.Color(0.35, 1.6, 1.35), transparent: true,
      depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true, fog: true });
    m.userData.noAutoTex = true;
    const p = new THREE.Points(g, m);
    p.name = 'glowworms';
    scene.add(p);
    worms.push(p);
    facts.glowworms += pos.length / 3;
  }

  // ── drips and puddles ─────────────────────────────────────────────────────
  const drips = [];
  const dropMat = new THREE.SpriteMaterial({ map: dotTex, color: 0xcfe6ff, transparent: true, depthWrite: false, opacity: 0.9 });
  dropMat.userData.noAutoTex = true;
  const ringMat = new THREE.MeshBasicMaterial({ color: 0xbcd4e8, transparent: true, depthWrite: false, opacity: 0 });
  ringMat.userData.noAutoTex = true;
  for (let t = 0; t < 4000 && drips.length < 14; t++) {
    const x = (rnd() - 0.5) * gsize * 0.9, z = (rnd() - 0.5) * gsize * 0.9;
    const sd = segD(x, z);
    if (!isOpen(x, z) || sd < 2.5 || sd > 9) continue;
    if (drips.some(d => Math.hypot(d.x - x, d.z - z) < 10)) continue;
    const fy = hAt(x, z) + 0.03, cy = ceilAt(x, z) - 0.3;
    const pr = 0.7 + rnd() * 1.1;
    const pool = new THREE.Mesh(new THREE.CircleGeometry(pr, 24), waterMaterial('lake', clock));
    pool.rotation.x = -Math.PI / 2; pool.position.set(x, fy, z); pool.renderOrder = 2;
    scene.add(pool);
    const drop = new THREE.Sprite(dropMat.clone()); drop.scale.set(0.06, 0.16, 1);
    scene.add(drop);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.8, 1, 24), ringMat.clone());
    ring.rotation.x = -Math.PI / 2; ring.position.set(x, fy + 0.01, z);
    scene.add(ring);
    drips.push({ x, z, fy, cy, t: rnd() * 2, every: 1.4 + rnd() * 2.2, drop, ring, rt: 9 });
  }
  facts.drips = drips.length;

  // ── dust in the lamp light ────────────────────────────────────────────────
  const DN = 260, dpos = new Float32Array(DN * 3);
  for (let i = 0; i < DN; i++) { dpos[i * 3] = (rnd() - 0.5) * 16; dpos[i * 3 + 1] = rnd() * 5; dpos[i * 3 + 2] = (rnd() - 0.5) * 16; }
  const dg = new THREE.BufferGeometry(); dg.setAttribute('position', new THREE.BufferAttribute(dpos, 3));
  const dust = new THREE.Points(dg, new THREE.PointsMaterial({ map: dotTex, size: 0.035, color: 0xffe2b8, transparent: true,
    opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true }));
  dust.material.userData.noAutoTex = true;
  dust.frustumCulled = false;
  scene.add(dust);

  // ── the camera stays in the cave ──────────────────────────────────────────
  const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _p = new THREE.Vector3();
  function clampCamera(cam, target) {
    if (!target) return;
    _a.set(target.x, target.y + 1.5, target.z);
    _b.copy(cam.position);
    let ok = 1;
    for (let s = 1; s <= 14; s++) {
      const f = s / 14;
      _p.lerpVectors(_a, _b, f);
      if (hAt(_p.x, _p.z) > _p.y - 0.35 || ceilAt(_p.x, _p.z) < _p.y + 0.6) { ok = (s - 1) / 14; break; }
    }
    if (ok < 1) cam.position.lerpVectors(_a, _b, Math.max(0.12, ok));
    const top = ceilAt(cam.position.x, cam.position.z) - 0.6;
    if (cam.position.y > top) cam.position.y = top;
  }

  function update(dt, cam, playerPos) {
    const t = clock.value;
    if (playerPos && (glowT -= dt) <= 0) { glowT = 0.5; placeGlows(playerPos.x, playerPos.z); }
    if (playerPos) roofLight.position.set(playerPos.x, Math.min(playerPos.y + 5.5, ceilAt(playerPos.x, playerPos.z) - 1.5), playerPos.z);
    for (const g of glows) g.L.intensity = g.base * (0.9 + 0.1 * Math.sin(t * 1.3 + g.ph));
    worms[0].material.opacity = 0.65 + 0.35 * Math.sin(t * 0.8);
    worms[1].material.opacity = 0.65 + 0.35 * Math.sin(t * 0.8 + 2.4);
    for (const d of drips) {
      d.t += dt;
      const fallT = Math.sqrt(2 * (d.cy - d.fy) / 9.8);
      if (d.t > d.every) { d.t = 0; d.rt = 0; }
      if (d.t < fallT) {
        d.drop.visible = true;
        d.drop.position.set(d.x, d.cy - 0.5 * 9.8 * d.t * d.t, d.z);
      } else {
        if (d.drop.visible) { d.drop.visible = false; d.rt = 0; }
      }
      d.rt += dt;
      const r = 0.05 + d.rt * 0.9;
      d.ring.scale.set(r, r, 1);
      d.ring.material.opacity = Math.max(0, 0.5 - d.rt * 0.6);
    }
    if (cam) {
      const p = cam.position;
      for (let i = 0; i < DN; i++) {
        const o = i * 3;
        dpos[o] += Math.sin(t * 0.3 + i) * dt * 0.05; dpos[o + 1] += Math.cos(t * 0.2 + i * 1.7) * dt * 0.03;
        for (const ax of [0, 2]) {
          const c = ax === 0 ? p.x : p.z;
          if (dpos[o + ax] - c > 8) dpos[o + ax] -= 16; else if (dpos[o + ax] - c < -8) dpos[o + ax] += 16;
        }
        if (dpos[o + 1] - p.y > 3) dpos[o + 1] -= 5; else if (dpos[o + 1] - p.y < -2) dpos[o + 1] += 5;
      }
      dg.attributes.position.needsUpdate = true;
    }
  }
  return { update, clampCamera, ceilAt, facts: () => Object.assign({}, facts) };
}
