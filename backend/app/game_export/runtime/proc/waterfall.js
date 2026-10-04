// ── THE WATERFALL (2026-10-03) ──────────────────────────────────────────────
// "An explorer hacking through a dense jungle to find a lost temple by a
// waterfall" built the jungle and the temple, and no waterfall: nothing in
// the engine could draw one. A waterfall is a place, so it is built as one:
//
//   cliff   a curved wall of rock, ledged and fractured, wet and darker where
//           the fall runs down it, mossed on its ledges in a green world
//   fall    a sheet of water from the lip to the pool, streaks accelerating
//           down it (water falls; it does not scroll at one speed), torn at
//           its edges, brightest where it is thinnest
//   pool    a plunge pool in the world's own water (proc/water.js), white with
//           foam where the fall lands and spreading rings of it
//   spray   a cloud of drifting droplets and a mist that rises off the pool
//
// Placed beside the goal, on the far side from the spawn, so the walk ends
// with the fall in view. Procedural, no assets.
import * as THREE from 'three';
import { waterMaterial } from './water.js';

export function createWaterfall({ scene, at, facing, hAt, clock, green = true, height = 14 }) {
  const H = height, W = 4.2, R = 11;
  const [ax, az] = at;
  const base = hAt(ax, az);
  const grp = new THREE.Group();
  grp.position.set(ax, base, az);
  grp.rotation.y = Math.atan2(facing[0], facing[1]);      // the fall faces back along `facing`
  grp.name = 'waterfall';
  scene.add(grp);

  // ── the cliff: the edge of a plateau, a horseshoe bowl cut into it ───────
  // The first cut was an arc of rock standing on its own, and it read as a
  // painted flat on a stage. A fall pours off the edge of high ground: the
  // plateau rises behind the pool and falls away behind and to the sides
  // into the land around it, mossed on top, wet and dark down the walls,
  // ledged where the rock breaks.
  const EXT = R + 26;                                    // how far the plateau reaches
  const plateauH = (x, z) => {
    const d = Math.hypot(x, z);
    const behind = Math.min(1, Math.max(0, (-z + R * 0.25) / (R * 0.6)));      // the high ground is behind the pool
    const wall = Math.min(1, Math.max(0, (d - (R - 0.6)) / 2.4));               // the bowl's walls
    const fall = 1 - Math.min(1, Math.max(0, (d - (R + 10)) / 16));             // the plateau slopes down to the land
    const ww = wall * wall * (3 - 2 * wall), bb = behind * behind * (3 - 2 * behind), ff = fall * fall * (3 - 2 * fall);
    let h = H * ww * bb * ff;
    // ledges on the walls, lumps on the top
    if (h > 0.5 && ww < 0.99) h += Math.sin(h * 1.9 + Math.atan2(x, -z) * 3) * 0.45;
    h += (Math.sin(x * 0.31 + z * 0.17) * Math.cos(z * 0.27 - x * 0.11)) * 0.9 * ww * bb * ff;
    return h;
  };
  {
    const NG = 96, S = EXT * 2, pos = [], col = [], idx = [];
    const rock = new THREE.Color(0x7a7266), wet = new THREE.Color(0x3a3833), moss = new THREE.Color(0x4f6e2c), turf = new THREE.Color(0x3f6a24);
    const c = new THREE.Color();
    for (let i = 0; i <= NG; i++) for (let j = 0; j <= NG; j++) {
      const x = (j / NG - 0.5) * S, z = (i / NG - 0.5) * S;
      pos.push(x, plateauH(x, z) - 0.05, z);
    }
    for (let i = 0; i < NG; i++) for (let j = 0; j < NG; j++) {
      const a = i * (NG + 1) + j, b = a + NG + 1;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    const na = g.attributes.normal, pa = g.attributes.position;
    for (let v = 0; v < pa.count; v++) {
      const x = pa.getX(v), y = pa.getY(v), z = pa.getZ(v), up = na.getY(v);
      const nearFall = Math.exp(-((Math.atan2(x, -z) / 0.25) ** 2)) * (Math.hypot(x, z) < R + 3 ? 1 : 0);
      c.copy(rock).multiplyScalar(0.8 + 0.3 * Math.sin(y * 2.3 + x * 0.4));
      c.lerp(wet, Math.min(1, nearFall * 0.85 + (1 - up) * 0.25));
      if (green) {
        if (up > 0.8) c.lerp(turf, Math.min(1, (up - 0.8) * 5));                 // turf on the flats
        else if (up > 0.45 && Math.sin(y * 1.9) > 0.4) c.lerp(moss, 0.5);       // moss on the ledges
      }
      col.push(c.r, c.g, c.b);
    }
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    // where the plateau is no higher than the land, it is not drawn at all
    const keep = [];
    for (let t = 0; t < idx.length; t += 3) {
      if (pa.getY(idx[t]) > 0.02 || pa.getY(idx[t + 1]) > 0.02 || pa.getY(idx[t + 2]) > 0.02) keep.push(idx[t], idx[t + 1], idx[t + 2]);
    }
    g.setIndex(keep);
    // rock detail: the ground's own rock photo, wrapped round the bowl on the
    // walls and laid flat on the top, so the cliff is stone and not cloth
    const uv = new Float32Array(pa.count * 2);
    for (let v = 0; v < pa.count; v++) {
      const x = pa.getX(v), y = pa.getY(v), z = pa.getZ(v);
      if (na.getY(v) > 0.7) { uv[v * 2] = x / 6; uv[v * 2 + 1] = z / 6; }
      else { uv[v * 2] = Math.atan2(x, -z) * Math.hypot(x, z) / 6; uv[v * 2 + 1] = y / 6; }
    }
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    const tl = new THREE.TextureLoader();
    const rmap = tl.load('textures/cliff.jpg'), rnrm = tl.load('textures/cliff_n.jpg');
    rmap.colorSpace = THREE.SRGBColorSpace;
    for (const t of [rmap, rnrm]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; }
    const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, map: rmap, normalMap: rnrm,
                                               normalScale: new THREE.Vector2(1.2, 1.2) });
    m.userData.noAutoTex = true;
    const cliff = new THREE.Mesh(g, m);
    cliff.castShadow = true; cliff.receiveShadow = true;
    cliff.name = 'waterfallCliff';
    grp.add(cliff);
  }

  // ── the fall ─────────────────────────────────────────────────────────────
  const fallMat = new THREE.ShaderMaterial({
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, { uTime: { value: 0 } }]),
    transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: true,
    vertexShader: `
      #include <common>
      #include <fog_pars_vertex>
      varying vec2 vUv;
      void main(){ vUv = uv; vec4 mvPosition = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mvPosition;
        #include <fog_vertex>
      }`,
    fragmentShader: `
      #include <common>
      #include <fog_pars_fragment>
      uniform float uTime; varying vec2 vUv;
      float h1(float x){ return fract(sin(x * 127.1) * 43758.5453); }
      float n1(float x){ float i = floor(x), f = fract(x); return mix(h1(i), h1(i + 1.0), f * f * (3.0 - 2.0 * f)); }
      float hh(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float nn(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(mix(hh(i), hh(i + vec2(1, 0)), u.x), mix(hh(i + vec2(0, 1)), hh(i + vec2(1, 1)), u.x), u.y); }
      void main(){
        float drop = 1.0 - vUv.y;                     // 0 at the lip, 1 at the pool
        // falling bodies accelerate: the streaks stretch as they fall
        float s = sqrt(drop) * 6.0 - uTime * 1.6;
        float x = vUv.x * 22.0;
        float streak = nn(vec2(x, s * 3.0)) * 0.6 + nn(vec2(x * 2.3, s * 7.0)) * 0.4;
        // the sheet tears at its edges and thins as it falls
        float edge = smoothstep(0.0, 0.18 + 0.1 * n1(vUv.y * 9.0 + uTime), vUv.x) * smoothstep(0.0, 0.18 + 0.1 * n1(vUv.y * 7.0 - uTime), 1.0 - vUv.x);
        float a = edge * (0.55 + 0.45 * streak) * (0.85 - 0.25 * drop);
        vec3 col = mix(vec3(0.62, 0.72, 0.74), vec3(1.05, 1.1, 1.12), smoothstep(0.45, 0.85, streak));
        gl_FragColor = vec4(col, a);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
        #include <fog_fragment>
      }`,
  });
  fallMat.userData.noAutoTex = true;
  {
    // the sheet leaves the lip forward, then drops: a slight arc
    const g = new THREE.PlaneGeometry(W, H, 1, 24);
    const pa = g.attributes.position;
    for (let i = 0; i < pa.count; i++) {
      const y = pa.getY(i) + H / 2;                     // 0 .. H
      const t = 1 - y / H;                              // 0 at the lip
      pa.setY(i, y);
      pa.setZ(i, -(R + 1.6) + Math.sqrt(t) * 2.8);              // off the lip, clear of the wall below
      pa.setX(i, pa.getX(i) * (1 + t * 0.35));          // it spreads as it falls
    }
    g.computeVertexNormals();
    const fall = new THREE.Mesh(g, fallMat);
    fall.renderOrder = 4;
    fall.name = 'waterfallSheet';
    grp.add(fall);
  }

  // ── the pool ─────────────────────────────────────────────────────────────
  const poolR = R - 1.2;
  const pool = new THREE.Mesh(new THREE.CircleGeometry(poolR, 48), waterMaterial('lake', clock));
  pool.rotation.x = -Math.PI / 2;
  pool.position.set(0, 0.12, -R * 0.35);
  pool.renderOrder = 2;
  pool.name = 'waterfallPool';
  grp.add(pool);
  // foam where the fall lands, spreading out in rings
  const foamTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    for (let k = 0; k < 60; k++) {
      const x = Math.random() * 128, y = Math.random() * 128, r = 4 + Math.random() * 14;
      const gr = g.createRadialGradient(x, y, 0, x, y, r);
      gr.addColorStop(0, 'rgba(255,255,255,0.5)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const foams = [];
  for (let k = 0; k < 5; k++) {
    const m = new THREE.MeshBasicMaterial({ map: foamTex, transparent: true, depthWrite: false, opacity: 0, color: 0xf2f6f6 });
    m.userData.noAutoTex = true;
    const f = new THREE.Mesh(new THREE.CircleGeometry(1, 32), m);
    f.rotation.x = -Math.PI / 2;
    f.position.set(0, 0.16 + k * 0.004, -R + 1.4);
    f.renderOrder = 3;
    grp.add(f);
    foams.push({ f, p: k / 5 });
  }
  // spray and mist: sprites that rise off the landing and drift
  // spray is round: the foam sheet's blobs run to the canvas edge, and on a
  // sprite that edge showed as a square
  const sprayTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(255,255,255,0.55)'); gr.addColorStop(0.6, 'rgba(255,255,255,0.18)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const sprays = [];
  for (let k = 0; k < 26; k++) {
    const m = new THREE.SpriteMaterial({ map: sprayTex, transparent: true, depthWrite: false, opacity: 0, color: 0xe8eef0 });
    m.userData.noAutoTex = true;
    const sp = new THREE.Sprite(m);
    sp.renderOrder = 5;
    grp.add(sp);
    sprays.push({ sp, p: Math.random(), jx: Math.random() - 0.5, jz: Math.random() - 0.5 });
  }

  function update(dt) {
    fallMat.uniforms.uTime.value = clock.value;
    for (const q of foams) {
      q.p = (q.p + dt * 0.18) % 1;
      const s = 1.2 + q.p * 5.5;
      q.f.scale.set(s, s, 1);
      q.f.material.opacity = 0.75 * (1 - q.p);
    }
    for (const q of sprays) {
      q.p += dt * 0.25;
      if (q.p >= 1) { q.p -= 1; q.jx = Math.random() - 0.5; q.jz = Math.random() - 0.5; }
      const p = q.p;
      q.sp.position.set(q.jx * (2 + p * 5), 0.4 + p * 5.5, -R + 1.4 + q.jz * (2 + p * 4) + p * 2);
      const s = 1.5 + p * 5;
      q.sp.scale.set(s, s, 1);
      q.sp.material.opacity = Math.sin(Math.PI * p) * 0.32;
    }
  }
  return { update, group: grp, facts: () => ({ height: H, width: W }) };
}
