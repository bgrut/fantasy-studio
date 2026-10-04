// ── WATER THAT IS WATER (2026-10-03) ────────────────────────────────────────
// Every lake, swamp and island sea was one flat MeshStandardMaterial: a pale
// blue sheet with no ripple, no depth and a mirror finish that, at the
// grazing angle a third-person camera sees a lake from, reflected a bright
// sky as a white slab. The scene survey's swamp at dawn was a glaring white
// ribbon through a green lawn.
//
// The same material, told what kind of water it is:
//   ripples   two scrolling octaves of procedural normals, in world space, so
//             the surface breaks the sky's reflection into glints instead of
//             a slab; wind-driven, finer on a still pond than on a sea
//   depth     a body of water is dark: the colour is what the depth absorbs
//             (tea-brown in a swamp, deep green-blue in a lake), and the
//             reflection is held back on the still kinds so it never washes
//   swamp     duckweed and algae drift in mats on the surface, matte and
//             green, and the water between them is black tea
// Kinds: 'lake' (default), 'swamp', 'sea' (an island's clear sea keeps its
// shallows showing), 'ice' (a frozen lake: still, pale and only a little glossy). Read through onBeforeCompile so the cascades, fog and
// the scene's environment light all keep working.
import * as THREE from 'three';

const LOOKS = {
  lake:  { col: 0x123540, opacity: 0.9,  rough: 0.08, env: 0.55, ripple: 0.22, scale: 0.55, weed: 0 },
  swamp: { col: 0x1a1d10, opacity: 0.96, rough: 0.14, env: 0.32, ripple: 0.12, scale: 0.4,  weed: 1 },
  sea:   { col: 0x1f6f96, opacity: 0.74, rough: 0.1,  env: 0.8,  ripple: 0.3,  scale: 0.3,  weed: 0 },
  ice:   { col: 0x6f93a8, opacity: 1.0,  rough: 0.1,  env: 0.75, ripple: 0.0,  scale: 0.2,  weed: 0 },
};

/** the kind of water a world's words ask for */
export function waterKind(words, frozen) {
  if (/swamp|marsh|bog|bayou|fen|mire|everglade/.test(words || '')) return 'swamp';
  if (frozen) return 'ice';
  return 'lake';
}

export function waterMaterial(kind = 'lake', clock = { value: 0 }) {
  const L = LOOKS[kind] || LOOKS.lake;
  const m = new THREE.MeshStandardMaterial({
    color: L.col, transparent: true, opacity: L.opacity, roughness: L.rough, metalness: 0,
    side: THREE.DoubleSide, depthWrite: false, envMapIntensity: L.env,
  });
  m.userData.noAutoTex = true;
  m.userData.waterKind = kind;
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uTime = clock;
    sh.vertexShader = 'varying vec3 vWPos;\n' + sh.vertexShader.replace('#include <worldpos_vertex>',
      '#include <worldpos_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = `uniform float uTime; varying vec3 vWPos;
float wh(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float wn(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(wh(i), wh(i + vec2(1.0, 0.0)), u.x), mix(wh(i + vec2(0.0, 1.0)), wh(i + vec2(1.0, 1.0)), u.x), u.y); }
float wfbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 4; i++){ s += a * wn(p); p = p * 2.07 + vec2(3.1, 1.7); a *= 0.5; } return s; }
float wave(vec2 p){
  return wfbm(p * ${L.scale.toFixed(3)} + vec2(uTime * 0.06, uTime * 0.035))
       + 0.5 * wfbm(p * ${(L.scale * 3.1).toFixed(3)} - vec2(uTime * 0.09, -uTime * 0.05));
}
` + sh.fragmentShader
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
  {
    vec2 wp = vWPos.xz;
    float e = 0.12;
    float h0 = wave(wp), hx = wave(wp + vec2(e, 0.0)), hz = wave(wp + vec2(0.0, e));
    vec3 nW = normalize(vec3(-(hx - h0) / e * ${L.ripple.toFixed(3)}, 1.0, -(hz - h0) / e * ${L.ripple.toFixed(3)}));
    nW = normalize(mix(nW, vec3(0.0, 1.0, 0.0), weed));     // a weed mat lies still on the ripples
    normal = normalize((viewMatrix * vec4(nW, 0.0)).xyz);
    if (!gl_FrontFacing) normal = -normal;
  }`)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
  float weed = 0.0;
  ${L.weed ? `{
    // duckweed mats: drifting, broken at their edges, thicker toward the banks' still corners
    vec2 dp = vWPos.xz + vec2(uTime * 0.02, uTime * 0.012);
    float n = wfbm(dp * 0.11) * 0.75 + wfbm(dp * 0.9) * 0.35;
    weed = smoothstep(0.5, 0.6, n);
    diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.06, 0.09, 0.025) * (0.7 + 0.6 * wn(dp * 4.0)), weed);
    diffuseColor.a = mix(diffuseColor.a, 1.0, weed);
    roughnessFactor = mix(roughnessFactor, 0.85, weed);
  }` : ''}
  ${kind === 'ice' ? `{
    // ice: dark where it is clear and deep, frosted pale in drifts, and
    // crazed with white fracture lines (the edges of a cell pattern)
    vec2 ip = (vWPos.xz + vec2(wfbm(vWPos.xz * 0.07), wfbm(vWPos.xz * 0.07 + 5.2)) * 9.0) * 0.11;   // big, warped plates
    vec2 ii = floor(ip), ff = fract(ip); float d1 = 8.0, d2 = 8.0;
    for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++) {
      vec2 gg = vec2(float(x), float(y));
      vec2 oo = vec2(wh(ii + gg), wh(ii + gg + 7.7));
      float dd = length(gg + oo - ff);
      if (dd < d1) { d2 = d1; d1 = dd; } else if (dd < d2) d2 = dd;
    }
    // thin, and only some of the plate edges have cracked
    float crack = (1.0 - smoothstep(0.0, 0.012, d2 - d1)) * smoothstep(0.42, 0.6, wfbm(vWPos.xz * 0.045 + 3.3));
    float frost = smoothstep(0.45, 0.75, wfbm(vWPos.xz * 0.08));
    diffuseColor.rgb = mix(vec3(0.20, 0.33, 0.42), vec3(0.78, 0.86, 0.92), frost * 0.8);
    diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.86, 0.92, 0.97), crack * 0.6);
    roughnessFactor = mix(0.06, 0.55, max(frost, crack));
  }` : ''}`);
  };
  m.customProgramCacheKey = () => 'water-' + kind;
  return m;
}

// ── GROUND MIST (2026-10-03) ────────────────────────────────────────────────
// "A misty swamp at dawn" had no mist: distance fog greys the far trees, but
// mist is a thing that LIES on still water and low ground, waist-high, in
// banks that drift and part. A few soft horizontal sheets around the camera,
// stacked a little apart, each drawn from one shared tileable noise and
// scrolled at its own speed; they fade with the camera's height above them so
// they never become a ceiling, and fade up close so you walk into a thinning,
// not through a wall.
export function groundMist(scene, { hAt = () => 0, color = 0xcfd6d2, density = 0.5, clock = { value: 0 } } = {}) {
  const N = 256, c = document.createElement('canvas'); c.width = c.height = N;
  const g = c.getContext('2d'), im = g.createImageData(N, N);
  const P = 8, lat = new Float32Array(P * P);
  let s = 4242;
  for (let i = 0; i < P * P; i++) { s = (s * 1664525 + 1013904223) >>> 0; lat[i] = s / 4294967296; }
  const vn = (x, y, p) => {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const at = (a, b) => lat[((b % p + p) % p) * P + ((a % p + p) % p)];
    return at(xi, yi) * (1 - u) * (1 - v) + at(xi + 1, yi) * u * (1 - v) + at(xi, yi + 1) * (1 - u) * v + at(xi + 1, yi + 1) * u * v;
  };
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const u = x / N, v = y / N;
    const n = vn(u * 4, v * 4, 4) * 0.6 + vn(u * 8, v * 8, 8) * 0.4;
    const a = Math.max(0, Math.min(1, (n - 0.38) * 2.6));
    const k = (y * N + x) * 4;
    im.data[k] = im.data[k + 1] = im.data[k + 2] = 255; im.data[k + 3] = a * a * 255;
  }
  g.putImageData(im, 0, 0);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  const sheets = [];
  const SIZE = 140;
  for (let k = 0; k < 4; k++) {
    const t = tex.clone(); t.needsUpdate = true; t.repeat.set(2.2 + k * 0.4, 2.2 + k * 0.4);
    const m = new THREE.MeshBasicMaterial({ map: t, color, transparent: true, depthWrite: false, opacity: 0, fog: true, side: THREE.DoubleSide });
    m.userData.noAutoTex = true;
    const sh = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE), m);
    sh.rotation.x = -Math.PI / 2;
    sh.renderOrder = 3;
    sh.name = 'groundMist';
    scene.add(sh);
    sheets.push({ sh, t, y: 0.35 + k * 0.45, vx: 0.004 + k * 0.002, vz: 0.002 - k * 0.0015 });
  }
  function update(cam) {
    const base = hAt(cam.position.x, cam.position.z);
    for (const q of sheets) {
      // the sheet follows the camera, snapped so its pattern stays put in the world
      const sx = Math.round(cam.position.x / 10) * 10, sz = Math.round(cam.position.z / 10) * 10;
      q.sh.position.set(sx, base + q.y, sz);
      q.t.offset.set(clock.value * q.vx + sx / SIZE * q.t.repeat.x, clock.value * q.vz - sz / SIZE * q.t.repeat.y);
      const above = cam.position.y - (base + q.y);
      // thick seen from just above, thin seen from high up or from inside
      const k = Math.max(0, Math.min(1, above / 1.2)) * Math.max(0, Math.min(1, (14 - above) / 10));
      q.sh.material.opacity = density * k * 0.4;
    }
  }
  return { update, sheets: sheets.length };
}
