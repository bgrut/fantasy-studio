// THE PLACES A SENTENCE NAMES (2026-10-20).
// "He must find three brass lantern lenses scattered among the tide pools,
// the boathouse and the ruined chapel" built none of the three: the lenses
// floated over bare turf. A sentence that names a place gets that place,
// built beside the route in the order the sentence gives them, and when the
// things to find are scattered among them, each one lies at its place.
//
// The kit: a stone cottage (croft, bothy, cabin, hut), a boathouse with its
// slipway and boat, a roofless chapel (kirk, abbey, church) with its
// graves, tide pools on the shore, a ring of standing stones, a well.
// Everything is in metres with photographed surfaces at their real scale,
// sat on a footing so a slope never shows daylight under it, and solid.
//
// o: { THREE, scene, hAt(x,z), waterY|null, path:[[x,z]...], goal:[x,z]|null,
//      spawn:[x,z], prompt, goalLabel, seed, night, HDT(name,rx,ry),
//      HDN(name,rx,ry), bound, collider(x,y,z,hx,hy,hz,yaw) }
// returns { places:[{kind,x,z,yaw,item:[x,z,y?]}], tick(t,dt), holes, spots }

const KINDS = [
  ['cottage', /\b(?:stone |whitewashed |thatched |crofter'?s? )?(cottages?|crofts?|bothy|bothies|cabins?|huts?|shacks?)\b/],
  ['boathouse', /\b(boat ?houses?|boat ?sheds?|slipways?)\b/],
  ['chapel', /\b(?:ruined |old |roofless |abandoned )?(chapels?|kirks?|abbeys?|priory|priories|churche?s?)\b/],
  ['tidepools', /\b(tide ?pools?|rock ?pools?|rockpools?)\b/],
  ['stones', /\b(standing stones?|stone circles?|menhirs?|dolmens?)\b/],
  ['well', /\b(wishing wells?|old wells?|stone wells?|village wells?)\b/],
  // (2026-10-20) a jungle, lost or ancient temple: the stepped monument (main.js.tpl's
  // buildAncientTemple); an East Asian temple is a pagoda and is left to its own builder
  ['temple', /\b(?:jungle |lost |ancient |ruined |forgotten |stone |overgrown |maya\w* |aztec |inca |khmer )?(temples?|ziggurats?)\b/],
  // (2026-10-21) "in an old castle" built no castle: the facade kit's keep, battlements and all
  ['castle', /\b(?:old |ruined |ancient |medieval |stone |dark |haunted )?(castles?|fortress(?:es)?|citadels?|strongholds?)\b/],
];
const EAST_ASIA = /japan|chinese|china|asian|zen|torii|pagoda|cherry|sakura|kyoto|shinto|buddhis|tibet|himalaya|monaster|korea|bamboo/;

function rng(seed) {
  let a = (seed >>> 0) || 1;
  return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/** which places the sentence names, in its order; a place it starts FROM is the start */
export function namedPlaces(prompt, goalLabel) {
  const p = String(prompt || '').toLowerCase(), gl = String(goalLabel || '').toLowerCase(), out = [];
  for (const [kind, re] of KINDS) {
    const m = re.exec(p);
    if (!m) continue;
    if (gl && m[1] && gl.includes(m[1].replace(/s$/, ''))) continue;          // the goal builds its own
    if (kind === 'temple' && EAST_ASIA.test(p)) continue;
    if (kind === 'castle' && /\b(joust\w*|tournament|siege|storm(?:s|ing)? the castle|inside the castle|castle walls|courtyard)\b/.test(p)) continue;   // the castle sites build their own
    const before = p.slice(Math.max(0, m.index - 24), m.index);
    out.push({ kind, at: m.index, start: /\bfrom (?:his|her|their|the|a|an|its|my|your)\s+(?:\w+\s+)?$/.test(before) });
  }
  return out.sort((a, b) => a.at - b.at);
}

export function buildPlaces(o) {
  const { THREE, scene, hAt, HDT, HDN } = o;
  const named = namedPlaces(o.prompt, o.goalLabel);
  if (!named.length || !o.path || o.path.length < 2) return null;
  const r = rng((o.seed || 1) * 7 + 4049);
  const WY = (o.waterY === null || o.waterY === undefined) ? null : o.waterY;
  const ticks = [], holes = [], spots = [], places = [];

  // ── materials, all in metre UVs (texture repeat = 1 / tile size) ──────────
  const MS = (p) => { const m = new THREE.MeshStandardMaterial(p); m.userData.noAutoTex = true; return m; };
  const stone = MS({ map: HDT('stone', 0.5, 0.5), normalMap: HDN('stone', 0.5, 0.5), normalScale: new THREE.Vector2(1.3, 1.3), color: 0xbdb8ae, roughness: 0.95 });
  const oldStone = MS({ map: HDT('stone', 0.5, 0.5), normalMap: HDN('stone', 0.5, 0.5), normalScale: new THREE.Vector2(1.5, 1.5), color: 0x97928a, roughness: 0.97 });
  const lime = MS({ map: HDT('plaster', 0.4, 0.4), normalMap: HDN('plaster', 0.4, 0.4), color: 0xe9e6dc, roughness: 0.92 });
  const slate = MS({ map: HDT('roof', 0.6, 0.6), normalMap: HDN('roof', 0.6, 0.6), color: 0x8c9096, roughness: 0.8 });
  const rust = MS({ map: HDT('roof', 0.6, 0.6), normalMap: HDN('roof', 0.6, 0.6), color: 0xa0705a, roughness: 0.85 });
  const wood = MS({ map: HDT('planks', 0.7, 0.7), normalMap: HDN('planks', 0.7, 0.7), color: 0x9a8268, roughness: 0.9 });
  const darkWood = MS({ map: HDT('planks', 0.7, 0.7), normalMap: HDN('planks', 0.7, 0.7), color: 0x5e4a3a, roughness: 0.9 });
  const paint = MS({ map: HDT('planks', 0.7, 0.7), normalMap: HDN('planks', 0.7, 0.7), color: [0x3d6b5a, 0x2f4f78, 0x8a2f2a][Math.floor(r() * 3)], roughness: 0.7 });
  const moss = MS({ color: 0x3c4d24, roughness: 1 });
  const iron = MS({ color: 0x2b2b2e, roughness: 0.6, metalness: 0.6 });
  const glass = o.night
    ? MS({ color: 0x2a1c0c, emissive: 0xffb15c, emissiveIntensity: 1.6, roughness: 0.4 })
    : MS({ color: 0x182024, roughness: 0.08, metalness: 0.1, envMapIntensity: 1.4 });

  // a box whose UVs are metres on every face, so a 6 m wall is not one stretched tile
  const box = (w, h, d) => {
    const g = new THREE.BoxGeometry(w, h, d), uv = g.attributes.uv;
    const span = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
    for (let f = 0; f < 6; f++) for (let k = 0; k < 4; k++) { const i = f * 4 + k; uv.setXY(i, uv.getX(i) * span[f][0], uv.getY(i) * span[f][1]); }
    return g;
  };
  const rockGeo = (rad, seed) => {
    const g = new THREE.IcosahedronGeometry(rad, 1), pa = g.attributes.position, rr = rng(seed * 31 + 7);
    const n = []; for (let i = 0; i < 12; i++) n.push([rr() * 2 - 1, rr() * 2 - 1, rr() * 2 - 1]);
    for (let i = 0; i < pa.count; i++) {
      const x = pa.getX(i), y = pa.getY(i), z = pa.getZ(i), l = Math.hypot(x, y, z) || 1;
      let d = 0; for (const v of n) d += Math.max(0, (x * v[0] + y * v[1] + z * v[2]) / l) * 0.09;
      const k = 1 + d - 0.12 + (rr() - 0.5) * 0.08; pa.setXYZ(i, x * k, y * k * 0.72, z * k);
    }
    g.computeVertexNormals();
    const uv = []; for (let i = 0; i < pa.count; i++) uv.push(pa.getX(i) + pa.getZ(i) * 0.5, pa.getY(i));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    return g;
  };
  const add = (G, g, m, x, y, z, ry = 0) => { const s = new THREE.Mesh(g, m); s.position.set(x, y, z); s.rotation.y = ry; s.castShadow = s.receiveShadow = true; G.add(s); return s; };

  // world <-> a place's frame: local +z is its front
  const frame = (G) => { const c = Math.cos(G.rotation.y), s = Math.sin(G.rotation.y);
    return (lx, lz) => [G.position.x + lx * c + lz * s, G.position.z - lx * s + lz * c]; };
  const solid = (G, lx, ly, lz, hx, hy, hz) => { const [x, z] = frame(G)(lx, lz); o.collider(x, G.position.y + ly, z, hx, hy, hz, G.rotation.y); };
  const hole = (G, hx, hz) => holes.push({ x: G.position.x, z: G.position.z, c: Math.cos(G.rotation.y), s: Math.sin(G.rotation.y), hx, hz });
  const footing = (G, w, d) => {                       // the lowest corner sets the floor; a footing goes down to the highest
    let lo = Infinity, hi = -Infinity; const f = frame(G);
    for (const [a, b] of [[-w / 2, -d / 2], [w / 2, -d / 2], [-w / 2, d / 2], [w / 2, d / 2], [0, 0]]) { const [x, z] = f(a, b); const h = hAt(x, z); lo = Math.min(lo, h); hi = Math.max(hi, h); }
    G.position.y = Math.min(hi, lo + 0.6) + 0.05;
    const dep = G.position.y - lo + 0.4;
    add(G, box(w + 0.3, dep, d + 0.3), oldStone, 0, -dep / 2 + 0.12, 0);
  };
  const smoke = (G, x, y, z) => {
    const cv = document.createElement('canvas'); cv.width = cv.height = 64; const c = cv.getContext('2d');
    const gr = c.createRadialGradient(32, 32, 2, 32, 32, 30); gr.addColorStop(0, 'rgba(200,200,200,0.55)'); gr.addColorStop(1, 'rgba(200,200,200,0)');
    c.fillStyle = gr; c.fillRect(0, 0, 64, 64);
    const tex = new THREE.CanvasTexture(cv), puffs = [];
    for (let i = 0; i < 7; i++) { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, color: 0xb8b6b2 }));
      G.add(sp); puffs.push({ sp, t: i / 7 }); }
    ticks.push((t, dt) => { for (const q of puffs) { q.t += dt / 7; if (q.t > 1) q.t -= 1; const h = q.t * 7;
      q.sp.position.set(x + h * 0.55 + Math.sin(q.t * 7 + t * 0.5) * 0.2, y + h, z + h * 0.15);
      q.sp.scale.setScalar(0.6 + q.t * 3.2); q.sp.material.opacity = Math.min(1, q.t * 5) * (1 - q.t) * 0.5; } });
  };

  // ── THE KIT ───────────────────────────────────────────────────────────────
  // a gable roof over L (x) by D (z): two pitched slabs, ridge, and the
  // triangular gable walls; returns the ridge height
  const gableRoof = (G, L, D, wallH, rise, roofM, wallM, over = 0.35) => {
    const half = D / 2 + over, slope = Math.hypot(half, rise), ang = Math.atan2(rise, half);
    for (const s of [-1, 1]) { const sl = add(G, box(L + over * 2, 0.16, slope), roofM, 0, wallH + rise / 2 + 0.08, s * half / 2); sl.rotation.x = s * ang; }
    const rg = add(G, new THREE.CylinderGeometry(0.09, 0.09, L + over * 2, 8), roofM, 0, wallH + rise + 0.12, 0); rg.rotation.z = Math.PI / 2;
    const tri = new THREE.Shape(); tri.moveTo(-D / 2, 0); tri.lineTo(D / 2, 0); tri.lineTo(0, rise); tri.closePath();
    for (const s of [-1, 1]) { const g = new THREE.ExtrudeGeometry(tri, { depth: 0.5, bevelEnabled: false }); g.translate(0, 0, -0.25);
      const m = add(G, g, wallM, s * (L / 2 - 0.25), wallH, 0); m.rotation.y = Math.PI / 2; }
    return wallH + rise;
  };
  const windowAt = (G, x, y, z, ry, w = 0.8, h = 0.9) => {
    const W = new THREE.Group(); W.position.set(x, y, z); W.rotation.y = ry; G.add(W);
    add(W, box(w, h, 0.06), glass, 0, 0, 0.02);
    for (const [bx, by, bw, bh] of [[0, h / 2 + 0.05, w + 0.2, 0.1], [0, -h / 2 - 0.06, w + 0.26, 0.12], [-w / 2 - 0.05, 0, 0.1, h + 0.1], [w / 2 + 0.05, 0, 0.1, h + 0.1], [0, 0, 0.05, h], [0, 0, w, 0.05]])
      add(W, box(bw, bh, 0.12), paint, bx, by, 0.06);
  };

  const KIT = {
    cottage(G) {
      const L = 6.6, D = 4.4, H = 2.4, T = 0.55;
      footing(G, L + 0.4, D + 0.4);
      const wallM = r() < 0.5 ? lime : stone;
      add(G, box(L, H, T), wallM, 0, H / 2, -D / 2 + T / 2);
      add(G, box(T, H, D), wallM, -L / 2 + T / 2, H / 2, 0); add(G, box(T, H, D), wallM, L / 2 - T / 2, H / 2, 0);
      // the front: a door between two windows
      add(G, box(L / 2 - 0.55, H, T), wallM, -L / 4 - 0.27, H / 2, D / 2 - T / 2); add(G, box(L / 2 - 0.55, H, T), wallM, L / 4 + 0.27, H / 2, D / 2 - T / 2);
      add(G, box(1.1, H - 1.95, T), wallM, 0, 1.95 + (H - 1.95) / 2, D / 2 - T / 2);
      add(G, box(0.98, 1.92, 0.08), paint, 0, 0.96, D / 2 - T + 0.1);
      add(G, box(1.4, 0.16, 0.5), oldStone, 0, 0.06, D / 2 + 0.25);               // the step
      add(G, new THREE.SphereGeometry(0.04, 8, 6), iron, 0.32, 1.0, D / 2 - T + 0.16);
      for (const x of [-L / 4 - 0.3, L / 4 + 0.3]) windowAt(G, x, 1.35, D / 2 + 0.01, 0);
      windowAt(G, 0, 1.35, -D / 2 - 0.01, Math.PI);
      const top = gableRoof(G, L, D, H, 1.9, slate, wallM);
      // the chimney on the west gable, smoking
      add(G, box(0.9, 1.5, 0.75), stone, -L / 2 + 0.45, top + 0.25, 0);
      for (const dx of [-0.18, 0.18]) add(G, new THREE.CylinderGeometry(0.1, 0.12, 0.35, 10), MS({ color: 0x9a5a3e, roughness: 0.8 }), -L / 2 + 0.45 + dx, top + 1.17, 0);
      smoke(G, -L / 2 + 0.45, top + 1.4, 0);
      if (o.night) { const lt = new THREE.PointLight(0xffb066, 3.2, 9, 1.8); lt.position.set(0, 1.4, D / 2 + 0.9); G.add(lt); }
      // a water butt, a stack of cut peat, and a run of drystone dyke
      add(G, new THREE.CylinderGeometry(0.34, 0.3, 0.85, 14), darkWood, L / 2 + 0.55, 0.42, D / 2 - 0.4);
      for (let i = 0; i < 14; i++) add(G, box(0.32, 0.12, 0.2), MS({ color: 0x2c2118, roughness: 1 }), -L / 2 - 0.7 + (i % 4) * 0.02, 0.07 + Math.floor(i / 4) * 0.13, -1 + (i % 4) * 0.25, r() * 0.3);
      for (let i = 0; i < 18; i++) { const x = -L / 2 - 2 + i * 0.55, m = add(G, rockGeo(0.32 + r() * 0.12, i + 3), oldStone, x, 0.25 + (i % 2) * 0.18, D / 2 + 3.2); m.rotation.set(r(), r() * 6, r()); }
      solid(G, 0, H / 2, 0, L / 2, H / 2 + 1, D / 2);
      hole(G, L / 2 + 0.8, D / 2 + 1.2);
      return [0, D / 2 + 1.4];                                                       // the item lies on the step
    },
    boathouse(G) {
      const L = 7.2, W = 4.6, H = 2.7;
      footing(G, L, W);
      // board walls on three sides; the +x end stands open to the water
      for (const z of [-W / 2, W / 2]) add(G, box(L, H, 0.14), wood, 0, H / 2, z);
      add(G, box(0.14, H, W), wood, -L / 2, H / 2, 0);
      for (let i = 0; i < 6; i++) for (const z of [-W / 2 - 0.08, W / 2 + 0.08]) add(G, box(0.12, H, 0.06), darkWood, -L / 2 + 0.1 + i * (L - 0.2) / 5, H / 2, z);   // battens
      gableRoof(G, L, W, H, 1.5, rust, wood, 0.4);
      add(G, box(L - 0.3, 0.06, W - 0.3), darkWood, 0, 0.05, 0);                    // the floor
      // the slipway, running down from the open end into the sea
      const SL = 7, drop = 1.6, ang = Math.atan2(drop, SL);
      const sw = add(G, box(SL, 0.14, 2.4), darkWood, L / 2 + SL / 2 - 0.1, -drop / 2, 0); sw.rotation.z = -ang;
      for (let i = 0; i < 7; i++) add(G, new THREE.CylinderGeometry(0.1, 0.12, 2.4, 8), darkWood, L / 2 + i * 1.05, -i * drop / 7 - 0.9, 1.25);
      // a clinker rowing boat on its trolley, oars, creels, a coil of rope, buoys
      const hull = new THREE.SphereGeometry(1, 20, 10, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2); hull.scale(2.1, 0.55, 0.75);
      add(G, hull, paint, -0.2, 0.68, 0.2);                                       // the lower half of a sphere: a bowl, open to the sky
      add(G, box(4.0, 0.06, 1.3), darkWood, -0.2, 0.7, 0.2);
      for (const s of [-1, 1]) add(G, box(2.8, 0.05, 0.08), wood, -0.2, 0.74, 0.2 + s * 0.45).rotation.y = s * 0.1;
      for (let i = 0; i < 3; i++) { const c = add(G, new THREE.CylinderGeometry(0.32, 0.32, 0.6, 12, 1, true, 0, Math.PI), MS({ color: 0x6a5b48, wireframe: true }), -L / 2 + 1 + i * 0.75, 0.32, -W / 2 + 0.6);
        c.rotation.z = Math.PI / 2; }
      add(G, new THREE.TorusGeometry(0.32, 0.06, 8, 20), MS({ color: 0xb59a6a, roughness: 1 }), L / 2 - 1.2, 0.12, -W / 2 + 0.5).rotation.x = Math.PI / 2;
      for (let i = 0; i < 3; i++) add(G, new THREE.SphereGeometry(0.22, 14, 10), MS({ color: i % 2 ? 0xf2efe6 : 0xe0592a, roughness: 0.5 }), -L / 2 + 0.4, 1.7 - i * 0.42, W / 2 - 0.25);
      for (const z of [-W / 2, W / 2]) solid(G, 0, H / 2, z, L / 2, H / 2, 0.12);
      solid(G, -L / 2, H / 2, 0, 0.12, H / 2, W / 2);
      hole(G, L / 2 + 0.5, W / 2 + 0.6);
      return [1.8, 0.3];                                                             // the item lies on the floor by the boat
    },
    chapel(G) {
      const L = 9.4, W = 5.4, H = 3.8, T = 0.7, rise = 3.0;
      footing(G, L + 0.4, W + 0.4);
      // a long wall with a jagged broken top and two pointed windows through it
      const arch = (path, cx, y0, w, h) => { path.moveTo(cx - w / 2, y0); path.lineTo(cx - w / 2, y0 + h - w / 2);
        path.quadraticCurveTo(cx - w / 2, y0 + h, cx, y0 + h + w * 0.1); path.quadraticCurveTo(cx + w / 2, y0 + h, cx + w / 2, y0 + h - w / 2); path.lineTo(cx + w / 2, y0); path.closePath(); };
      const longWall = (seed) => { const rr = rng(seed), sh = new THREE.Shape(); sh.moveTo(-L / 2, 0); sh.lineTo(L / 2, 0);
        let x = L / 2; sh.lineTo(x, H * (0.55 + rr() * 0.3));
        while (x > -L / 2) { x = Math.max(-L / 2, x - 0.5 - rr() * 0.9); sh.lineTo(x, H * (0.62 + rr() * 0.38) - (Math.abs(x) < 1.6 ? rr() * 1.4 : 0)); }
        sh.closePath();
        for (const cx of [-L / 4, L / 4]) { const p = new THREE.Path(); arch(p, cx, 1.1, 0.9, 1.6); sh.holes.push(p); }
        const g = new THREE.ExtrudeGeometry(sh, { depth: T, bevelEnabled: false }); g.translate(0, 0, -T / 2); return g; };
      add(G, longWall(11), oldStone, 0, 0, -W / 2 + T / 2); add(G, longWall(23), oldStone, 0, 0, W / 2 - T / 2);
      // the east gable, whole, with its tall window; the west, broken, with the door
      const gable = (broken) => { const sh = new THREE.Shape(); sh.moveTo(-W / 2, 0); sh.lineTo(W / 2, 0); sh.lineTo(W / 2, H);
        if (broken) { sh.lineTo(W / 4, H + rise * 0.45); sh.lineTo(0.2, H + rise * 0.2); sh.lineTo(-0.6, H + rise * 0.62); sh.lineTo(-W / 2, H + 0.2); }
        else { sh.lineTo(0.35, H + rise); sh.lineTo(0.35, H + rise + 0.9); sh.lineTo(-0.35, H + rise + 0.9); sh.lineTo(-0.35, H + rise); sh.lineTo(-W / 2, H); }
        sh.closePath(); const p = new THREE.Path(); if (broken) arch(p, 0, 0, 1.3, 2.3); else arch(p, 0, 1.6, 1.2, 2.8); sh.holes.push(p);
        const g = new THREE.ExtrudeGeometry(sh, { depth: T, bevelEnabled: false }); g.translate(0, 0, -T / 2); return g; };
      add(G, gable(false), oldStone, L / 2 - T / 2, 0, 0, Math.PI / 2);
      add(G, gable(true), oldStone, -L / 2 + T / 2, 0, 0, Math.PI / 2);
      // the bell-cote's empty arch on the east gable, rubble, moss on the wall heads
      for (let i = 0; i < 26; i++) { const a = r() * 6.28, d = 1 + r() * 3.5; const m = add(G, box(0.3 + r() * 0.4, 0.18 + r() * 0.2, 0.25 + r() * 0.3), oldStone,
        Math.cos(a) * d * 1.3, 0.1, Math.sin(a) * d * 0.5 + (r() < 0.5 ? -W / 2 - 0.6 : W / 2 + 0.6) * (r() < 0.5 ? 1 : 0)); m.rotation.set(r() * 0.4, r() * 6, r() * 0.4); }
      for (let i = 0; i < 12; i++) { const x = (r() - 0.5) * L * 0.9, z = (r() < 0.5 ? -1 : 1) * (W / 2 - T / 2);
        add(G, box(0.5 + r() * 0.8, 0.06, T + 0.04), moss, x, H * 0.6 + r() * 0.3, z); }
      // the kirkyard: leaning headstones with rounded heads, and a cross
      const head = new THREE.Shape(); head.moveTo(-0.32, 0); head.lineTo(0.32, 0); head.lineTo(0.32, 0.8); head.absarc(0, 0.8, 0.32, 0, Math.PI, false); head.closePath();
      const hg = new THREE.ExtrudeGeometry(head, { depth: 0.12, bevelEnabled: true, bevelSize: 0.02, bevelThickness: 0.02, bevelSegments: 1 });
      for (let i = 0; i < 7; i++) { const x = -L / 2 + 1 + (i % 4) * 2.2 + r() * 0.5, z = W / 2 + 2.2 + Math.floor(i / 4) * 1.8;
        const m = add(G, hg, oldStone, x, -0.15, z, (r() - 0.5) * 0.3); m.rotation.x = (r() - 0.5) * 0.3; m.rotation.z = (r() - 0.5) * 0.25; }
      add(G, box(0.22, 1.6, 0.2), oldStone, L / 2 + 1.8, 0.7, W / 2 + 2); add(G, box(0.9, 0.2, 0.2), oldStone, L / 2 + 1.8, 1.15, W / 2 + 2);
      add(G, new THREE.TorusGeometry(0.3, 0.05, 8, 20), oldStone, L / 2 + 1.8, 1.15, W / 2 + 2);
      for (const z of [-W / 2 + T / 2, W / 2 - T / 2]) solid(G, 0, H / 2, z, L / 2, H / 2, T / 2);
      solid(G, L / 2 - T / 2, (H + rise) / 2, 0, T / 2, (H + rise) / 2, W / 2);
      for (const s of [-1, 1]) solid(G, -L / 2 + T / 2, H / 2, s * (W / 4 + 0.35), T / 2, H / 2, W / 4 - 0.35);
      hole(G, L / 2 + 0.3, W / 2 + 0.3);
      return [L / 2 - 1.3, 0];                                                       // the item lies under the east window, where the altar stood
    },
    tidepools(G) {
      // three pools in a shelf of rock at the tide line, weed, mussels, starfish
      const pools = [[0, 0, 1.6], [3.2, 1.4, 1.1], [-2.6, 1.9, 0.9]];
      const star = new THREE.Shape(); for (let k = 0; k < 10; k++) { const a = k / 10 * Math.PI * 2, rr = k % 2 ? 0.05 : 0.14; (k ? star.lineTo.bind(star) : star.moveTo.bind(star))(Math.cos(a) * rr, Math.sin(a) * rr); }
      const sg = new THREE.ExtrudeGeometry(star, { depth: 0.03, bevelEnabled: true, bevelSize: 0.015, bevelThickness: 0.015, bevelSegments: 1 }); sg.rotateX(-Math.PI / 2);
      const wetM = MS({ color: 0x1b2f33, roughness: 0.04, transparent: true, opacity: 0.86, envMapIntensity: 1.2 });
      const bedM = MS({ map: HDT('rock', 0.8, 0.8), color: 0x6a6458, roughness: 0.6 });
      G.position.y = hAt(G.position.x, G.position.z);
      for (const [px, pz, pr] of pools) {
        const y0 = hAt(...frame(G)(px, pz)) - G.position.y;
        add(G, new THREE.CircleGeometry(pr, 28).rotateX(-Math.PI / 2), bedM, px, y0 - 0.12, pz);
        add(G, new THREE.CircleGeometry(pr * 0.98, 28).rotateX(-Math.PI / 2), wetM, px, y0 + 0.04, pz).castShadow = false;
        const n = 9 + Math.floor(pr * 4);
        for (let k = 0; k < n; k++) { const a = k / n * 6.28 + r() * 0.3, d = pr + 0.15 + r() * 0.3;
          const m = add(G, rockGeo(0.3 + r() * 0.35, k * 13 + pr * 10), oldStone, px + Math.cos(a) * d, y0 + 0.05, pz + Math.sin(a) * d); m.rotation.y = r() * 6;
          if (r() < 0.45) for (let j = 0; j < 5; j++) add(G, new THREE.SphereGeometry(0.05, 6, 4).scale(1, 0.5, 1.8), MS({ color: 0x1a1d26, roughness: 0.35 }),
            px + Math.cos(a) * (d - 0.3) + (r() - 0.5) * 0.3, y0 + 0.12, pz + Math.sin(a) * (d - 0.3) + (r() - 0.5) * 0.3, r() * 6); }
        for (let k = 0; k < 2; k++) { const a = r() * 6.28, d = r() * pr * 0.6;
          add(G, sg, MS({ color: [0xd2602e, 0x8a3a7a, 0xe08a3a][Math.floor(r() * 3)], roughness: 0.8 }), px + Math.cos(a) * d, y0 - 0.06, pz + Math.sin(a) * d, r() * 6); }
        for (let k = 0; k < 14; k++) { const a = r() * 6.28, d = r() * pr * 0.85, b = add(G, new THREE.ConeGeometry(0.04, 0.35 + r() * 0.3, 4), MS({ color: 0x4a5a22, roughness: 0.9 }),
          px + Math.cos(a) * d, y0 - 0.02, pz + Math.sin(a) * d); b.rotation.set((r() - 0.5) * 0.6, 0, (r() - 0.5) * 0.6); }
      }
      hole(G, 5, 4);
      return [0, 0];
    },
    stones(G) {
      G.position.y = hAt(G.position.x, G.position.z);
      for (let k = 0; k < 9; k++) { const a = k / 9 * 6.28, R = 6.5, h = 1.6 + r() * 1.6;
        const x = Math.cos(a) * R, z = Math.sin(a) * R, y = hAt(...frame(G)(x, z)) - G.position.y;
        const g = box(0.7 + r() * 0.4, h, 0.45 + r() * 0.2), pa = g.attributes.position;
        for (let i = 0; i < pa.count; i++) if (pa.getY(i) > 0) pa.setX(i, pa.getX(i) * 0.72);     // tapering to the top
        g.computeVertexNormals();
        const m = add(G, g, oldStone, x, y + h / 2 - 0.2, z, -a + Math.PI / 2);
        if (k === 4) { m.rotation.z = Math.PI / 2 - 0.1; m.position.y = y + 0.3; }       // one has fallen
        else { m.rotation.z = (r() - 0.5) * 0.12; const [wx, wz] = frame(G)(x, z); o.collider(wx, G.position.y + y + h / 2, wz, 0.35, h / 2, 0.25, G.rotation.y - a + Math.PI / 2); }
        add(G, box(0.5, 0.05, 0.3), moss, x, y + h * 0.7, z, -a + Math.PI / 2);
      }
      return [0, 0];
    },
    temple(G) {
      // the monument is built later, once the facade kit exists (main.js.tpl runs the queue);
      // here its ground is cleared, its base is solid, and its place is kept
      footing(G, 17, 17);
      solid(G, 0, 1.8, 0, 8, 1.8, 8);
      (window.__placesDeferred = window.__placesDeferred || []).push(() => { if (o.facade) { const t = o.facade('ancient'), obj = t && t.g ? t.g : t; if (obj && obj.isObject3D) G.add(obj); } });
      hole(G, 9.5, 9.5);
      return [0, 9.5];                                                             // at the foot of the stair
    },
    castle(G) {
      footing(G, 17, 17);
      solid(G, 0, 3, 0, 8, 3, 8);
      (window.__placesDeferred = window.__placesDeferred || []).push(() => { if (o.facade) { const t = o.facade('keep'), obj = t && t.g ? t.g : t; if (obj && obj.isObject3D) G.add(obj); } });
      hole(G, 10, 10);
      return [0, 10];
    },
    well(G) {
      footing(G, 2.2, 2.2);
      const ring = new THREE.LatheGeometry([[0.8, 0], [1.05, 0], [1.05, 0.85], [0.8, 0.85]].map(p => new THREE.Vector2(p[0], p[1])), 24);
      add(G, ring, stone, 0, 0, 0);
      add(G, new THREE.CircleGeometry(0.8, 24).rotateX(-Math.PI / 2), MS({ color: 0x0b0f10, roughness: 0.1 }), 0, 0.5, 0);
      for (const s of [-1, 1]) add(G, box(0.14, 1.9, 0.14), darkWood, s * 0.95, 1.6, 0);
      const ax = add(G, new THREE.CylinderGeometry(0.1, 0.1, 2.0, 10), darkWood, 0, 2.1, 0); ax.rotation.z = Math.PI / 2;
      gableRoof(G, 2.4, 1.6, 2.5, 0.7, slate, darkWood, 0.2);
      add(G, new THREE.CylinderGeometry(0.17, 0.14, 0.3, 12), darkWood, 0.2, 1.35, 0);
      add(G, new THREE.CylinderGeometry(0.008, 0.008, 0.7, 4), iron, 0.2, 1.75, 0);
      solid(G, 0, 0.5, 0, 1.05, 0.5, 1.05);
      return [1.4, 0.8];
    },
  };

  // ── WHERE: beside the route, in the sentence's order ─────────────────────
  const P = o.path, segs = []; let total = 0;
  for (let i = 1; i < P.length; i++) { const l = Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]); segs.push(l); total += l; }
  const along = (f) => { let d = f * total;
    for (let i = 0; i < segs.length; i++) { if (d <= segs[i] || i === segs.length - 1) { const t = Math.min(1, d / (segs[i] || 1));
      const a = P[i], b = P[i + 1]; const dx = b[0] - a[0], dz = b[1] - a[1], l = Math.hypot(dx, dz) || 1;
      return { x: a[0] + dx * t, z: a[1] + dz * t, tx: dx / l, tz: dz / l }; } d -= segs[i]; } };
  const pathDist = (x, z) => { let best = Infinity; for (let i = 1; i < P.length; i++) { const a = P[i - 1], b = P[i], dx = b[0] - a[0], dz = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz || 1))); best = Math.min(best, Math.hypot(x - a[0] - dx * t, z - a[1] - dz * t)); } return best; };
  const land = (x, z) => WY === null || hAt(x, z) > WY + 0.35;
  const ok = (x, z, rad, wet) => Math.abs(x) < o.bound && Math.abs(z) < o.bound && (wet || land(x, z))
    && (!o.goal || Math.hypot(x - o.goal[0], z - o.goal[1]) > rad + 9) && Math.hypot(x - o.spawn[0], z - o.spawn[1]) > rad + 5
    && pathDist(x, z) > rad * 0.6 + 2.5 && places.every(q => Math.hypot(x - q.x, z - q.z) > rad + 12);
  // the shore: land just above the water with the water a few metres off
  const shore = (x0, z0) => { if (WY === null) return null; let best = null;
    for (let R = 6; R <= 70 && !best; R += 4) for (let k = 0; k < 28; k++) { const a = k / 28 * 6.28, x = x0 + Math.cos(a) * R, z = z0 + Math.sin(a) * R, h = hAt(x, z);
      if (h < WY + 0.3 || h > WY + 1.6) continue;
      for (let j = 0; j < 12; j++) { const b = j / 12 * 6.28; if (hAt(x + Math.cos(b) * 6, z + Math.sin(b) * 6) < WY - 0.2) { best = { x, z, wx: Math.cos(b), wz: Math.sin(b) }; break; } }
      if (best && !ok(best.x, best.z, 4, true)) best = null; }
    return best; };
  const rads = { cottage: 5, boathouse: 6, chapel: 7, tidepools: 5, stones: 8, well: 2, temple: 11, castle: 11 };
  const middle = named.filter(n => !n.start), N = middle.length;
  let mi = 0;
  for (const n of named) {
    const rad = rads[n.kind] || 5, G = new THREE.Group(); G.name = 'place_' + n.kind;
    let spot = null;
    const f0 = n.start ? 0.02 : 0.22 + (N > 1 ? mi / (N - 1) : 0.5) * 0.58;
    if (!n.start) mi++;
    const q = along(f0);
    if (n.kind === 'boathouse' || n.kind === 'tidepools') {
      const s = shore(q.x, q.z);
      if (s) { spot = { x: s.x - s.wx * (n.kind === 'boathouse' ? 3.4 : 0.5), z: s.z - s.wz * (n.kind === 'boathouse' ? 3.4 : 0.5), yaw: Math.atan2(-s.wz, s.wx) };   // local +x, the open end, toward the water
        if (n.kind === 'boathouse' && !land(spot.x, spot.z)) spot = null; }
      if (!spot && n.kind === 'tidepools') continue;                                 // no sea, no tide pools
    }
    for (let k = 0; k < 40 && !spot; k++) {
      const side = ((k + mi) % 2 ? 1 : -1), d = 11 + rad + Math.floor(k / 2) * 3, sl = (k % 6 - 2.5) * 4;
      const x = q.x - q.tz * side * d + q.tx * sl, z = q.z + q.tx * side * d + q.tz * sl;
      if (ok(x, z, rad, false)) spot = { x, z, yaw: Math.atan2(q.x - x, q.z - z) };   // its front faces the route
    }
    if (!spot) continue;
    G.position.set(spot.x, 0, spot.z); G.rotation.y = spot.yaw;
    scene.add(G);
    let item = null;
    try { item = KIT[n.kind](G); } catch (e) { console.warn('[places] ' + n.kind + ': ' + e.message); scene.remove(G); continue; }
    const [ix, iz] = frame(G)(item[0], item[1]);
    places.push({ kind: n.kind, start: n.start, x: spot.x, z: spot.z, yaw: spot.yaw, item: item.length > 2 ? [ix, iz, item[2]] : [ix, iz] });
    spots.push([spot.x, spot.z, rad + (n.kind === 'temple' || n.kind === 'castle' ? 12 : 2)]);   // a temple stands in a glade: a jungle's canopies spread ten metres
  }
  return { places, holes, spots, tick: (t, dt) => { for (const f of ticks) f(t, dt); } };
}
