// GRASS THAT GROWS LIKE THE FOREST (2026-10-02)
// ------------------------------------------------
// The meadow was 38,000 three-blade tufts scattered once over a 70 m square:
// sparse up close, gone past the square, and nothing like the forest standing
// in it. This is the forest's approach brought down to the ground: every
// blade is drawn on the GPU from one shared shape, in a field that travels
// with the camera, so there is always grass under you and to the edge of
// the near view, and none is spent behind you.
//
// How a blade finds its place: each instance owns a fixed spot in an L x L
// tile; the tile repeats across the world and the vertex shader picks the
// copy nearest the camera. A blade therefore stays put in the world while the
// camera walks (no swimming), and the field never ends. Two such fields run
// at once: a fine one close in (well over a hundred blades a square metre)
// and a coarse one to the far edge; each thins blade by blade with distance,
// so there is no ring where one hands over to the other.
//
// What the ground says goes: a height map lays every blade on the terrain,
// and a mask (density, dryness, height) keeps grass off paths, water,
// floors, rock and sand, and lets it grow in clumps and bare patches.
//
// Lighting is the forest's: both faces of a blade share one normal, bent
// toward the sky the way a lawn reads, and the sun behind a blade lights it
// from within. Wind runs through it in gusts; it parts around the hero.
import * as THREE from 'three';

function bladeGeometry(SEG = 4) {
  // x across the blade (-0.5..0.5), y along it (0 root .. 1 tip); the
  // shader turns, bends and sizes it. Colour darkens toward the root.
  const pos = [], col = [], idx = [];
  for (let s = 0; s < SEG; s++) {
    const t = s / SEG;
    pos.push(-0.5, t, 0, 0.5, t, 0);
    const c = 0.38 + 0.5 * Math.pow(t, 0.8);
    col.push(c, c, c, c, c, c);
  }
  pos.push(0, 1, 0); col.push(0.9, 0.9, 0.9);
  for (let s = 0; s < SEG - 1; s++) {
    const a = s * 2;
    idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  }
  const a = (SEG - 1) * 2;
  idx.push(a, a + 1, a + 2);
  const g = new THREE.InstancedBufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(new Array(pos.length).fill(0).map((_, i) => (i % 3 === 1 ? 1 : 0)), 3));
  g.setIndex(idx);
  return g;
}

function mulberry(a) {
  return () => {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

// o: { scene, seed, hAt(x,z), maskAt(x,z) -> [density 0..1, dryness 0..1, height 0..1],
//      center:[x,z], size, colA, colB, colDry (THREE.Color), height (m), quality,
//      wind: {value} (a clock), sunDir: THREE.Vector3, sunCol: THREE.Color }
export function plantGrass(o) {
  const size = o.size, half = size / 2;
  const cx = (o.center || [0, 0])[0], cz = (o.center || [0, 0])[1];
  // the ground's height, as a texture the blades read (half floats filter)
  const HN = 512;
  const hd = new Uint16Array(HN * HN);
  for (let j = 0; j < HN; j++) for (let i = 0; i < HN; i++) {
    const x = cx - half + (i + 0.5) / HN * size, z = cz - half + (j + 0.5) / HN * size;
    hd[j * HN + i] = THREE.DataUtils.toHalfFloat(o.hAt(x, z));
  }
  const hTex = new THREE.DataTexture(hd, HN, HN, THREE.RedFormat, THREE.HalfFloatType);
  hTex.magFilter = hTex.minFilter = THREE.LinearFilter;
  hTex.wrapS = hTex.wrapT = THREE.ClampToEdgeWrapping;
  hTex.needsUpdate = true;
  // where it grows: density, dryness, height
  const MN = 256;
  const md = new Uint8Array(MN * MN * 4);
  let covered = 0;
  for (let j = 0; j < MN; j++) for (let i = 0; i < MN; i++) {
    const x = cx - half + (i + 0.5) / MN * size, z = cz - half + (j + 0.5) / MN * size;
    const [d, dry, h] = o.maskAt(x, z);
    const k = (j * MN + i) * 4;
    md[k] = Math.round(Math.max(0, Math.min(1, d)) * 255);
    md[k + 1] = Math.round(Math.max(0, Math.min(1, dry)) * 255);
    md[k + 2] = Math.round(Math.max(0, Math.min(1, h)) * 255);
    md[k + 3] = 255;
    covered += d;
  }
  const mTex = new THREE.DataTexture(md, MN, MN, THREE.RGBAFormat, THREE.UnsignedByteType);
  mTex.magFilter = mTex.minFilter = THREE.LinearFilter;
  mTex.needsUpdate = true;

  const q = o.quality || 'balanced';
  const layers = [
    // the fine field: right around you
    { L: 30, R: 15, n: { ultra: 140000, high: 100000, balanced: 75000, performance: 32000 }[q] ?? 75000, w: 0.065, thin: 0.4 },
    // the coarse field: out to the edge of the near view
    { L: 104, R: 48, n: { ultra: 190000, high: 140000, balanced: 100000, performance: 42000 }[q] ?? 100000, w: 0.1, thin: 0.55 },
  ];
  const camU = { value: new THREE.Vector3() };
  const heroU = { value: new THREE.Vector3(1e6, -1e6, 1e6) };
  const group = new THREE.Group();
  group.name = 'grassField';
  const geo = bladeGeometry(4);
  const rnd = mulberry((o.seed || 1) >>> 0);
  let blades = 0;
  for (const ly of layers) {
    if (!ly.n) continue;
    const g = geo.clone();
    const off = new Float32Array(ly.n * 4);
    for (let i = 0; i < ly.n; i++) {
      off[i * 4] = rnd(); off[i * 4 + 1] = rnd(); off[i * 4 + 2] = rnd(); off[i * 4 + 3] = rnd();
    }
    g.setAttribute('aOff', new THREE.InstancedBufferAttribute(off, 4));
    g.instanceCount = ly.n;
    blades += ly.n;
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1.0, metalness: 0,
                                                side: THREE.DoubleSide, envMapIntensity: 0.45 });
    mat.name = 'grassBlade';
    mat.userData.noAutoTex = true;
    const U = {
      uCamG: camU, uHero: heroU, uL: { value: ly.L }, uR: { value: ly.R }, uThin: { value: ly.thin },
      uTime: o.wind || { value: 0 }, uWindK: { value: o.windK ?? 0.35 },
      uH: { value: o.height || 0.42 }, uW: { value: ly.w },
      uHgt: { value: hTex }, uMask: { value: mTex },
      uMap: { value: new THREE.Vector4(cx - half, cz - half, size, 0) },
      uColA: { value: o.colA.clone() }, uColB: { value: o.colB.clone() }, uColDry: { value: o.colDry.clone() },
      uSunDir: { value: (o.sunDir || new THREE.Vector3(0.4, 0.8, 0.3)).clone().normalize() },
      uSunCol: { value: (o.sunCol || new THREE.Color(1, 1, 1)).clone() },
    };
    mat.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, U);
      sh.vertexShader = `attribute vec4 aOff;
        uniform vec3 uCamG; uniform vec3 uHero; uniform float uL; uniform float uR; uniform float uThin;
        uniform float uTime; uniform float uWindK; uniform float uH; uniform float uW;
        uniform sampler2D uHgt; uniform sampler2D uMask; uniform vec4 uMap;
        uniform vec3 uColA; uniform vec3 uColB; uniform vec3 uColDry;
        varying vec3 vGW; varying float vGT;
        ` + sh.vertexShader
        .replace('#include <color_vertex>', `#include <color_vertex>
          // the copy of this blade's spot nearest the camera
          vec2 gO = aOff.xy * uL;
          vec2 gW = uCamG.xz + mod(gO - uCamG.xz + 0.5 * uL, uL) - 0.5 * uL;
          vec2 gM = (gW - uMap.xy) / uMap.z;
          float gIn = step(0.0, gM.x) * step(gM.x, 1.0) * step(0.0, gM.y) * step(gM.y, 1.0);
          vec4 gK = texture2D(uMask, gM);
          float gD = length(gW - uCamG.xz);
          float gFar = clamp(gD / uR, 0.0, 1.0);
          float gR1 = fract(aOff.w * 7.713);
          float gR2 = fract(aOff.w * 13.37);
          // thinned blade by blade with distance, then gone at the edge
          float gKeep = gIn * step(aOff.z, gK.r) * step(smoothstep(uThin, 1.0, gFar), gR1);
          float gY = texture2D(uHgt, gM).r;
          float gA = fract(aOff.w * 91.7) * 6.2832;
          vec2 gDir = vec2(cos(gA), sin(gA));
          float gWind = sin(uTime * 1.6 + gW.x * 0.31 + gW.y * 0.23) * 0.6
                      + sin(uTime * 3.1 + gW.x * 1.3 - gW.y * 0.9) * 0.25 + 0.35;
          vec2 gLean = vec2(cos(gA * 2.3), sin(gA * 2.3)) * (0.10 + 0.32 * gR2)
                     + vec2(0.8, 0.45) * gWind * uWindK;
          // parted by the hero's legs
          vec2 gAway = gW - uHero.xz; float gHd = length(gAway);
          gLean += (gHd > 1e-3 ? gAway / gHd : vec2(0.0)) * 1.2
                 * (1.0 - smoothstep(0.3, 1.0, gHd)) * step(abs(uHero.y - gY), 2.5);
          float gH = uH * (0.55 + 0.9 * aOff.w) * (0.35 + 0.65 * gK.b) * gKeep;
          float gWid = uW * (0.75 + 0.5 * gR2) * (1.0 + gFar * 0.8);
          float gT = position.y;
          vec3 gSide = vec3(-gDir.y, 0.0, gDir.x);
          vec3 gP = vec3(gW.x, gY - 0.02, gW.y) + gSide * position.x * gWid * (1.0 - 0.85 * gT);
          float gLL = min(length(gLean), 1.1);
          gP.xz += gLean * gH * gT * gT;
          gP.y += gH * gT * (1.0 - 0.38 * gLL * gT);
          vec3 gTan = normalize(vec3(gLean.x * gH * 2.0 * gT, gH * (1.0 - 0.76 * gLL * gT) + 1e-4, gLean.y * gH * 2.0 * gT));
          vec3 gN = normalize(cross(gSide, gTan));
          if (gN.y < 0.0) gN = -gN;
          gN = normalize(mix(gN, vec3(0.0, 1.0, 0.0), 0.5));
          vec3 gTint = mix(uColA, uColB, fract(aOff.w * 5.71));
          gTint = mix(gTint, uColDry, gK.g * (0.35 + 0.65 * fract(aOff.w * 3.31)));
          #ifdef USE_COLOR
            vColor *= gTint;
          #endif
          vGW = gP; vGT = gT;`)
        .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = gN;')
        .replace('#include <begin_vertex>', 'vec3 transformed = gP;');
      sh.fragmentShader = `uniform vec3 uSunDir; uniform vec3 uSunCol;
        varying vec3 vGW; varying float vGT;
        ` + sh.fragmentShader
        .replace('#include <normal_fragment_begin>', `#include <normal_fragment_begin>
          normal = normalize(vNormal);          // both faces of a blade face the sky
          nonPerturbedNormal = normal;`)
        .replace('#include <opaque_fragment>', `{
            // the sun behind a blade lights it from within
            vec3 Vw = normalize(cameraPosition - vGW);
            float bl = pow(max(dot(-Vw, uSunDir), 0.0), 2.5) * (0.35 + 0.65 * vGT);
            outgoingLight += diffuseColor.rgb * uSunCol * bl * 0.4;
          }
          #include <opaque_fragment>`);
    };
    mat.customProgramCacheKey = () => 'grassField';
    const mesh = new THREE.Mesh(g, mat);
    mesh.frustumCulled = false;
    mesh.receiveShadow = true;
    mesh.castShadow = false;
    group.add(mesh);
  }
  o.scene.add(group);
  return {
    group, blades,
    coverage: covered / (MN * MN),
    update(camera, hero) {
      camU.value.copy(camera.position);
      if (hero) heroU.value.copy(hero);
    },
  };
}
