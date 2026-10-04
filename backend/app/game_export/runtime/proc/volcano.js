// ── THE VOLCANO (2026-10-03) ────────────────────────────────────────────────
// "Climb a smoking volcano and escape the lava flows" built a night of black
// alpine peaks: no cone, no lava, no smoke, and a static 'lava flow' prop
// standing on the grass. A volcano is the one place lit by its own ground, so
// this is a biome rather than a texture:
//
//   lava    the level cuts channels across the route (level.py); here the
//           lava runs IN them: a ribbon down each channel whose crust plates
//           drift with the flow, cooler and crustier at the banks, white-hot
//           in the cracks, bright enough to bloom. Four orange lights follow
//           the player along the nearest channels so the banks, the rocks
//           and the hero are lit by it.
//   cone    a stratovolcano past the goal: concave flanks cut by gullies,
//           ash on the shoulders, oxidised red at the rim, a crater that
//           glows, and lava streaks running down the side facing the player.
//           Its glow punches through the haze the rest of it sits in.
//   plume   an eruption column of soft puffs from the crater, lit orange from
//           below, rising, spreading downwind and fading into the ash deck.
//   air     embers rising around the player, ash drifting down.
//   sky     an ash sky: a heavy cloud deck over a haze the colour of the fog,
//           glowing orange low over the cone, the sun a dull red disc.
//
// Everything is procedural (no assets), deterministic from the seed, and
// reports what it built through facts() so the gate can hold it to account.
import * as THREE from 'three';

const NOISE_GLSL = `
float vh(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vn(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(vh(i), vh(i + vec2(1.0, 0.0)), u.x), mix(vh(i + vec2(0.0, 1.0)), vh(i + vec2(1.0, 1.0)), u.x), u.y); }
float vfbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++){ s += a * vn(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; } return s; }
`;

function mulberry(a) {
  return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}

function softTex(size, puff, seed) {
  const c = document.createElement('canvas'); c.width = c.height = size;
  const g = c.getContext('2d');
  const r = mulberry(seed);
  if (puff) {
    // a smoke puff: overlapping soft blobs, so no two edges are a circle
    for (let k = 0; k < 18; k++) {
      const x = size * (0.3 + r() * 0.4), y = size * (0.3 + r() * 0.4), rad = size * (0.16 + r() * 0.2);
      const gr = g.createRadialGradient(x, y, 0, x, y, rad);
      gr.addColorStop(0, 'rgba(255,255,255,0.32)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, size, size);
    }
  } else {
    const gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,0.55)');
    gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, size, size);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function createVolcano({ scene, lava, gsize, hAt, camera, sunDir, seed = 1 }) {
  const rnd = mulberry(seed * 31 + 7);
  const half = gsize / 2;
  const LEVEL = lava.level;
  const clock = { value: 0 };
  const facts = { channels: 0, ribbon_len: 0, lights: 0, cone: false, plume: 0, embers: 0, ash: 0, sky: false };

  // ── LAVA RIBBONS ────────────────────────────────────────────────────────
  const lavaMat = new THREE.ShaderMaterial({
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, { uTime: { value: 0 }, uW: { value: 3 } }]),
    fog: true,
    side: THREE.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 4,   // where a bank lies level with the lava, the bank wins
    vertexShader: `
      #include <common>
      #include <fog_pars_vertex>
      attribute float halfW;
      varying vec2 vUv; varying float vHW;
      void main(){
        vUv = uv; vHW = halfW;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        #include <fog_vertex>
      }`,
    fragmentShader: `
      #include <common>
      #include <fog_pars_fragment>
      uniform float uTime; varying vec2 vUv; varying float vHW;
      ${NOISE_GLSL}
      vec2 vor(vec2 p){ vec2 i = floor(p), f = fract(p); float d1 = 8.0, d2 = 8.0;
        for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++){
          vec2 g = vec2(float(x), float(y));
          vec2 o = vec2(vh(i + g), vh(i + g + 19.1));
          o = 0.5 + 0.45 * sin(uTime * 0.15 + 6.2831 * o);
          float d = length(g + o - f);
          if (d < d1){ d2 = d1; d1 = d; } else if (d < d2) d2 = d; }
        return vec2(d1, d2); }
      void main(){
        float across = vUv.x;
        // THE MIDDLE RUNS, THE BANKS DRAG, AND NOTHING SHEARS. A flow that is
        // faster mid-channel than at the banks smears any pattern into
        // stripes within a minute, so the crust is drawn twice, each copy
        // flowing for one period and then reset, crossfaded so a reset is
        // never seen (the flow-map technique)
        float speed = 0.5 * (1.0 - across * across * 0.8);
        float edgeCool = smoothstep(0.45, 1.0, abs(across));
        const float PER = 7.0;
        vec3 acc = vec3(0.0);
        for (int k = 0; k < 2; k++) {
          float ph = fract(uTime / PER + float(k) * 0.5);
          float wk = 1.0 - abs(2.0 * ph - 1.0);
          float cyc = floor(uTime / PER + float(k) * 0.5);
          vec2 p = vec2(across * vHW, vUv.y - ph * PER * speed) + vec2(cyc * 17.3, cyc * 31.7 + float(k) * 9.1);
          vec2 w = vec2(vfbm(p * 0.15), vfbm(p * 0.15 + 7.3));
          vec2 q = p + (w - 0.5) * 3.0;
          vec2 v = vor(q * 0.55);
          float crack = v.y - v.x;                               // 0 along a crack between plates
          float heat = vfbm(q * 0.3 + vec2(0.0, uTime * 0.05));
          float plate = smoothstep(0.02, 0.1 + 0.14 * (1.0 - edgeCool), crack);
          plate *= smoothstep(0.24, 0.5, heat * 0.85 + edgeCool * 0.6);   // the hottest runs carry no crust
          float T = (1.0 - plate) * (0.55 + 0.5 * heat);
          T *= 0.86 + 0.14 * sin(uTime * 1.8 + q.x * 0.7 + q.y * 0.5);
          vec3 crustC = vec3(0.032, 0.026, 0.024) * (0.7 + 0.6 * vn(q * 3.1));
          crustC += vec3(0.30, 0.05, 0.0) * pow(1.0 - plate, 2.0);  // plate rims still glow dull red
          vec3 hot = mix(vec3(0.45, 0.03, 0.0), vec3(2.3, 0.5, 0.04), smoothstep(0.2, 0.7, T));
          hot = mix(hot, vec3(4.2, 1.7, 0.4), smoothstep(0.86, 1.0, T));
          acc += mix(crustC, hot, smoothstep(0.1, 0.38, T)) * wk;
        }
        gl_FragColor = vec4(acc, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
        #include <fog_fragment>
      }`,
  });
  lavaMat.userData.noAutoTex = true;
  // the sample points along every channel, for the lights and the hazard
  const samples = [];
  const clipR = half * 0.95;
  for (const ch of lava.channels || []) {
    const W = ch.w, HW = W + 2.2;
    // resample the polyline every metre and a bit, inside the playfield only
    const pts = [];
    for (let k = 0; k < ch.pts.length - 1; k++) {
      const [ax, az] = ch.pts[k], [bx, bz] = ch.pts[k + 1];
      const L = Math.hypot(bx - ax, bz - az), n = Math.max(1, Math.ceil(L / 1.25));
      for (let s = 0; s < n; s++) {
        const t = s / n, x = ax + (bx - ax) * t, z = az + (bz - az) * t;
        if (Math.abs(x) < clipR && Math.abs(z) < clipR) pts.push([x, z]);
        else if (pts.length) { k = ch.pts.length; break; }   // left the field: this channel is done
      }
    }
    if (pts.length < 4) continue;
    // the level's line has a slight kink at each of its points; a ribbon
    // five metres wide folds over itself at a kink, so round them off
    for (let pass = 0; pass < 3; pass++) {
      const src = pts.map(q => q.slice());
      for (let i = 1; i < pts.length - 1; i++) {
        let sx = 0, sz = 0, n = 0;
        for (let d = -4; d <= 4; d++) {
          const q = src[Math.max(0, Math.min(src.length - 1, i + d))];
          sx += q[0]; sz += q[1]; n++;
        }
        pts[i][0] = sx / n; pts[i][1] = sz / n;
      }
    }
    const pos = [], uv = [], hw = [], idx = [];
    let along = 0;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
      let tx = b[0] - a[0], tz = b[1] - a[1]; const tl = Math.hypot(tx, tz) || 1; tx /= tl; tz /= tl;
      const nx = -tz, nz = tx;
      if (i > 0) along += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      for (const side of [-1, 0, 1]) {
        pos.push(pts[i][0] + nx * HW * side, LEVEL, pts[i][1] + nz * HW * side);
        uv.push(side * HW / W, along);
        hw.push(W);
      }
      samples.push([pts[i][0], pts[i][1], W]);
      if (i > 0) {
        const o = (i - 1) * 3, p2 = i * 3;
        idx.push(o, p2, o + 1, o + 1, p2, p2 + 1, o + 1, p2 + 1, o + 2, o + 2, p2 + 1, p2 + 2);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setAttribute('halfW', new THREE.Float32BufferAttribute(hw, 1));
    g.setIndex(idx);
    g.computeBoundingSphere();
    const m = new THREE.Mesh(g, lavaMat);
    m.name = 'lavaRibbon';
    scene.add(m);
    facts.channels++;
    facts.ribbon_len += Math.round(along);
  }

  // ── LAVA LIGHT: four lights walk the channels with the player ─────────────
  const lights = [];
  for (let k = 0; k < 4; k++) {
    const L = new THREE.PointLight(0xff8a3a, 0, 17, 1.6);
    L.castShadow = false;
    scene.add(L);
    lights.push({ L, base: 0, ph: rnd() * 6.28 });
  }
  facts.lights = lights.length;
  let lightT = 0;
  function placeLights(px, pz) {
    const near = samples.map(s => [s, (s[0] - px) ** 2 + (s[1] - pz) ** 2]).sort((a, b) => a[1] - b[1]);
    const used = [];
    for (const [s, d2] of near) {
      if (used.length >= lights.length || d2 > 60 * 60) break;
      if (used.some(u => (u[0] - s[0]) ** 2 + (u[1] - s[1]) ** 2 < 9 * 9)) continue;
      used.push(s);
    }
    lights.forEach((l, k) => {
      const s = used[k];
      if (!s) { l.base = 0; return; }
      l.L.position.set(s[0], LEVEL + 1.1, s[1]);
      l.base = 26 + s[2] * 7;
    });
  }

  // ── THE CONE ──────────────────────────────────────────────────────────────
  const cd = lava.cone_dir || [0, 1];
  const R = gsize * 0.72, H = gsize * 0.42;
  const D = half + R * 0.9;
  const cx = cd[0] * D, cz = cd[1] * D;
  const toPlayer = Math.atan2(-cd[1], -cd[0]);          // the flank that faces the playfield
  {
    // NOT A PARTY HAT. A real stratovolcano is lopsided: its base lobes out
    // where old flows ran, broad spurs of rock stand between the gullies, the
    // rim is ragged and breached on one side (the lava leaves through the
    // breach), and a parasitic cone sits on one shoulder.
    const RINGS = 110, SEG = 288, rc = R * 0.075, craterD = H * 0.12;
    const pos = [], col = [], glow = [], idx = [];
    const wave = (n0, n1, amp) => {                     // a periodic wobble around the cone
      const ks = [];
      for (let k = n0; k <= n1; k++) ks.push([k, rnd() * 6.28, amp / k]);
      return a => ks.reduce((s, [k, ph, am]) => s + am * Math.sin(k * a + ph), 0);
    };
    const lobe = wave(2, 7, 0.42), spur = wave(5, 11, 1.0), ragged = wave(3, 14, 1.0);
    const aBreach = toPlayer + (rnd() - 0.5) * 0.7;
    const aPara = toPlayer + (rnd() < 0.5 ? 1 : -1) * (0.9 + rnd() * 0.6);
    const vn2 = (x, z) => {                             // value noise for the rubble on the flanks
      const xi = Math.floor(x), zi = Math.floor(z), xf = x - xi, zf = z - zi;
      const h = (a, b) => { const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return s - Math.floor(s); };
      const u = xf * xf * (3 - 2 * xf), v = zf * zf * (3 - 2 * zf);
      return h(xi, zi) * (1 - u) * (1 - v) + h(xi + 1, zi) * u * (1 - v) + h(xi, zi + 1) * (1 - u) * v + h(xi + 1, zi + 1) * u * v;
    };
    const angd = (a, b) => Math.atan2(Math.sin(a - b), Math.cos(a - b));
    const streaks = [];
    for (let k = 0; k < 5; k++) streaks.push({ a: aBreach + (k === 0 ? 0 : (rnd() - 0.5) * 1.1), len: 0.3 + rnd() * 0.4,
                                               w: (k === 0 ? 0.02 : 0.011) + rnd() * 0.008, f: 5 + rnd() * 6, ph: rnd() * 6.28 });
    const basalt = new THREE.Color(0x17120f), ashC = new THREE.Color(0x5a4e46), rust = new THREE.Color(0x6a3018);
    const c = new THREE.Color();
    const heightAt = (r, a) => {
      const rim = H * (1 + 0.035 * ragged(a)) - H * 0.02 * Math.exp(-((angd(a, aBreach) / 0.2) ** 2));
      if (r < rc) return rim - craterD * (1 - (r / rc) ** 2);
      const re = r / (1 + lobe(a) * 0.35);              // the base lobes out along old flows
      const t = Math.min(1, Math.max(0, (re - rc) / (R - rc)));
      const prof = (Math.exp(-2.8 * t) - Math.exp(-2.8)) / (1 - Math.exp(-2.8));
      const mid = Math.sin(Math.PI * Math.min(1, t * 1.25));
      const sp = Math.abs(Math.sin(a * 8 + spur(a) * 1.4 + t * 2.2));
      const g = Math.abs(Math.sin(a * 31 + Math.sin(t * 7 + a * 3) * 1.6));
      const rub = (vn2(Math.cos(a) * r / R * 26, Math.sin(a) * r / R * 26) - 0.5) * H * 0.03 * mid;
      const para = H * 0.2 * Math.exp(-(((Math.cos(a) * r - Math.cos(aPara) * R * 0.42) ** 2
                                        + (Math.sin(a) * r - Math.sin(aPara) * R * 0.42) ** 2) / (R * 0.1) ** 2));
      return rim * prof + sp * H * 0.045 * mid - g * H * 0.014 * mid + rub + para;
    };
    for (let i = 0; i <= RINGS; i++) {
      const rr = (i / RINGS) ** 1.35 * R;               // denser near the summit
      for (let j = 0; j <= SEG; j++) {
        const a = (j / SEG) * Math.PI * 2;
        const y = heightAt(rr, a);
        pos.push(Math.cos(a) * rr, y, Math.sin(a) * rr);
        const t = rr / R;
        // colour: basalt low, ash on the shoulders, rust at the rim
        c.copy(basalt).lerp(ashC, Math.min(1, Math.max(0, (0.8 - t) * 1.5)) * 0.75);
        c.lerp(rust, Math.exp(-(((rr - rc * 1.5) / (R * 0.07)) ** 2)) * 0.75);
        c.multiplyScalar(0.75 + 0.5 * vn2(Math.cos(a) * t * 40, Math.sin(a) * t * 40));
        col.push(c.r, c.g, c.b);
        // the crater floor glows; its walls and the breach a little
        let gl = rr < rc * 0.8 ? 0.55 : rr < rc ? 0.12 : 0;
        for (const s of streaks) {
          const tt = (rr - rc) / R;
          if (tt < 0 || tt > s.len) continue;
          const sa = s.a + 0.1 * Math.sin(tt * s.f + s.ph) + tt * 0.2;
          const across = Math.abs(angd(a, sa)) * rr / R;
          const width = s.w * (1 + tt * 1.4);
          const fade = Math.min(1, tt * 25) * Math.pow(1 - tt / s.len, 0.6);
          gl = Math.max(gl, Math.exp(-((across / width) ** 2)) * fade * 0.9);
        }
        glow.push(gl);
      }
    }
    for (let i = 0; i < RINGS; i++) for (let j = 0; j < SEG; j++) {
      const a = i * (SEG + 1) + j, b = a + SEG + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.setAttribute('glow', new THREE.Float32BufferAttribute(glow, 1));
    g.setIndex(idx);
    g.computeVertexNormals();
    const m = new THREE.MeshLambertMaterial({ vertexColors: true });
    m.userData.noAutoTex = true;
    m.onBeforeCompile = (sh) => {
      sh.uniforms.uTime = clock;
      sh.vertexShader = 'attribute float glow;\nvarying float vGlow;\n' + sh.vertexShader
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvGlow = glow;');
      sh.fragmentShader = 'uniform float uTime;\nvarying float vGlow;\n' + sh.fragmentShader
        .replace('#include <fog_fragment>', `#include <fog_fragment>
          {
            float gk = vGlow * (0.86 + 0.14 * sin(uTime * 1.7 + vGlow * 3.0));
            vec3 gc = mix(vec3(2.4, 0.55, 0.07), vec3(4.6, 1.9, 0.45), clamp(vGlow - 0.7, 0.0, 1.0));
            float keep = 1.0;
            #ifdef USE_FOG
              keep = 1.0 - 0.6 * fogFactor;    // the glow carries through the haze the rock sits in
            #endif
            gl_FragColor.rgb += gc * gk * keep;
          }`);
    };
    const cone = new THREE.Mesh(g, m);
    cone.position.set(cx, -2.5, cz);
    cone.name = 'volcanoCone';
    cone.receiveShadow = false; cone.castShadow = false;
    scene.add(cone);
    facts.cone = true;
    facts.cone_h = Math.round(H);
  }

  // ── THE PLUME ─────────────────────────────────────────────────────────────
  const puffTex = softTex(128, true, seed + 3);
  const puffs = [];
  const wind = new THREE.Vector2(-cd[1], cd[0]).multiplyScalar(rnd() < 0.5 ? 1 : -1);
  const NP = 80;
  for (let k = 0; k < NP; k++) {
    const mat = new THREE.SpriteMaterial({ map: puffTex, transparent: true, depthWrite: false, fog: true,
                                           color: 0x2a2523, opacity: 0 });
    mat.userData.noAutoTex = true;
    const sp = new THREE.Sprite(mat);
    sp.renderOrder = 2;
    scene.add(sp);
    puffs.push({ sp, p: k / NP, jx: (rnd() - 0.5), jz: (rnd() - 0.5), rot: rnd() * 6.28, spin: (rnd() - 0.5) * 0.1 });
  }
  facts.plume = NP;
  const _pc = new THREE.Color(), _base = new THREE.Color(0.85, 0.32, 0.13), _top = new THREE.Color(0x2a2523);
  function stepPlume(dt) {
    for (const q of puffs) {
      q.p += dt / 70;                                  // seventy seconds from crater to ash deck
      if (q.p >= 1) { q.p -= 1; q.jx = rnd() - 0.5; q.jz = rnd() - 0.5; }
      const p = q.p;
      const rise = H * (1.02 + Math.pow(p, 0.8) * 1.3);
      const drift = Math.pow(p, 1.8) * H * 1.1;
      const spread = H * (0.05 + p * p * 0.6);                 // a column, then an anvil
      q.sp.position.set(cx + wind.x * drift + q.jx * spread, rise, cz + wind.y * drift + q.jz * spread);
      const s = H * (0.09 + p * 0.95);
      q.sp.scale.set(s, s, 1);
      q.rot += q.spin * dt; q.sp.material.rotation = q.rot;
      q.sp.material.opacity = Math.pow(Math.sin(Math.PI * Math.min(1, p * 1.1)), 0.45) * 0.95;
      _pc.copy(_base).lerp(_top, Math.min(1, p * 9));
      q.sp.material.color.copy(_pc);
    }
  }

  // ── EMBERS AND ASH around the camera ──────────────────────────────────────
  const BOX = 36, BH = 16;
  function cloud(n, size, color, additive, sizeAtt) {
    const pos = new Float32Array(n * 3), vel = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (rnd() - 0.5) * BOX; pos[i * 3 + 1] = rnd() * BH; pos[i * 3 + 2] = (rnd() - 0.5) * BOX;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const m = new THREE.PointsMaterial({ size, map: softTex(32, false, seed), color, transparent: true,
      depthWrite: false, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending, sizeAttenuation: sizeAtt });
    m.userData.noAutoTex = true;
    const pts = new THREE.Points(g, m);
    pts.frustumCulled = false;
    scene.add(pts);
    return { pts, pos, vel, n, origin: new THREE.Vector3() };
  }
  const embers = cloud(420, 0.11, new THREE.Color(4.0, 1.3, 0.25), true, true);
  const ash = cloud(600, 0.05, new THREE.Color(0.16, 0.15, 0.14), false, true);
  for (let i = 0; i < embers.n; i++) { embers.vel[i * 3] = rnd() * 6.28; embers.vel[i * 3 + 1] = 0.5 + rnd() * 1.2; }
  for (let i = 0; i < ash.n; i++) { ash.vel[i * 3] = rnd() * 6.28; ash.vel[i * 3 + 1] = 0.35 + rnd() * 0.45; }
  facts.embers = embers.n; facts.ash = ash.n;
  function wrap(c, i, cam) {
    const o = i * 3;
    for (const ax of [0, 2]) {
      const d = c.pos[o + ax] - (ax === 0 ? cam.x : cam.z);
      if (d > BOX / 2) c.pos[o + ax] -= BOX; else if (d < -BOX / 2) c.pos[o + ax] += BOX;
    }
  }
  function stepAir(dt, cam) {
    const t = clock.value;
    for (let i = 0; i < embers.n; i++) {
      const o = i * 3, ph = embers.vel[o];
      embers.pos[o] += Math.sin(t * 1.3 + ph) * dt * 0.6 + wind.x * dt * 0.4;
      embers.pos[o + 2] += Math.cos(t * 1.1 + ph * 1.7) * dt * 0.6 + wind.y * dt * 0.4;
      embers.pos[o + 1] += embers.vel[o + 1] * dt;
      if (embers.pos[o + 1] > cam.y + BH * 0.6) {
        embers.pos[o + 1] = cam.y - 3 - rnd() * 3;
        embers.pos[o] = cam.x + (rnd() - 0.5) * BOX; embers.pos[o + 2] = cam.z + (rnd() - 0.5) * BOX;
      }
      wrap(embers, i, cam);
    }
    for (let i = 0; i < ash.n; i++) {
      const o = i * 3, ph = ash.vel[o];
      ash.pos[o] += (Math.sin(t * 0.7 + ph) * 0.4 + wind.x * 0.9) * dt;
      ash.pos[o + 2] += (Math.cos(t * 0.6 + ph) * 0.4 + wind.y * 0.9) * dt;
      ash.pos[o + 1] -= ash.vel[o + 1] * dt;
      if (ash.pos[o + 1] < cam.y - 4) {
        ash.pos[o + 1] = cam.y + BH * 0.7;
        ash.pos[o] = cam.x + (rnd() - 0.5) * BOX; ash.pos[o + 2] = cam.z + (rnd() - 0.5) * BOX;
      }
      wrap(ash, i, cam);
    }
    embers.pts.geometry.attributes.position.needsUpdate = true;
    ash.pts.geometry.attributes.position.needsUpdate = true;
    embers.pts.material.opacity = 0.75 + 0.25 * Math.sin(t * 9.0);
  }

  // ── THE ASH SKY ───────────────────────────────────────────────────────────
  const fogC = scene.fog ? scene.fog.color.clone() : new THREE.Color(0x3a2a24);
  const skyR = Math.min(camera.far * 0.92, 4000);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { uTime: clock, uFog: { value: fogC }, uCone: { value: new THREE.Vector2(cd[0], cd[1]) },
                uSun: { value: (sunDir || new THREE.Vector3(0.3, 0.2, 0.3)).clone().normalize() } },
    vertexShader: `varying vec3 vDir;
      void main(){ vDir = position; vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_Position = p; }`,
    fragmentShader: `uniform float uTime; uniform vec3 uFog; uniform vec2 uCone; uniform vec3 uSun; varying vec3 vDir;
      ${NOISE_GLSL}
      void main(){
        vec3 d = normalize(vDir);
        float e = clamp(d.y, 0.0, 1.0);
        vec3 col = mix(uFog, uFog * 0.3, pow(e, 0.5));
        vec2 cp = d.xz / max(d.y + 0.14, 0.06) * 1.25 + vec2(uTime * 0.004, uTime * 0.0025);
        float c1 = vfbm(cp), c2 = vfbm(cp * 2.7 + 3.1);
        float deck = smoothstep(0.4, 0.68, c1 * 0.72 + c2 * 0.36) * smoothstep(0.0, 0.16, d.y);
        vec2 hz = normalize(d.xz + 1e-4);
        float toward = pow(max(dot(hz, uCone), 0.0), 3.0);
        vec3 glowC = vec3(0.95, 0.30, 0.06);
        col += glowC * toward * exp(-e * 7.0) * 0.6;
        vec3 cloudC = uFog * (0.3 + 0.35 * c2) + glowC * toward * 0.45 * exp(-e * 2.6);   // billows: lit crowns, dark bellies
        col = mix(col, cloudC, deck * 0.88);
        float sd = max(dot(d, normalize(uSun)), 0.0);
        col += vec3(1.0, 0.42, 0.18) * (pow(sd, 700.0) * 1.4 + pow(sd, 10.0) * 0.1) * (1.0 - deck * 0.75);
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  skyMat.userData.noAutoTex = true;
  const skyMesh = new THREE.Mesh(new THREE.SphereGeometry(skyR, 48, 24), skyMat);
  skyMesh.renderOrder = -10;
  skyMesh.frustumCulled = false;
  skyMesh.name = 'ashSky';
  scene.add(skyMesh);
  facts.sky = true;

  // ── what the game asks ────────────────────────────────────────────────────
  /** metres from the lava's edge (negative inside a channel), from the samples */
  function edgeDist(x, z) {
    let best = 1e9;
    for (const s of samples) {
      const d = Math.hypot(s[0] - x, s[1] - z) - s[2];
      if (d < best) best = d;
    }
    return best;
  }
  /** is a body standing at (x, z) on ground the lava covers */
  function inLava(x, z) {
    return hAt(x, z) < LEVEL - 0.05;          // only a channel lies under the lava (level.py clamps the rest above it)
  }
  function update(dt, cam, playerPos) {
    clock.value += dt;
    lavaMat.uniforms.uTime.value = clock.value;
    skyMesh.position.copy(cam.position);
    if ((lightT -= dt) <= 0 && playerPos) { lightT = 0.4; placeLights(playerPos.x, playerPos.z); }
    for (const l of lights) {
      l.L.intensity = l.base * (0.85 + 0.15 * Math.sin(clock.value * 7.3 + l.ph) * Math.sin(clock.value * 3.1 + l.ph * 2));
    }
    stepPlume(dt);
    stepAir(dt, cam.position);
  }
  return { update, inLava, edgeDist, level: LEVEL, facts: () => Object.assign({}, facts) };
}
