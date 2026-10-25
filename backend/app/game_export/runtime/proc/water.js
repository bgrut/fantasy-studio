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
  // (2026-10-20) a storm sea: slate green, long wind-driven swells running
  // fast, white crests breaking along them, and a wide surf at the shore
  storm: { col: 0x1b3236, opacity: 0.94, rough: 0.2,  env: 0.42, ripple: 0.75, scale: 0.16, weed: 0, speed: 2.6, surf: 1.5 },
  // (2026-10-22) a drowned city's flood: a hand deep over the old paving, clear and dark,
  // the sky in it; every metre of it was "shallows", and the shallows' foam turned it milk
  flood: { col: 0x163c3c, opacity: 0.58, rough: 0.04, env: 0.95, ripple: 0.14, scale: 0.5, weed: 0, speed: 0.6 },
};

/** the kind of water a world's words ask for */
export function waterKind(words, frozen) {
  if (/\b(sunken|drowned|flooded|submerged|half-sunk) (?:city|town|ruins?|kingdom|empire|capital)\b|\batlant(?:is|ean)\b/.test(words || '')) return 'flood';
  if (/swamp|marsh|bog|bayou|fen|mire|everglade/.test(words || '')) return 'swamp';
  if (frozen) return 'ice';
  if (/\b(storm\w*|gales?|tempest\w*|hurricanes?|squalls?|typhoons?)\b/.test(words || '')) return 'storm';
  // (2026-10-22) a surfing beach and the tropics are clear blue sea, not the dark of a lake
  if (/\b(surf\w*|tropical|hawai\w*|caribbean|lagoons?|atolls?|bahamas|maldives|tahiti|fiji|polynesia\w*|bali)\b/.test(words || '')) return 'sea';
  return 'lake';
}

// ── SHORES (2026-10-17) ─────────────────────────────────────────────────────
// The surface was a flat sheet cut by a coarse ground, so every shore was the
// saw-tooth where the two meshes crossed, sharp water against dry sand. Given
// the depth under it (baked once from the ground: metres of water, 0..2, in a
// byte texture over the play area), the water thins to nothing as the bed
// rises, turns the sand's colour in the shallows, and wears a soft broken
// line of foam a hand's depth out from the edge. Outside the baked square it
// is simply deep.
export function shoreDepth(hAt, level, cx, cz, size, res = 384) {
  const d = new Uint8Array(res * res * 4);
  for (let j = 0; j < res; j++) for (let i = 0; i < res; i++) {
    const x = cx + ((i + 0.5) / res - 0.5) * size, z = cz + ((j + 0.5) / res - 0.5) * size;
    const v = Math.max(0, Math.min(255, Math.round((level - hAt(x, z)) / 2 * 255)));
    const k = (j * res + i) * 4; d[k] = v; d[k + 3] = 255;
  }
  const t = new THREE.DataTexture(d, res, res, THREE.RGBAFormat);
  t.magFilter = t.minFilter = THREE.LinearFilter; t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  t.needsUpdate = true;
  return { tex: t, cx, cz, size };
}

export function waterMaterial(kind = 'lake', clock = { value: 0 }, shore = null) {
  const L = LOOKS[kind] || LOOKS.lake;
  const m = new THREE.MeshStandardMaterial({
    color: L.col, transparent: true, opacity: L.opacity, roughness: L.rough, metalness: 0,
    side: THREE.DoubleSide, depthWrite: false, envMapIntensity: L.env,
  });
  m.userData.noAutoTex = true;
  m.userData.waterKind = kind;
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uTime = clock;
    if (shore) {
      sh.uniforms.uShore = { value: shore.tex };
      sh.uniforms.uShoreO = { value: new THREE.Vector2(shore.cx, shore.cz) };
      sh.uniforms.uShoreS = { value: shore.size };
    }
    sh.vertexShader = 'varying vec3 vWPos;\n' + sh.vertexShader.replace('#include <worldpos_vertex>',
      '#include <worldpos_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = `uniform float uTime; varying vec3 vWPos;${shore ? ' uniform sampler2D uShore; uniform vec2 uShoreO; uniform float uShoreS;' : ''}
float wh(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float wn(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(wh(i), wh(i + vec2(1.0, 0.0)), u.x), mix(wh(i + vec2(0.0, 1.0)), wh(i + vec2(1.0, 1.0)), u.x), u.y); }
float wfbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 4; i++){ s += a * wn(p); p = p * 2.07 + vec2(3.1, 1.7); a *= 0.5; } return s; }
float wave(vec2 p){
  return wfbm(p * ${L.scale.toFixed(3)} + vec2(uTime * ${(0.06 * (L.speed || 1)).toFixed(3)}, uTime * ${(0.035 * (L.speed || 1)).toFixed(3)}))
       + 0.5 * wfbm(p * ${(L.scale * 3.1).toFixed(3)} - vec2(uTime * ${(0.09 * (L.speed || 1)).toFixed(3)}, -uTime * ${(0.05 * (L.speed || 1)).toFixed(3)}));
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
  ${kind === 'storm' ? `{
    // whitecaps: the swell's crests break white in streaks laid along the
    // wind, and the spray thins off them
    vec2 sp = vWPos.xz;
    float cr = wave(sp);
    float streak = wn(vec2(sp.x * 0.3 + sp.y * 0.1, sp.y * 1.4 - sp.x * 0.35) + vec2(uTime * 0.35, -uTime * 0.2));
    float cap = smoothstep(1.08, 1.24, cr + 0.3 * streak) * (0.6 + 0.4 * wn(sp * 3.1 + uTime * 0.6));
    diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.84, 0.88, 0.88), cap * 0.85);
    diffuseColor.a = max(diffuseColor.a, cap);
    roughnessFactor = mix(roughnessFactor, 0.8, cap);
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
  }` : ''}
  ${shore ? `{
    vec2 suv = (vWPos.xz - uShoreO) / uShoreS + 0.5;
    float dep = (suv.x > 0.0 && suv.x < 1.0 && suv.y > 0.0 && suv.y < 1.0) ? texture2D(uShore, suv).r * 2.0 : 2.0;
    float br = wn(vWPos.xz * 1.7 + vec2(uTime * 0.11, -uTime * 0.07));
    ${kind === 'flood' ? `
    // a flood is one clear depth: tinted, darker where it deepens, no foam
    diffuseColor.rgb *= mix(1.15, 0.8, smoothstep(0.0, 1.2, dep));
    diffuseColor.a *= smoothstep(0.0, 0.12, dep);` : kind === 'ice' ? `
    // ice thins to a clear rim at its edge, frosted white where it meets the bank
    diffuseColor.rgb = mix(vec3(0.84, 0.9, 0.95), diffuseColor.rgb, smoothstep(0.0, 0.35, dep));
    diffuseColor.a *= smoothstep(0.0, 0.08, dep);` : kind === 'swamp' ? `
    // (2026-10-25) still black water: no surf breaks on a bayou's bank. The shallows go to mud and
    // duckweed, the edge darkens into the bank, and there is no foam to read as a beach
    diffuseColor.rgb = mix(vec3(0.07, 0.08, 0.04), diffuseColor.rgb, smoothstep(0.0, 0.8, dep));
    diffuseColor.a *= smoothstep(0.0, 0.2, dep);` : `
    // the shallows take the bed's colour, the edge goes clear, and foam lies
    // in a broken line just off the bank, breathing with the ripples
    diffuseColor.rgb = mix(vec3(0.24, 0.27, 0.2), diffuseColor.rgb, smoothstep(0.0, 1.1, dep));
    float edgeA = smoothstep(0.0, 0.35, dep);
    float foam = smoothstep(0.0, 0.05, dep) * (1.0 - smoothstep(0.08 * ${(L.surf || 1).toFixed(2)}, (0.26 + 0.08 * br) * ${(L.surf || 1).toFixed(2)}, dep)) * smoothstep(0.3, 0.7, br * 0.6 + wn(vWPos.xz * 6.0 - uTime * 0.2) * 0.6);
    diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.82, 0.86, 0.86), foam * 0.75);
    diffuseColor.a = max(diffuseColor.a * edgeA, foam * 0.7);
    roughnessFactor = mix(roughnessFactor, 0.7, foam);`}
  }` : ''}`);
  };
  if (shore) m.userData.shore = shore;
  m.customProgramCacheKey = () => 'water-' + kind + (shore ? '-shore' : '');
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
    // (2026-10-21) the judge: "the mist is a flat grey gradient". A flat sheet cut the rising
    // ground in a straight line, a hard edge across every slope. Each sheet is a mesh now,
    // laid over the ground under it, so the mist lies in the hollows and rolls over the rises
    const sh = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE, 56, 56).rotateX(-Math.PI / 2), m);
    sh.renderOrder = 3;
    sh.name = 'groundMist';
    scene.add(sh);
    sheets.push({ sh, t, y: 0.35 + k * 0.45, vx: 0.004 + k * 0.002, vz: 0.002 - k * 0.0015 });
  }
  let lastX = NaN, lastZ = NaN;
  function update(cam) {
    const base = hAt(cam.position.x, cam.position.z);
    const sx0 = Math.round(cam.position.x / 10) * 10, sz0 = Math.round(cam.position.z / 10) * 10;
    if (sx0 !== lastX || sz0 !== lastZ) {
      // re-laid over the ground when the field moves on (every ten metres)
      lastX = sx0; lastZ = sz0;
      const ref = hAt(sx0, sz0);
      for (const q of sheets) {
        const pa = q.sh.geometry.attributes.position;
        for (let i = 0; i < pa.count; i++) pa.setY(i, hAt(sx0 + pa.getX(i), sz0 + pa.getZ(i)) - ref);
        pa.needsUpdate = true; q.sh.geometry.computeBoundingSphere();
        q.ref = ref;
      }
    }
    for (const q of sheets) {
      // the sheet follows the camera, snapped so its pattern stays put in the world
      const sx = sx0, sz = sz0;
      q.sh.position.set(sx, (q.ref ?? base) + q.y, sz);
      q.t.offset.set(clock.value * q.vx + sx / SIZE * q.t.repeat.x, clock.value * q.vz - sz / SIZE * q.t.repeat.y);
      const above = cam.position.y - (base + q.y);
      // thick seen from just above, thin seen from high up or from inside
      const k = Math.max(0, Math.min(1, above / 1.2)) * Math.max(0, Math.min(1, (14 - above) / 10));
      q.sh.material.opacity = density * k * 0.4;
    }
  }
  return { update, sheets: sheets.length };
}
