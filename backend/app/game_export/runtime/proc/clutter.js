// ── WHAT LIES ON THE GROUND (2026-10-04) ────────────────────────────────────
// Up close the ground was a photograph and nothing else: however good the
// scan, a pebble in a picture has no shadow and no edge, and the first metre
// in front of the camera is where the eye looks hardest. Real ground carries
// small loose things. This lays them in a window that travels with the
// camera, cell by cell, the same cell always holding the same things:
//
//   pebbles   many tiny, a few larger, each its own lumpy stone, in the colour
//             of the world's rock with a little variation stone to stone
//   twigs     thin bent sticks with a side shoot, lying where they fell
//   leaves    small curled leaves in dried and living colours, under trees
//
// Every item sits on the terrain and tilts with its slope; pebbles sink a
// little into it. What the world says to keep clear (buildings, water, lava,
// the walked middle of the trail for leaves) is asked through keepOut.
import * as THREE from 'three';

function mulberry(a) {
  return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const hash2 = (x, z, s) => ((x * 73856093) ^ (z * 19349663) ^ (s * 83492791)) >>> 0;

function pebbleGeo(seed) {
  const r = mulberry(seed);
  const g = new THREE.IcosahedronGeometry(1, 2);
  const p = g.attributes.position, v = new THREE.Vector3();
  const sx = 0.8 + r() * 0.5, sz = 0.8 + r() * 0.5, sy = 0.42 + r() * 0.25;
  const a1 = r() * 6, a2 = r() * 6;
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    // a smooth lumpy stone: two low waves, not random spikes
    const k = 1 + 0.12 * Math.sin(v.x * 2.3 + a1) * Math.cos(v.z * 2.1 + a2) + 0.06 * Math.sin(v.y * 4 + a1);
    p.setXYZ(i, v.x * sx * k, v.y * sy * k, v.z * sz * k);
  }
  g.computeVertexNormals();
  return g;
}
function twigGeo(seed) {
  const r = mulberry(seed);
  const parts = [];
  const main = new THREE.CylinderGeometry(0.5, 0.35, 1, 5, 6, false);
  main.rotateZ(Math.PI / 2);                       // lies along x
  const p = main.attributes.position;
  const bend = (r() - 0.5) * 0.12, kink = r() * 6;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    p.setZ(i, p.getZ(i) + Math.sin(x * 3 + kink) * bend);
    p.setY(i, p.getY(i) + Math.sin(x * 2.2 + kink) * bend * 0.4);
  }
  parts.push(main);
  const side = new THREE.CylinderGeometry(0.3, 0.2, 0.35, 4, 1);
  side.rotateZ(Math.PI / 2); side.rotateY(0.6 + r() * 0.5); side.translate(0.12, 0, 0.08);
  parts.push(side);
  const g = mergeSimple(parts);
  g.computeVertexNormals();
  return g;
}
function leafGeo(seed) {
  const r = mulberry(seed);
  const g = new THREE.PlaneGeometry(1, 0.62, 4, 2);
  g.rotateX(-Math.PI / 2);
  const p = g.attributes.position;
  const curl = 0.12 + r() * 0.2, twist = (r() - 0.5) * 0.2;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), z = p.getZ(i);
    const taper = 1 - Math.pow(Math.abs(x) * 2, 2) * 0.9;     // pointed at both ends
    p.setZ(i, z * Math.max(0.08, taper));
    p.setY(i, (z * z) * curl * 4 + x * twist + Math.abs(x) * 0.05);
  }
  g.computeVertexNormals();
  return g;
}
function mergeSimple(geos) {
  const pos = [], idx = [];
  let base = 0;
  for (const g0 of geos) {
    const g = g0.index ? g0 : g0;
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) pos.push(p.getX(i), p.getY(i), p.getZ(i));
    if (g.index) for (let i = 0; i < g.index.count; i++) idx.push(g.index.getX(i) + base);
    else for (let i = 0; i < p.count; i++) idx.push(i + base);
    base += p.count;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  out.setIndex(idx);
  return out;
}

/**
 * o: { scene, seed, hAt(x,z), keepOut(x,z,kind) -> bool, density: { pebble, twig, leaf } per m²,
 *      rockCol, twigCol, leafCols: [THREE.Color], radius, cell }
 */
export function plantClutter(o) {
  const radius = o.radius || 24, cell = o.cell || 6;
  const D = Object.assign({ pebble: 0.8, twig: 0.1, leaf: 0 }, o.density || {});
  const span = Math.ceil(radius / cell);
  const cells = (2 * span + 1) ** 2;
  const per = { pebble: Math.ceil(D.pebble * cell * cell), twig: Math.ceil(D.twig * cell * cell), leaf: Math.ceil(D.leaf * cell * cell) };
  const kinds = [];
  const mk = (name, geos, mat, n) => {
    if (n <= 0) return;
    const meshes = geos.map(g => {
      const m = new THREE.InstancedMesh(g, mat, Math.ceil(cells * n / geos.length) + 8);
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      m.receiveShadow = true; m.castShadow = name === 'pebble';
      m.frustumCulled = false; m.count = 0; m.name = 'clutter_' + name;
      m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(m.instanceMatrix.count * 3), 3);
      o.scene.add(m);
      return m;
    });
    kinds.push({ name, meshes, n });
  };
  const stoneMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.82, metalness: 0.0 });
  // a stone wears the photographed rock (the same face the boulders wear),
  // projected in world space so every pebble shows a different patch of it
  if (o.rockTex) {
    stoneMat.onBeforeCompile = (sh) => {
      sh.uniforms.uRk = { value: o.rockTex };
      sh.vertexShader = 'varying vec3 vCkP; varying vec3 vCkN;\n' + sh.vertexShader.replace('#include <worldpos_vertex>',
        `#include <worldpos_vertex>
        #ifdef USE_INSTANCING
          vCkP = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;
          vCkN = normalize(mat3(modelMatrix * instanceMatrix) * objectNormal);
        #else
          vCkP = (modelMatrix * vec4(transformed, 1.0)).xyz; vCkN = normalize(mat3(modelMatrix) * objectNormal);
        #endif`);
      sh.fragmentShader = 'uniform sampler2D uRk; varying vec3 vCkP; varying vec3 vCkN;\n' + sh.fragmentShader.replace('#include <color_fragment>',
        `#include <color_fragment>
        {
          vec3 bw = pow(abs(normalize(vCkN)), vec3(4.0)); bw /= (bw.x + bw.y + bw.z + 1e-5);
          vec3 tp = vCkP * 2.2;
          vec3 rk = texture2D(uRk, tp.zy).rgb * bw.x + texture2D(uRk, tp.xz).rgb * bw.y + texture2D(uRk, tp.xy).rgb * bw.z;
          diffuseColor.rgb *= rk * 2.0;
        }`);
    };
    stoneMat.customProgramCacheKey = () => 'clutter-stone';
  }
  const twigMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95 });
  const leafMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, side: THREE.DoubleSide });
  for (const m of [stoneMat, twigMat, leafMat]) m.userData.noAutoTex = true;
  mk('pebble', [0, 1, 2, 3].map(k => pebbleGeo((o.seed || 1) * 7 + k)), stoneMat, per.pebble);
  mk('twig', [0, 1, 2].map(k => twigGeo((o.seed || 1) * 11 + k)), twigMat, per.twig);
  mk('leaf', [0, 1, 2].map(k => leafGeo((o.seed || 1) * 13 + k)), leafMat, per.leaf);

  const rockCol = (o.rockCol || new THREE.Color(0x7d756c)).clone();
  const twigCol = (o.twigCol || new THREE.Color(0x5a4632)).clone();
  const leafCols = (o.leafCols && o.leafCols.length ? o.leafCols : [new THREE.Color(0x8a6a3a), new THREE.Color(0x6f7a3a), new THREE.Color(0xa0582c)]).map(c => c.clone());
  const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), Qy = new THREE.Quaternion(), P = new THREE.Vector3(), S = new THREE.Vector3();
  const UP = new THREE.Vector3(0, 1, 0), N = new THREE.Vector3(), C = new THREE.Color();
  let lastKey = null, placed = 0;

  function normalAt(x, z) {
    const e = 0.4;
    return N.set(o.hAt(x - e, z) - o.hAt(x + e, z), 2 * e, o.hAt(x, z - e) - o.hAt(x, z + e)).normalize();
  }
  function rebuild(cx, cz) {
    placed = 0;
    for (const k of kinds) for (const m of k.meshes) m.count = 0;
    for (let a = -span; a <= span; a++) for (let b = -span; b <= span; b++) {
      const gx = cx + a, gz = cz + b;
      const r = mulberry(hash2(gx, gz, o.seed || 1));
      for (const k of kinds) {
        for (let n = 0; n < k.n; n++) {
          const x = (gx + r()) * cell, z = (gz + r()) * cell;
          const pick = Math.floor(r() * k.meshes.length), rot = r() * Math.PI * 2, u = r(), w = r(), w2 = r();
          if (o.keepOut && o.keepOut(x, z, k.name)) continue;
          const m = k.meshes[pick];
          if (m.count >= m.instanceMatrix.count) continue;
          const y = o.hAt(x, z);
          Q.setFromUnitVectors(UP, normalAt(x, z));
          Qy.setFromAxisAngle(UP, rot);
          Q.multiply(Qy);
          let s;
          if (k.name === 'pebble') {
            s = 0.012 + Math.pow(u, 3.6) * 0.11;         // many tiny, a few larger
            P.set(x, y - s * 0.22, z); S.setScalar(s);
            C.copy(rockCol).offsetHSL((w - 0.5) * 0.03, (w2 - 0.5) * 0.08, (u - 0.5) * 0.14);
          } else if (k.name === 'twig') {
            s = 0.18 + u * 0.45;
            P.set(x, y + 0.008, z); S.set(s, 0.022 + w * 0.012, 0.022 + w * 0.012);
            C.copy(twigCol).offsetHSL(0, (w2 - 0.5) * 0.1, (u - 0.5) * 0.12);
          } else {
            s = 0.055 + u * 0.06;
            P.set(x, y + 0.006, z); S.setScalar(s);
            C.copy(leafCols[Math.floor(w * leafCols.length) % leafCols.length]).offsetHSL((w2 - 0.5) * 0.04, 0, (u - 0.5) * 0.1);
          }
          M.compose(P, Q, S);
          m.setMatrixAt(m.count, M);
          m.instanceColor.setXYZ(m.count, C.r, C.g, C.b);
          m.count++; placed++;
        }
      }
    }
    for (const k of kinds) for (const m of k.meshes) { m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true; }
  }
  return {
    update(camera) {
      const cx = Math.floor(camera.position.x / cell), cz = Math.floor(camera.position.z / cell);
      const key = cx + ',' + cz;
      if (key === lastKey) return;
      lastKey = key;
      rebuild(cx, cz);
    },
    facts: () => ({ placed, kinds: kinds.map(k => k.name) }),
  };
}
