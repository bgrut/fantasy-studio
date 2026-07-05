// Fantasy Studio game runtime (Phase 26). Deterministic template — the
// exporter injects __GAME_SPEC__ and never edits logic. three.js r170 (MIT) +
// Rapier 0.14 (Apache-2.0), all vendored locally: works fully offline.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/jsm/loaders/GLTFLoader.js';
import { clone as skClone } from './vendor/jsm/utils/SkeletonUtils.js';
import { mergeGeometries } from './vendor/jsm/utils/BufferGeometryUtils.js';
import { Sky } from './vendor/jsm/objects/Sky.js';
import { EffectComposer } from './vendor/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './vendor/jsm/postprocessing/RenderPass.js';
import { ShaderPass } from './vendor/jsm/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from './vendor/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from './vendor/jsm/postprocessing/OutputPass.js';
import RAPIER from './vendor/rapier.es.js';

const SPEC = __GAME_SPEC__;

const errBox = document.getElementById('err');
function fail(msg) {
  errBox.style.display = 'block';
  errBox.textContent += msg + '\n';
  console.error('[game] ' + msg);
}
window.addEventListener('error', e => fail('uncaught: ' + e.message));

// seeded RNG so scatter placement is reproducible (spec.seed)
function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

const SKY = {
  day:      { sky: 0x87b5e0, fog: 0xa8c4dd, sun: 3.2, amb: 0.55, sunPos: [40, 80, 30] },
  sunset:   { sky: 0xe8996a, fog: 0xd9a07a, sun: 2.2, amb: 0.40, sunPos: [80, 25, 10] },
  night:    { sky: 0x0d1626, fog: 0x0d1626, sun: 0.35, amb: 0.15, sunPos: [30, 60, -40] },
  overcast: { sky: 0x9aa4ad, fog: 0x9aa4ad, sun: 1.2, amb: 0.65, sunPos: [20, 90, 20] },
};

async function main() {
  await RAPIER.init();
  const pal = SKY[SPEC.world.sky] || SKY.day;

  // ── renderer / scene / camera ────────────────────────────────────────────
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;   // filmic response for the Sky
  renderer.toneMappingExposure = 0.75;
  document.getElementById('app').appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(pal.sky);
  if (SPEC.world.fog) scene.fog = new THREE.Fog(pal.fog, SPEC.world.size_m * 0.25, SPEC.world.size_m * 0.9);

  // QUALITY PACK — real atmospheric sky (day/sunset/overcast) or a starfield
  // dome (night): kills the flat-color backdrop everywhere at once.
  if (SPEC.world.sky !== 'night') {
    const sky = new Sky();
    sky.scale.setScalar(4000);
    scene.add(sky);
    const su = sky.material.uniforms;
    const cfg = {
      day:      { turbidity: 6,  rayleigh: 1.2, elev: 35 },
      sunset:   { turbidity: 8,  rayleigh: 2.6, elev: 6 },
      overcast: { turbidity: 20, rayleigh: 0.6, elev: 25 },
    }[SPEC.world.sky] || { turbidity: 6, rayleigh: 1.2, elev: 35 };
    su.turbidity.value = cfg.turbidity;
    su.rayleigh.value = cfg.rayleigh;
    su.mieCoefficient.value = 0.004;
    su.mieDirectionalG.value = 0.85;
    const phi = THREE.MathUtils.degToRad(90 - cfg.elev);
    const theta = THREE.MathUtils.degToRad(38);
    su.sunPosition.value.setFromSphericalCoords(1, phi, theta);
    scene.background = null;              // the sky IS the background now
    try {
      // ENVIRONMENT REFLECTIONS baked from this same sky: glossy materials
      // (car paint, windows) pick up real reflections instead of reading
      // flat and blotchy under pure direct light.
      const pmrem = new THREE.PMREMGenerator(renderer);
      const envScene = new THREE.Scene();
      const sky2 = new Sky();
      sky2.scale.setScalar(1000);
      for (const k in su) sky2.material.uniforms[k].value = su[k].value;
      envScene.add(sky2);
      scene.environment = pmrem.fromScene(envScene, 0.02).texture;
      pmrem.dispose();
    } catch (e) { console.warn('[game] env reflections skipped: ' + e.message); }
  } else {
    const sN = 1400, sPos = new Float32Array(sN * 3);
    const sRng = mulberry32(SPEC.seed + 5);
    for (let i = 0; i < sN; i++) {
      const a = sRng() * Math.PI * 2, e = Math.asin(sRng() * 0.95 + 0.05), r = 900;
      sPos[i * 3] = r * Math.cos(e) * Math.cos(a);
      sPos[i * 3 + 1] = r * Math.sin(e);
      sPos[i * 3 + 2] = r * Math.cos(e) * Math.sin(a);
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute('position', new THREE.BufferAttribute(sPos, 3));
    const stars = new THREE.Points(sg, new THREE.PointsMaterial({
      color: 0xcdd6ff, size: 1.6, sizeAttenuation: false, fog: false,
      transparent: true, opacity: 0.9 }));
    stars.frustumCulled = false;
    scene.add(stars);
  }

  const camera = new THREE.PerspectiveCamera(SPEC.camera.fov_deg, innerWidth / innerHeight, 0.1, 1000);

  const hemi = new THREE.HemisphereLight(pal.sky, 0x3a3f35, pal.amb);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xffffff, pal.sun);
  sun.position.set(...pal.sunPos);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const sc = SPEC.world.size_m * 0.5;
  Object.assign(sun.shadow.camera, { left: -sc, right: sc, top: sc, bottom: -sc, far: 400 });
  scene.add(sun);

  // ── physics world ────────────────────────────────────────────────────────
  const world = new RAPIER.World({ x: 0, y: -9.81, z: 0 });

  // ── ground (QUALITY PACK 2: hand-painted-style ground — soft tonal
  // blotches, bare-dirt patches, fine speckle, a WORN TRAIL painted along the
  // level path, and real asphalt roads when the level carries OSM data) ─────
  const gsize = SPEC.world.size_m;
  const LVL = SPEC.world.level || null;
  const OSM = (LVL && LVL.osm) || null;
  const gcol = new THREE.Color(...SPEC.world.ground_color);
  const TEXN = LVL ? 1024 : 256;        // level ground is painted 1:1 (no tiling)
  const cnv = document.createElement('canvas'); cnv.width = cnv.height = TEXN;
  const ctx = cnv.getContext('2d');
  const rngTex = mulberry32(SPEC.seed + 1);
  ctx.fillStyle = '#' + gcol.getHexString(); ctx.fillRect(0, 0, TEXN, TEXN);
  // large soft blotches: patchy meadow / mottled concrete, not one flat tone
  for (let i = 0; i < TEXN / 12; i++) {
    const r = TEXN * (0.04 + rngTex() * 0.14), x = rngTex() * TEXN, y = rngTex() * TEXN;
    const c2 = gcol.clone().offsetHSL((rngTex() - 0.5) * 0.02, (rngTex() - 0.5) * 0.10, (rngTex() - 0.5) * 0.09);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, '#' + c2.getHexString() + '99'); g.addColorStop(1, '#' + c2.getHexString() + '00');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  }
  // bare-dirt patches showing through
  const dirt = gcol.clone().lerp(new THREE.Color(0x6b5334), 0.65);
  for (let i = 0; i < TEXN / 36; i++) {
    const r = TEXN * (0.012 + rngTex() * 0.045), x = rngTex() * TEXN, y = rngTex() * TEXN;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, '#' + dirt.getHexString() + '66'); g.addColorStop(1, '#' + dirt.getHexString() + '00');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  }
  // fine speckle (pebbles / grass tufts)
  for (let i = 0; i < TEXN * 26; i++) {
    const sh = (rngTex() - 0.5) * 0.22;
    const c2 = gcol.clone().offsetHSL(0, (rngTex() - 0.5) * 0.06, sh * 0.5);
    ctx.fillStyle = '#' + c2.getHexString();
    ctx.fillRect(rngTex() * TEXN, rngTex() * TEXN, 1 + rngTex() * 2, 1 + rngTex() * 2);
  }
  const W2T = v => (v / gsize + 0.5) * TEXN;         // world (x,z) -> texel
  function drawTrail(pts, widthM, col, alpha) {
    ctx.strokeStyle = col; ctx.globalAlpha = alpha;
    ctx.lineCap = ctx.lineJoin = 'round';
    ctx.lineWidth = Math.max(2, widthM / gsize * TEXN);
    ctx.beginPath();
    pts.forEach(([x, z], i) => i ? ctx.lineTo(W2T(x), W2T(z)) : ctx.moveTo(W2T(x), W2T(z)));
    ctx.stroke(); ctx.globalAlpha = 1;
  }
  if (OSM) {                                   // real streets: asphalt + wear
    for (const r of OSM.roads) drawTrail(r.pts, (r.w || 7) + 2, '#26262b', 0.92);
    for (const r of OSM.roads) drawTrail(r.pts, (r.w || 7) * 0.55, '#3a3a41', 0.85);
  } else if (LVL && LVL.path) {                // worn trail along the mission route
    const c = LVL.corridor_m || 5.5;
    drawTrail(LVL.path, c * 1.15, '#' + dirt.getHexString(), 0.5);
    drawTrail(LVL.path, c * 0.60, '#7a6140', 0.65);
    drawTrail(LVL.path, c * 0.22, '#8a7048', 0.75);
  }
  const gtex = new THREE.CanvasTexture(cnv);
  gtex.wrapS = gtex.wrapT = THREE.RepeatWrapping;
  gtex.repeat.set(LVL ? 1 : gsize / 8, LVL ? 1 : gsize / 8);
  gtex.anisotropy = 8;
  gtex.colorSpace = THREE.SRGBColorSpace;
  // Phase 32 LEVEL: terrain heightfield (hills, flattened path corridor) when
  // the LevelPlan is present; flat plane otherwise. hAt(x,z) is THE ground
  // sampler — scatter, objectives, NPCs and landmarks all sit on it.
  let hAt = () => 0;
  const gmat = new THREE.MeshStandardMaterial({ map: gtex, roughness: 1.0 });
  if (LVL && LVL.heights && LVL.heights.length === LVL.grid_n * LVL.grid_n) {
    const n = LVL.grid_n, hs = LVL.heights;
    hAt = (x, z) => {
      const fx = (x / gsize + 0.5) * (n - 1), fz = (z / gsize + 0.5) * (n - 1);
      const j0 = Math.max(0, Math.min(n - 2, Math.floor(fx)));
      const i0 = Math.max(0, Math.min(n - 2, Math.floor(fz)));
      const tx = Math.max(0, Math.min(1, fx - j0)), tz = Math.max(0, Math.min(1, fz - i0));
      return hs[i0 * n + j0] * (1 - tx) * (1 - tz) + hs[i0 * n + j0 + 1] * tx * (1 - tz)
           + hs[(i0 + 1) * n + j0] * (1 - tx) * tz + hs[(i0 + 1) * n + j0 + 1] * tx * tz;
    };
    // world-space grid mesh + EXACT-match trimesh collider (same vertices)
    const verts = new Float32Array(n * n * 3);
    const uvs = new Float32Array(n * n * 2);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const k = i * n + j;
      verts[k * 3] = (j / (n - 1) - 0.5) * gsize;
      verts[k * 3 + 1] = hs[k];
      verts[k * 3 + 2] = (i / (n - 1) - 0.5) * gsize;
      // 1:1 painted map; v inverted (canvas y is top-down, texture v is not)
      uvs[k * 2] = j / (n - 1); uvs[k * 2 + 1] = 1 - i / (n - 1);
    }
    const idx = new Uint32Array((n - 1) * (n - 1) * 6);
    let p = 0;
    for (let i = 0; i < n - 1; i++) for (let j = 0; j < n - 1; j++) {
      const a = i * n + j, b = a + 1, c = a + n, d = c + 1;
      idx[p++] = a; idx[p++] = c; idx[p++] = b;
      idx[p++] = b; idx[p++] = c; idx[p++] = d;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    geo.computeVertexNormals();
    const terrain = new THREE.Mesh(geo, gmat);
    terrain.receiveShadow = true;
    scene.add(terrain);
    world.createCollider(RAPIER.ColliderDesc.trimesh(verts, idx));
  } else {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(gsize, gsize), gmat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    world.createCollider(RAPIER.ColliderDesc.cuboid(gsize / 2, 0.05, gsize / 2)
      .setTranslation(0, -0.05, 0));
  }

  // goal beacon: glowing pillar at the level's goal zone — reaching it (with
  // all objectives collected) wins the level
  let goalPos = null, goalMesh = null;
  if (LVL && LVL.goal) {
    goalPos = new THREE.Vector3(LVL.goal[0], hAt(LVL.goal[0], LVL.goal[1]), LVL.goal[1]);
    const pil = new THREE.Mesh(
      new THREE.CylinderGeometry(0.9, 0.9, 22, 20, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x9f7bff, transparent: true, opacity: 0.16,
                                    side: THREE.DoubleSide, depthWrite: false }));
    pil.position.set(goalPos.x, goalPos.y + 11, goalPos.z);
    scene.add(pil);
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1.5, 0.09, 10, 40),
      new THREE.MeshStandardMaterial({ color: 0xb9a0ff, emissive: 0x7c5cff, emissiveIntensity: 2.2 }));
    ring.rotation.x = Math.PI / 2;
    ring.position.set(goalPos.x, goalPos.y + 0.25, goalPos.z);
    scene.add(ring);
    goalMesh = ring;
  }
  // invisible boundary walls — the park has edges; you can't run off the world
  const wh = 4, ext = gsize / 2;
  for (const [wx, wz, hx, hz] of [[ext, 0, 0.5, ext], [-ext, 0, 0.5, ext],
                                  [0, ext, ext, 0.5], [0, -ext, ext, 0.5]]) {
    world.createCollider(RAPIER.ColliderDesc.cuboid(hx, wh, hz).setTranslation(wx, wh, wz));
  }

  // ── asset loading ────────────────────────────────────────────────────────
  const loader = new GLTFLoader();
  const loadGLB = url => new Promise((res, rej) =>
    loader.load(url, res, undefined, () => rej(new Error('failed to load ' + url))));

  // belt-and-suspenders vs "string" strips: any alpha-aware material gets a
  // hard alphaTest so low-alpha fringe fragments DISCARD in three.js too
  function hardenAlpha(root) {
    root.traverse(o => {
      if (!o.isMesh) return;
      const ms = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of ms) {
        if (m && (m.transparent || m.alphaTest > 0) && m.map) {
          m.alphaTest = Math.max(m.alphaTest || 0, 0.55);
          m.transparent = false;      // MASK semantics: opaque + discard
          m.depthWrite = true;
          m.needsUpdate = true;
        }
      }
    });
  }
  function prepModel(gltf, targetH) {
    const root = gltf.scene;
    hardenAlpha(root);
    root.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
    const box = new THREE.Box3().setFromObject(root);
    const h = Math.max(box.max.y - box.min.y, 1e-3);
    const s = targetH / h;
    root.scale.setScalar(s);
    const box2 = new THREE.Box3().setFromObject(root);
    root.position.y -= box2.min.y;             // feet on y=0
    const holder = new THREE.Group();
    holder.add(root);
    return { holder, root, radius: Math.max((box2.max.x - box2.min.x), (box2.max.z - box2.min.z)) * 0.5 };
  }
  // rotate a model so its LONG horizontal axis points down +Z (the runtime's
  // travel direction) — cars/boats read sideways without this
  function alignLongAxis(root, enabled) {
    if (!enabled) return false;
    const bb = new THREE.Box3().setFromObject(root);
    if ((bb.max.x - bb.min.x) > (bb.max.z - bb.min.z) * 1.15) {
      // VERIFIED against Blender renders (2026-07-05): generator vehicles that
      // lie along X carry the NOSE at +X, so -90° puts the nose on +Z.
      // (+90° drives them backwards — do not "fix" this again without
      // re-rendering the asset. Per-asset flips: spec yaw_offset_deg = 180.)
      root.rotation.y -= Math.PI / 2;
      return true;
    }
    return false;
  }
  // generated-car paint reads flat/blotchy until the GPU texture tier lands —
  // a glossier material response under the Sky light hides most of it
  function polishVehiclePaint(root, enabled) {
    if (!enabled) return;
    root.traverse(o => {
      if (!o.isMesh) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (m && m.isMeshStandardMaterial) {
          m.roughness = 0.38; m.metalness = 0.28; m.needsUpdate = true;
        }
      }
    });
  }

  // ── scatter props (shared world-dressing manifest — video side reuses it) ─
  // Path-aware: props keep clear of the level's walking corridor and sit ON
  // the terrain. Landmarks = oversized instances of the first prop at the
  // LevelPlan's scenic points.
  const PATH = (LVL && LVL.path) || null;
  const CORR = (LVL && LVL.corridor_m || 5.5) + 1.5;
  function pathDist(x, z) {
    if (!PATH) return Infinity;
    let best = Infinity;
    for (let k = 0; k < PATH.length - 1; k++) {
      const [ax, az] = PATH[k], [bx, bz] = PATH[k + 1];
      const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz;
      const t = L2 < 1e-9 ? 0 : Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2));
      best = Math.min(best, Math.hypot(x - (ax + t * dx), z - (az + t * dz)));
    }
    return best;
  }

  // ── REAL-CITY BLOCKS (OSM footprints — © OpenStreetMap contributors) ─────
  // The video pipeline's city system, now shared: every named-city prompt gets
  // the actual street grid. Footprints extrude into one merged mesh (single
  // draw call) with per-building tint; each gets a box collider. Buildings
  // that would sit on the mission path / spawn / goal are skipped.
  const bldBoxes = [];                  // [minx, minz, maxx, maxz] per building
  function inBldg(x, z, pad = 1.5) {
    for (const b of bldBoxes) {
      if (x > b[0] - pad && x < b[2] + pad && z > b[1] - pad && z < b[3] + pad) return true;
    }
    return false;
  }
  if (OSM && OSM.buildings && OSM.buildings.length) {
    const wallGeos = [], capGeos = [];
    const tintA = new THREE.Color(0x8d8a84), tintB = new THREE.Color(0x5f6b78);
    const rngB = mulberry32(SPEC.seed + 77);
    // ExtrudeGeometry groups: materialIndex 0 = caps (roof/underside after the
    // rotate), 1 = side walls. Split so walls get the facade texture and roofs
    // stay plain — window grids on rooftops read as a bug from the follow-cam.
    function splitGroups(geo) {
      for (const g of geo.groups) {
        const sub = new THREE.BufferGeometry();
        for (const name of ['position', 'normal', 'uv', 'color']) {
          const a = geo.attributes[name];
          sub.setAttribute(name, new THREE.BufferAttribute(
            a.array.slice(g.start * a.itemSize, (g.start + g.count) * a.itemSize), a.itemSize));
        }
        (g.materialIndex === 0 ? capGeos : wallGeos).push(sub);
      }
    }
    for (const b of OSM.buildings) {
      let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
      for (const [px, pz] of b.pts) {
        mnx = Math.min(mnx, px); mxx = Math.max(mxx, px);
        mnz = Math.min(mnz, pz); mxz = Math.max(mxz, pz);
      }
      const cx = (mnx + mxx) / 2, cz = (mnz + mxz) / 2;
      if (Math.hypot(cx, cz) < 9) continue;                       // spawn stays open
      if (goalPos && Math.hypot(cx - goalPos.x, cz - goalPos.z) < 8) continue;
      if (pathDist(cx, cz) < CORR + Math.max(mxx - mnx, mxz - mnz) / 2) continue;
      try {
        const shape = new THREE.Shape();
        b.pts.forEach(([px, pz], i) => i ? shape.lineTo(px, -pz) : shape.moveTo(px, -pz));
        const h = Math.max(b.h || 9, 4);
        const geo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false });
        geo.rotateX(-Math.PI / 2);                                // extrude up
        const gy = hAt(cx, cz);
        geo.translate(0, gy, 0);
        const tint = tintA.clone().lerp(tintB, rngB()).offsetHSL(0, 0, (rngB() - 0.5) * 0.12);
        const nv = geo.attributes.position.count, cols = new Float32Array(nv * 3);
        for (let i = 0; i < nv; i++) { cols[i * 3] = tint.r; cols[i * 3 + 1] = tint.g; cols[i * 3 + 2] = tint.b; }
        geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
        splitGroups(geo);
        bldBoxes.push([mnx, mnz, mxx, mxz]);
        world.createCollider(RAPIER.ColliderDesc
          .cuboid((mxx - mnx) / 2, h / 2, (mxz - mnz) / 2)
          .setTranslation(cx, gy + h / 2, cz));
      } catch (e) { /* one bad footprint never kills the city */ }
    }
    if (wallGeos.length) {
      // procedural FACADE: window grid tiled in metres over the extrude UVs
      // (one 6m x 6m tile: 4 windows across, 2 floors) + a matching emissive
      // map so a fraction of windows glow — detail on EVERY building, no
      // assets, any city.
      const fc = document.createElement('canvas'); fc.width = fc.height = 256;
      const fx = fc.getContext('2d');
      const ec = document.createElement('canvas'); ec.width = ec.height = 256;
      const ex = ec.getContext('2d');
      fx.fillStyle = '#969490'; fx.fillRect(0, 0, 256, 256);   // multiplied by tint
      ex.fillStyle = '#000000'; ex.fillRect(0, 0, 256, 256);
      const rngW = mulberry32(SPEC.seed + 5);
      for (let wy = 0; wy < 2; wy++) for (let wx = 0; wx < 4; wx++) {
        const x = 10 + wx * 64, y = 16 + wy * 128, lit = rngW() < 0.28;
        fx.fillStyle = lit ? '#e8d9a8' : (rngW() < 0.5 ? '#2c3138' : '#3d4550');
        fx.fillRect(x, y, 40, 76);
        fx.strokeStyle = '#5b5b60'; fx.lineWidth = 3; fx.strokeRect(x, y, 40, 76);
        fx.fillStyle = '#77767c'; fx.fillRect(x - 4, y + 76, 48, 6);   // sill
        if (lit) { ex.fillStyle = '#cfa96a'; ex.fillRect(x, y, 40, 76); }
      }
      const facadeTex = new THREE.CanvasTexture(fc);
      const litTex = new THREE.CanvasTexture(ec);
      for (const t of [facadeTex, litTex]) {
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(1 / 6, 1 / 6);                    // extrude UVs are metres
        t.anisotropy = 4;
      }
      facadeTex.colorSpace = THREE.SRGBColorSpace;
      const walls = new THREE.Mesh(mergeGeometries(wallGeos, false),
        new THREE.MeshStandardMaterial({ vertexColors: true, map: facadeTex,
          emissive: 0xffc873, emissiveMap: litTex, emissiveIntensity: 0.4,
          roughness: 0.85, metalness: 0.08 }));
      const roofs = new THREE.Mesh(mergeGeometries(capGeos, false),
        new THREE.MeshStandardMaterial({ vertexColors: true, color: 0x77746e,
          roughness: 0.96, metalness: 0.02 }));
      for (const m of [walls, roofs]) {
        m.castShadow = true; m.receiveShadow = true;
        scene.add(m);
      }
      console.log('[game] OSM city "' + (OSM.place || '?') + '": ' + bldBoxes.length +
                  ' buildings (textured facades), ' + (OSM.roads || []).length + ' roads');
    }
  }
  const rng = mulberry32(SPEC.seed);
  let landmarkAsset = null;
  const swayProps = [];             // Phase 33: wind-swayed prop roots
  function placeProp(inst, x, z, scale, collide) {
    inst.scale.multiplyScalar(scale);
    inst.rotation.y = rng() * Math.PI * 2;
    const bb = new THREE.Box3().setFromObject(inst);
    const gy = hAt(x, z);
    inst.position.set(x, gy - bb.min.y, z);
    scene.add(inst);
    if ((bb.max.y - bb.min.y) > 1.2) swayProps.push({ o: inst, ph: rng() * Math.PI * 2 });
    if (collide) {
      const r = Math.max(bb.max.x - bb.min.x, bb.max.z - bb.min.z) * 0.25;
      world.createCollider(RAPIER.ColliderDesc.cylinder((bb.max.y - bb.min.y) / 2, Math.max(r, 0.1))
        .setTranslation(x, gy + (bb.max.y - bb.min.y) / 2, z));
    }
  }
  // QUALITY PACK: props render as INSTANCED sub-meshes — hundreds of trees at
  // 60fps instead of a sparse dozen of cloned groups.
  for (const sct of SPEC.world.scatter || []) {
    try {
      const gltf = await loadGLB(sct.asset);
      if (!landmarkAsset) landmarkAsset = gltf;
      gltf.scene.updateMatrixWorld(true);
      const parts = [];
      gltf.scene.traverse(o => {
        if (o.isMesh) parts.push({ geo: o.geometry, mat: o.material, local: o.matrixWorld.clone() });
      });
      const N = sct.count;
      const places = [];
      for (let i = 0; i < N; i++) {
        let x, z, tries = 0;
        do {
          x = (rng() - 0.5) * gsize * 0.9; z = (rng() - 0.5) * gsize * 0.9; tries++;
        } while ((Math.hypot(x, z) < sct.min_dist_m || pathDist(x, z) < CORR
                  || inBldg(x, z)) && tries < 30);
        places.push({ x, z, s: 1 + (rng() - 0.5) * 2 * sct.scale_jitter, rot: rng() * Math.PI * 2 });
      }
      const M = new THREE.Matrix4(), T = new THREE.Matrix4(), SV = new THREE.Vector3();
      for (const p of parts) {
        const im = new THREE.InstancedMesh(p.geo, p.mat, N);
        im.castShadow = true;
        im.frustumCulled = false;
        for (let i = 0; i < N; i++) {
          const pl = places[i];
          T.makeRotationY(pl.rot).scale(SV.set(pl.s, pl.s, pl.s));
          T.setPosition(pl.x, hAt(pl.x, pl.z), pl.z);
          M.multiplyMatrices(T, p.local);
          im.setMatrixAt(i, M);
        }
        im.instanceMatrix.needsUpdate = true;
        scene.add(im);
      }
      if (sct.collide) {
        for (let i = 0; i < Math.min(N, 260); i++) {
          const pl = places[i];
          world.createCollider(RAPIER.ColliderDesc.cylinder(1.6 * pl.s, 0.22 * pl.s)
            .setTranslation(pl.x, hAt(pl.x, pl.z) + 1.6 * pl.s, pl.z));
        }
      }
    } catch (e) { fail(e.message); }
  }

  // GRASS: instanced cross-blades on the terrain, thinned along the walking
  // path — the "flat green plane" is gone. (Gated off for cities/snow.)
  if ((SPEC.world.scatter || []).length && SPEC.world.grass !== false) {
    // undergrowth stays PLANT-colored: pull toward green so brown forest
    // floors get living tufts, not floating tan cards
    const gcolA = new THREE.Color(...SPEC.world.ground_color)
      .lerp(new THREE.Color(0x3f6b2a), 0.55).offsetHSL(0, 0.08, 0.06);
    const gcolB = gcolA.clone().offsetHSL(0.02, 0.05, -0.07);
    // REAL blade shape: tapered to a tip, bowed forward, shaded dark at the
    // root — reads as grass, not floating rectangles
    const blade = new THREE.PlaneGeometry(0.10, 0.34, 1, 3);
    blade.translate(0, 0.17, 0);
    {
      const bp = blade.attributes.position;
      const bcol = new Float32Array(bp.count * 3);
      for (let i = 0; i < bp.count; i++) {
        const t = bp.getY(i) / 0.34;               // 0 root -> 1 tip
        bp.setX(i, bp.getX(i) * (1 - 0.85 * t));   // taper to a point
        bp.setZ(i, t * t * 0.07);                  // bow
        const sh = 0.5 + 0.5 * t;                  // root shadow
        bcol[i * 3] = sh; bcol[i * 3 + 1] = sh; bcol[i * 3 + 2] = sh;
      }
      blade.setAttribute('color', new THREE.BufferAttribute(bcol, 3));
      blade.computeVertexNormals();
    }
    const bmat = new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, roughness: 1.0,
                                                  vertexColors: true });
    const GR = Math.min(gsize * 0.48, 70);
    const GN = Math.min(13000, Math.floor(GR * GR * 2.2));
    const rngG = mulberry32(SPEC.seed + 21);
    for (const baseRot of [0, Math.PI / 2]) {
      const im = new THREE.InstancedMesh(blade, bmat, GN);
      im.frustumCulled = false;
      const M = new THREE.Matrix4(), RX = new THREE.Matrix4();
      const SV = new THREE.Vector3(), C = new THREE.Color();
      let placed = 0;
      for (let i = 0; i < GN * 2 && placed < GN; i++) {
        const x = (rngG() - 0.5) * 2 * GR, z = (rngG() - 0.5) * 2 * GR;
        if (pathDist(x, z) < CORR * 0.5 && rngG() < 0.7) continue;   // trodden path
        if (inBldg(x, z, 0.5)) continue;                             // not through floors
        const s = 0.7 + rngG() * 0.8;
        M.makeRotationY(baseRot + rngG() * 0.9)
          .multiply(RX.makeRotationX((rngG() - 0.5) * 0.5))          // random lean
          .scale(SV.set(s, s * (0.8 + rngG() * 0.5), s));
        M.setPosition(x, hAt(x, z), z);
        im.setMatrixAt(placed, M);
        im.setColorAt(placed, C.lerpColors(gcolA, gcolB, rngG()));
        placed++;
      }
      im.count = placed;
      im.instanceMatrix.needsUpdate = true;
      if (im.instanceColor) im.instanceColor.needsUpdate = true;
      scene.add(im);
    }
  }
  if (LVL && LVL.landmarks && landmarkAsset) {
    for (const [lx, lz, ls] of LVL.landmarks) {
      const inst = landmarkAsset.scene.clone(true);
      inst.traverse(o => { if (o.isMesh) o.castShadow = true; });
      placeProp(inst, lx, lz, ls, true);
    }
  }

  // RACE COURSE FURNITURE (scalable: derived entirely from the level path, so
  // ANY race in ANY world gets it): glowing gates mark the route, a checkered
  // banner marks the finish — players can SEE where the race goes.
  if ((SPEC.objectives || []).some(o => o.kind === 'race') && PATH && PATH.length > 2 && goalPos) {
    const gateMat = new THREE.MeshStandardMaterial({
      color: 0xffa227, emissive: 0xff7a00, emissiveIntensity: 1.6, roughness: 0.5 });
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x222228, roughness: 0.6 });
    const step = Math.max(2, Math.floor(PATH.length / 6));
    for (let k = step; k < PATH.length - 1; k += step) {
      const [x, z] = PATH[k];
      const hd = Math.atan2(PATH[k + 1][0] - PATH[k][0], PATH[k + 1][1] - PATH[k][1]);
      const gate = new THREE.Group();
      const ring = new THREE.Mesh(new THREE.TorusGeometry(3.4, 0.15, 8, 28), gateMat);
      ring.position.y = 3.7;
      gate.add(ring);
      const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.45, 1.0, 4), gateMat);
      arrow.rotation.x = Math.PI / 2;                 // cone points down-route
      arrow.position.y = 3.7;
      gate.add(arrow);
      gate.position.set(x, hAt(x, z), z);
      gate.rotation.y = hd;
      scene.add(gate);
    }
    const fin = new THREE.Group();                    // checkered finish banner
    const chk = document.createElement('canvas'); chk.width = 64; chk.height = 16;
    const cx2 = chk.getContext('2d');
    for (let i = 0; i < 8; i++) for (let j = 0; j < 2; j++) {
      cx2.fillStyle = (i + j) % 2 ? '#101014' : '#f2f2ee';
      cx2.fillRect(i * 8, j * 8, 8, 8);
    }
    const banner = new THREE.Mesh(new THREE.PlaneGeometry(9.5, 1.5),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(chk), side: THREE.DoubleSide }));
    banner.position.y = 4.7;
    fin.add(banner);
    for (const sx of [-4.75, 4.75]) {
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 5.3, 8), poleMat);
      pole.position.set(sx, 2.65, 0);
      fin.add(pole);
    }
    fin.position.set(goalPos.x, goalPos.y, goalPos.z);
    fin.rotation.y = Math.atan2(goalPos.x - PATH[PATH.length - 2][0],
                                goalPos.z - PATH[PATH.length - 2][1]);
    scene.add(fin);
  }

  // ── Phase 33 dynamics: precipitation + wind ──────────────────────────────
  const WEATHER = SPEC.world.weather || 'none';
  const WIND = SPEC.world.wind ?? 0.5;
  let precip = null, precipVel = 0, precipBox = 46;
  if (WEATHER === 'rain' || WEATHER === 'snow') {
    const N = WEATHER === 'rain' ? 2200 : 1400;
    precipVel = WEATHER === 'rain' ? 20 : 1.6;
    const pos = new Float32Array(N * 3);
    const rngW = mulberry32(SPEC.seed + 913);
    for (let i = 0; i < N; i++) {
      pos[i * 3] = (rngW() - 0.5) * precipBox;
      pos[i * 3 + 1] = rngW() * 26;
      pos[i * 3 + 2] = (rngW() - 0.5) * precipBox;
    }
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const pm = new THREE.PointsMaterial({
      color: WEATHER === 'rain' ? 0x9db8d8 : 0xffffff,
      size: WEATHER === 'rain' ? 0.055 : 0.12,
      transparent: true, opacity: WEATHER === 'rain' ? 0.55 : 0.85,
      sizeAttenuation: true, depthWrite: false });
    precip = new THREE.Points(pg, pm);
    precip.frustumCulled = false;
    scene.add(precip);
  }
  function stepDynamics(dt, playerPos, t) {
    if (precip) {
      const a = precip.geometry.attributes.position, arr = a.array, N = arr.length / 3;
      const drift = WIND * (WEATHER === 'snow' ? 1.6 : 0.7);
      for (let i = 0; i < N; i++) {
        arr[i * 3 + 1] -= precipVel * dt * (0.8 + (i % 5) * 0.1);
        arr[i * 3] += Math.sin(t * 1.3 + i) * drift * dt;
        if (arr[i * 3 + 1] < 0) {
          arr[i * 3 + 1] = 24 + (i % 7);
          arr[i * 3] = playerPos.x + (Math.random() - 0.5) * precipBox;
          arr[i * 3 + 2] = playerPos.z + (Math.random() - 0.5) * precipBox;
        }
      }
      a.needsUpdate = true;
    }
    if (WIND > 0.05) {
      for (const s of swayProps) {
        s.o.rotation.z = Math.sin(t * 1.1 + s.ph) * 0.018 * WIND
                       + Math.sin(t * 2.7 + s.ph * 2) * 0.008 * WIND;
      }
    }
  }

  // ── NPC entities: wander / follow template AI ────────────────────────────
  const npcs = [];
  const rngN = mulberry32(SPEC.seed + 31);
  let vehIdx = 0;                       // starting-grid slot for vehicle rivals
  for (const ent of SPEC.entities || []) {
    try {
      const gltf = await loadGLB(ent.asset);
      const hostile = ent.behavior === 'hostile';
      const hasAnims = !!(gltf.animations && gltf.animations.length);
      for (let i = 0; i < (ent.count || 1); i++) {
        // SkeletonUtils.clone — plain clone() breaks skinned meshes (gliding)
        const inst = skClone(gltf.scene);
        hardenAlpha(inst);
        const mats = [];
        inst.traverse(o => {
          if (o.isMesh) {
            o.castShadow = true; o.frustumCulled = false;
            if (hostile) {          // own materials so the red tint/flash is per-enemy
              o.material = o.material.clone();
              if (o.material.emissive) o.material.emissive.setHex(0x550000);
              mats.push(o.material);
            }
          }
        });
        const box = new THREE.Box3().setFromObject(inst);
        const h = Math.max(box.max.y - box.min.y, 1e-3);
        inst.scale.multiplyScalar((ent.height_m || 1.0) / h);
        alignLongAxis(inst, ent.behavior === 'vehicle');   // rivals drive nose-first too
        polishVehiclePaint(inst, ent.behavior === 'vehicle');
        const b2 = new THREE.Box3().setFromObject(inst);
        const holder = new THREE.Group();
        inst.position.y = -b2.min.y;
        holder.add(inst);
        let startYaw = rngN() * Math.PI * 2;
        if (ent.behavior === 'vehicle' && PATH && PATH.length > 1) {
          // STARTING GRID: rivals line up beside the player at the route start,
          // facing down the street — no more cars materializing inside blocks
          const hd = Math.atan2(PATH[1][0] - PATH[0][0], PATH[1][1] - PATH[0][1]);
          const rx = Math.cos(hd), rz = -Math.sin(hd);         // lateral (right)
          const lane = (vehIdx % 2 ? 1 : -1) * (2.4 + Math.floor(vehIdx / 2) * 0.001);
          const back = 5 + Math.floor(vehIdx / 2) * 5.5;
          holder.position.set(
            PATH[0][0] + rx * lane - Math.sin(hd) * back, 0,
            PATH[0][1] + rz * lane - Math.cos(hd) * back);
          startYaw = hd;
          vehIdx++;
        } else {
          // hostiles spawn FAR (out along the path, guarding the objectives)
          const spread = hostile ? 0.6 : 0.3;
          holder.position.set((rngN() - 0.5) * gsize * spread, 0, (rngN() - 0.5) * gsize * spread);
          if (hostile && Math.hypot(holder.position.x, holder.position.z) < 14) {
            holder.position.x += Math.sign(holder.position.x || 1) * 16;
          }
        }
        scene.add(holder);
        // per-instance animation: idle/walk/run clips crossfade with movement
        let anim = null;
        if (hasAnims) {
          const mixer = new THREE.AnimationMixer(inst);
          const acts = {};
          for (const c of gltf.animations) acts[c.name] = mixer.clipAction(c);
          const pick = w => acts[w] || acts[Object.keys(acts)[0]];
          anim = { mixer, idle: pick('idle'), walk: pick('walk'), run: pick('run'), cur: null };
          anim.cur = anim.idle; anim.cur.play();
        }
        npcs.push({ obj: holder, speed: ent.speed || 1.5, behavior: ent.behavior || 'wander',
                    target: null, yaw: startYaw, phase: rngN() * Math.PI * 2,
                    hp: ent.hp || 3, cd: 0, dead: false, dieT: 0, mats, anim });
      }
    } catch (e) { fail(e.message); }
  }
  function stepNPCs(dt, playerPos, t) {
    for (const n of npcs) {
      // death animation: keel over + sink, then remove
      if (n.dead) {
        n.dieT += dt;
        n.obj.rotation.x = Math.min(n.dieT * 4, Math.PI / 2);
        if (n.dieT > 1.4) { scene.remove(n.obj); n.gone = true; }
        continue;
      }
      let tx = null, tz = null;
      if (n.behavior === 'hostile' && !won && !lost) {
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        if (d < 14 && d > 1.7) { tx = playerPos.x; tz = playerPos.z; }        // chase
        else if (d <= 1.7) {                                                  // attack
          n.cd -= dt;
          if (n.cd <= 0) { n.cd = 1.2; playerHit(1); }
        } else if (!n.target || Math.hypot(n.target[0] - n.obj.position.x, n.target[1] - n.obj.position.z) < 0.6) {
          n.target = [(rngN() - 0.5) * gsize * 0.6, (rngN() - 0.5) * gsize * 0.6];
          tx = n.target[0]; tz = n.target[1];
        } else { tx = n.target[0]; tz = n.target[1]; }
      } else if (n.behavior === 'vehicle') {
        // RACE AI: drive the level path toward the goal, record finish order
        if (!n.finished) {
          if (n.wp === undefined) { n.wp = 1; n.vjit = 0.85 + rngN() * 0.35; }
          const P2 = PATH || [[0, 0], [goalPos ? goalPos.x : 40, goalPos ? goalPos.z : 40]];
          const wpt = P2[Math.min(n.wp, P2.length - 1)];
          const dW = Math.hypot(wpt[0] - n.obj.position.x, wpt[1] - n.obj.position.z);
          if (dW < 3 && n.wp < P2.length - 1) n.wp++;
          else if (goalPos && Math.hypot(goalPos.x - n.obj.position.x, goalPos.z - n.obj.position.z) < 2.5) {
            n.finished = true; raceFinishers++;
          }
          tx = wpt[0]; tz = wpt[1];
        }
      } else if (n.behavior === 'follow') {
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        if (d > 2.6) { tx = playerPos.x; tz = playerPos.z; }
      } else if (n.behavior === 'wander') {
        if (!n.target || Math.hypot(n.target[0] - n.obj.position.x, n.target[1] - n.obj.position.z) < 0.6) {
          n.target = [(rngN() - 0.5) * gsize * 0.6, (rngN() - 0.5) * gsize * 0.6];
        }
        tx = n.target[0]; tz = n.target[1];
      }
      const moving = tx !== null;
      if (moving) {
        const dx = tx - n.obj.position.x, dz = tz - n.obj.position.z;
        const want = Math.atan2(dx, dz);
        // vehicles steer smoothly (no pivot-in-place), creatures turn quicker
        n.yaw = THREE.MathUtils.damp(n.yaw, want, n.behavior === 'vehicle' ? 2.2 : 6, dt);
        n.obj.rotation.y = n.yaw;
        const sp = n.speed * (n.vjit || 1) * dt;
        n.obj.position.x += Math.sin(n.yaw) * sp;
        n.obj.position.z += Math.cos(n.yaw) * sp;
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z)
                         + (n.anim ? 0 : Math.abs(Math.sin(t * 7 + n.phase)) * 0.045);
      } else {
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z)
                         + (n.anim ? 0 : Math.sin(t * 2 + n.phase) * 0.01 + 0.01);
      }
      // real gait: crossfade idle/walk/run with movement state (no more gliding)
      if (n.anim) {
        const want = moving ? (n.behavior === 'hostile' && n.speed > 2.2 ? n.anim.run : n.anim.walk)
                            : n.anim.idle;
        if (want && want !== n.anim.cur) {
          want.reset(); want.crossFadeFrom(n.anim.cur, 0.2, true); want.play();
          n.anim.cur = want;
        }
        n.anim.mixer.update(dt);
      }
      // stay inside the walls
      const lim = gsize * 0.47;
      n.obj.position.x = THREE.MathUtils.clamp(n.obj.position.x, -lim, lim);
      n.obj.position.z = THREE.MathUtils.clamp(n.obj.position.z, -lim, lim);
    }
  }

  // ── MISSIONS: ordered objective steps (collect / defeat / reach) with a
  // quest-log HUD. Genres compose from these verbs (Phase 36).
  const objEl = document.getElementById('obj');
  const questEl = document.getElementById('quest');
  let steps = (SPEC.objectives || []).map(o => ({ ...o }));
  if (!steps.length && goalPos) steps = [{ kind: 'reach', label: 'the beacon', count: 1 }];
  else if (goalPos && steps.length && steps[steps.length - 1].kind !== 'reach')
    steps.push({ kind: 'reach', label: 'the beacon', count: 1 });
  let stepIdx = -1, kills = 0, won = false, lost = false, raceFinishers = 0;
  const collectibles = [];
  const rngC = mulberry32(SPEC.seed + 77);
  const cgeo = new THREE.SphereGeometry(0.11, 12, 10);
  let cpUsed = 0;                        // LVL.collect_points consumed so far
  function spawnCollectibles(step) {
    const pts = LVL && LVL.collect_points;
    for (let i = 0; i < step.count; i++) {
      const m = new THREE.MeshStandardMaterial({
        color: 0xfff2b0, emissive: 0xffd54a, emissiveIntensity: 2.6, roughness: 0.4 });
      const s = new THREE.Mesh(cgeo, m);
      let cx, cz;
      if (pts && cpUsed < pts.length) { cx = pts[cpUsed][0]; cz = pts[cpUsed][1]; cpUsed++; }
      else {
        const ang = rngC() * Math.PI * 2;
        const d = 5 + rngC() * gsize * 0.32;
        cx = Math.cos(ang) * d; cz = Math.sin(ang) * d;
      }
      const baseY = hAt(cx, cz) + 1.0 + rngC() * 0.6;
      s.position.set(cx, baseY, cz);
      const halo = new THREE.PointLight(0xffd54a, 2.2, 6.0);
      s.add(halo);
      scene.add(s);
      collectibles.push({ mesh: s, baseY, phase: rngC() * Math.PI * 2 });
    }
  }
  function stepLabel(st) {
    if (st.kind === 'collect') return `Collect ${st.count} ${st.label || 'items'}`;
    if (st.kind === 'defeat') return `Defeat ${st.count} ${st.label || 'enemies'}`;
    if (st.kind === 'race') return `Win the race (${st.count} ${st.label || 'rivals'})`;
    return `Reach ${st.label || 'the beacon'}`;
  }
  function stepProgress(st) {
    if (st.kind === 'collect') return `${st._got || 0}/${st.count}`;
    if (st.kind === 'defeat') return `${Math.min(kills - (st._k0 || 0), st.count)}/${st.count}`;
    return '';
  }
  function renderQuest() {
    if (!steps.length) return;
    questEl.style.display = 'block';
    questEl.innerHTML = steps.map((st, i) => {
      const cls = i < stepIdx ? 'qs done' : (i === stepIdx ? 'qs active' : 'qs');
      const mark = i < stepIdx ? '✓' : (i === stepIdx ? '▸' : '·');
      const prog = i === stepIdx ? ' ' + stepProgress(st) : '';
      return `<div class="${cls}">${mark} ${stepLabel(st)}${prog}</div>`;
    }).join('');
    const st = steps[stepIdx];
    if (st) {
      objEl.style.display = 'block';
      const p = stepProgress(st);
      objEl.textContent = stepLabel(st) + (p ? ` — ${p}` : '');
    }
  }
  function advanceStep() {
    stepIdx++;
    const st = steps[stepIdx];
    if (!st) { doWin('Mission complete!'); return; }
    if (st.kind === 'collect') { st._got = 0; spawnCollectibles(st); }
    if (st.kind === 'defeat') { st._k0 = kills; }
    renderQuest();
  }
  let won_ = false;   // guard alias kept for clarity in doWin
  function doWin(text) {
    if (won || lost) return;
    won = true; won_ = true;
    document.getElementById('wintext').textContent = text;
    document.getElementById('win').style.display = 'flex';
    // Game Projects: hub passes ?next=<url> for level progression
    const nxt = new URLSearchParams(location.search).get('next');
    if (nxt && /^[\w./?=-]+$/.test(nxt)) {
      const a = document.getElementById('nextlvl');
      a.href = nxt; a.style.display = 'inline-block';
    }
    if (location.pathname.includes('/levels/')) {
      const b = document.getElementById('backhub');
      b.href = '../../../'; b.style.display = 'inline-block';
    }
    console.log('[game] WIN — ' + text);
  }

  // ── COMBAT: player health + hearts, damage vignette, lose state ──────────
  let php = SPEC.player.hp || 5;
  const maxHp = php;
  const heartsEl = document.getElementById('hearts');
  const hostilesExist = (SPEC.entities || []).some(e => e.behavior === 'hostile');
  function renderHearts() {
    if (!hostilesExist) return;
    heartsEl.style.display = 'block';
    heartsEl.textContent = '♥'.repeat(php) + '♡'.repeat(Math.max(0, maxHp - php));
    heartsEl.style.color = php <= 1 ? '#ff5c6a' : '#ff8fa0';
  }
  renderHearts();
  function doLose(text) {
    if (won || lost) return;
    lost = true;
    document.getElementById('losetext').textContent = text;
    document.getElementById('lose').style.display = 'flex';
    console.log('[game] LOSE — ' + text);
  }
  const dmgEl = document.getElementById('dmg');
  function playerHit(dmg) {
    if (won || lost) return;
    php = Math.max(0, php - dmg);
    renderHearts();
    dmgEl.style.opacity = '1';
    setTimeout(() => { dmgEl.style.opacity = '0'; }, 160);
    if (php <= 0) doLose('Overwhelmed by enemies.');
  }

  // ── player: animated GLB + kinematic capsule ─────────────────────────────
  let mixer = null, actions = {}, current = null;
  const P = SPEC.player;
  const pg = await loadGLB(P.asset);            // hard fail = visible error
  const { holder, root: pRoot, radius } = prepModel(pg, P.height_m);
  // VEHICLES: generated car GLBs lie along X (side-profile reference), but the
  // runtime's forward is +Z — auto-align the LONG axis so the car drives
  // nose-first instead of sliding sideways. yaw_offset_deg still flips 180.
  alignLongAxis(pRoot, (P.mode || 'walk') === 'drive');
  polishVehiclePaint(pRoot, (P.mode || 'walk') === 'drive');
  holder.rotation.y = THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);
  const playerObj = new THREE.Group();
  playerObj.add(holder);
  scene.add(playerObj);

  // NIGHT READABILITY: dark palettes get a soft moonlit fill parented to the
  // CAMERA — it always lights the side of the hero the player is looking at,
  // for any orbit angle. The atmosphere stays; the character never vanishes.
  if (pal.sun < 1.0) {
    scene.add(camera);                       // camera needs to be in the graph
    const fill = new THREE.PointLight(0xc3d6ff, pal.sun < 0.5 ? 120 : 40, 30, 1.9);
    fill.position.set(0, 0.6, 0.4);          // just above/behind the lens
    camera.add(fill);
    hemi.intensity = Math.max(hemi.intensity, 0.34);
    // "moonlit hero" grade: the player's own texture doubles as a faint
    // emissive map, so a dark-furred/dark-armored hero still reads at night
    holder.traverse(o => {
      if (!o.isMesh) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (m && m.emissive !== undefined && m.map) {
          m.emissiveMap = m.map; m.emissive.setScalar(0.34); m.needsUpdate = true;
        } else if (m && m.emissive) {
          m.emissive.setScalar(0.12);
        }
      }
    });
  }

  if (pg.animations && pg.animations.length) {
    mixer = new THREE.AnimationMixer(pg.scene);
    for (const clip of pg.animations) actions[clip.name] = mixer.clipAction(clip);
    const pick = want => actions[P.anims[want]] || actions[want] ||
                         actions[Object.keys(actions)[0]];
    actions.__idle = pick('idle'); actions.__walk = pick('walk'); actions.__run = pick('run');
    actions.__attack = actions['attack'] || null;    // one-shot swing overlay
    if (actions.__attack) {
      actions.__attack.setLoop(THREE.LoopOnce, 1);
      actions.__attack.clampWhenFinished = false;
    }
    current = actions.__idle; current.play();
  } else {
    console.warn('[game] player GLB has no animations — static fallback');
  }
  let attackUntil = 0;                 // swing overlay suppresses the locomotion FSM
  function setAnim(next) {
    if (!mixer || !next || next === current) return;
    if (performance.now() < attackUntil) return;
    next.reset(); next.crossFadeFrom(current, 0.22, true); next.play();
    current = next;
  }
  function playAttackAnim() {
    if (!mixer || !actions.__attack) return 0;
    const a = actions.__attack;
    const dur = Math.min(a.getClip().duration, 0.7);
    a.reset(); a.setEffectiveWeight(1); a.crossFadeFrom(current, 0.08, true); a.play();
    current = a;
    attackUntil = performance.now() + dur * 1000;
    setTimeout(() => {                 // return to locomotion after the swing
      attackUntil = 0;
      const back = actions.__idle;
      if (back) { back.reset(); back.crossFadeFrom(a, 0.15, true); back.play(); current = back; }
    }, dur * 1000);
    return dur;
  }

  // WEAPON IN HAND (bipeds): a real katana / bow parented to the hand bone —
  // it moves with the swing. Procedural, so every melee/ranged prompt gets one.
  (() => {
    const atkMode = (SPEC.player.attack && SPEC.player.attack !== 'none')
      ? SPEC.player.attack
      : ((SPEC.entities || []).some(e => e.behavior === 'hostile') ? 'melee' : 'none');
    if (atkMode === 'none') return;
    let handBone = null;
    pg.scene.traverse(o => { if (!handBone && o.isBone && /hand_R/i.test(o.name)) handBone = o; });
    if (!handBone) return;
    const w = new THREE.Group();
    if (atkMode === 'ranged') {
      const bow = new THREE.Mesh(
        new THREE.TorusGeometry(0.30, 0.013, 8, 24, Math.PI),
        new THREE.MeshStandardMaterial({ color: 0x6b4a2a, roughness: 0.8 }));
      bow.rotation.z = -Math.PI / 2;
      const str = new THREE.Mesh(
        new THREE.CylinderGeometry(0.003, 0.003, 0.60, 4),
        new THREE.MeshBasicMaterial({ color: 0xded8c4 }));
      w.add(bow, str);
    } else {
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(0.028, 0.62, 0.009),
        new THREE.MeshStandardMaterial({ color: 0xd9dfe8, metalness: 0.95, roughness: 0.22 }));
      blade.position.y = 0.37;
      const guard = new THREE.Mesh(
        new THREE.BoxGeometry(0.095, 0.018, 0.034),
        new THREE.MeshStandardMaterial({ color: 0x7a6428, metalness: 0.7, roughness: 0.45 }));
      guard.position.y = 0.055;
      const grip = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.015, 0.17, 8),
        new THREE.MeshStandardMaterial({ color: 0x241d2b, roughness: 0.9 }));
      grip.position.y = -0.04;
      w.add(blade, guard, grip);
    }
    w.traverse(o => { if (o.isMesh) o.castShadow = true; });
    w.rotation.x = Math.PI / 2;          // lie along the hand's forward
    handBone.add(w);
  })();

  const capR = Math.min(Math.max(radius * 0.6, 0.22), 0.6);
  const capHalf = Math.max(P.height_m / 2 - capR, 0.1);
  const body = world.createRigidBody(
    RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(0, P.height_m / 2 + 0.1, 0));
  const collider = world.createCollider(RAPIER.ColliderDesc.capsule(capHalf, capR), body);
  const kcc = world.createCharacterController(0.02);
  kcc.setApplyImpulsesToDynamicBodies(false);
  kcc.enableAutostep(0.3, 0.15, true);
  kcc.enableSnapToGround(0.3);
  let vy = 0;

  // ── input: keyboard + gamepad + touch stick ──────────────────────────────
  const keys = {};
  addEventListener('keydown', e => { keys[e.code] = true; });
  addEventListener('keyup', e => { keys[e.code] = false; });
  let yaw = 0, pitch = 0.35, dragging = false, px = 0, py = 0;
  renderer.domElement.addEventListener('pointerdown', e => {
    if (e.target.closest('#stick')) return;
    dragging = true; px = e.clientX; py = e.clientY;
  });
  addEventListener('pointerup', () => dragging = false);
  addEventListener('pointermove', e => {
    if (!dragging) return;
    yaw -= (e.clientX - px) * 0.005; pitch = THREE.MathUtils.clamp(pitch + (e.clientY - py) * 0.004, 0.05, 1.2);
    px = e.clientX; py = e.clientY;
  });
  // touch joystick
  const stick = document.getElementById('stick'), nub = document.getElementById('nub');
  let stickVec = { x: 0, y: 0 };
  if (stick) {
    stick.addEventListener('pointerdown', e => stick.setPointerCapture(e.pointerId));
    stick.addEventListener('pointermove', e => {
      if (e.buttons === 0) return;
      const r = stick.getBoundingClientRect();
      let dx = (e.clientX - r.left - 52) / 52, dy = (e.clientY - r.top - 52) / 52;
      const m = Math.hypot(dx, dy); if (m > 1) { dx /= m; dy /= m; }
      stickVec = { x: dx, y: dy };
      nub.style.left = 32 + dx * 30 + 'px'; nub.style.top = 32 + dy * 30 + 'px';
    });
    const reset = () => { stickVec = { x: 0, y: 0 }; nub.style.left = '32px'; nub.style.top = '32px'; };
    stick.addEventListener('pointerup', reset); stick.addEventListener('pointercancel', reset);
  }
  function readMove() {
    let x = 0, z = 0, run = false;
    if (keys.KeyW || keys.ArrowUp) z -= 1;
    if (keys.KeyS || keys.ArrowDown) z += 1;
    if (keys.KeyA || keys.ArrowLeft) x -= 1;
    if (keys.KeyD || keys.ArrowRight) x += 1;
    run = !!(keys.ShiftLeft || keys.ShiftRight);
    const gps = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const gp of gps) {
      if (!gp) continue;
      if (Math.abs(gp.axes[0]) > 0.15) x += gp.axes[0];
      if (Math.abs(gp.axes[1]) > 0.15) z += gp.axes[1];
      if (Math.abs(gp.axes[2] || 0) > 0.2) yaw -= gp.axes[2] * 0.03;
      run = run || (gp.buttons[10] && gp.buttons[10].pressed);
    }
    x += stickVec.x; z += stickVec.y;
    const m = Math.hypot(x, z);
    if (m > 1) { x /= m; z /= m; }
    return { x, z, run, mag: Math.min(m, 1) };
  }

  // ── player ATTACK: melee arc (sword and claws) or ranged projectiles ──────
  const ATTACK = SPEC.player.attack && SPEC.player.attack !== 'none'
    ? SPEC.player.attack : (hostilesExist ? 'melee' : 'none');
  if (ATTACK !== 'none') {
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent += ` · F / Space to ${ATTACK === 'ranged' ? 'shoot' : 'attack'}`;
  }
  const projectiles = [];
  let atkCd = 0;
  function dmgEnemy(n, dmg) {
    if (n.dead) return;
    n.hp -= dmg;
    for (const m of n.mats) { if (m.emissive) m.emissive.setHex(0xff4444); }
    setTimeout(() => { for (const m of n.mats) { if (m.emissive) m.emissive.setHex(0x550000); } }, 120);
    if (n.hp <= 0) {
      n.dead = true; kills++;
      const st = steps[stepIdx];
      if (st && st.kind === 'defeat') {
        renderQuest();
        if (kills - (st._k0 || 0) >= st.count) advanceStep();
      }
    }
  }
  function doAttack() {
    if (ATTACK === 'none' || atkCd > 0 || won || lost) return;
    atkCd = ATTACK === 'ranged' ? 0.35 : 0.55;
    playAttackAnim();                          // the actual katana/claw motion
    const dir = new THREE.Vector3(Math.sin(modelYaw), 0, Math.cos(modelYaw));
    if (ATTACK === 'ranged') {
      const m = new THREE.Mesh(
        new THREE.SphereGeometry(0.09, 8, 6),
        new THREE.MeshBasicMaterial({ color: 0xaef4ff }));
      m.position.copy(playerObj.position).add(new THREE.Vector3(0, P.height_m * 0.6, 0))
        .add(dir.clone().multiplyScalar(0.5));
      const glow = new THREE.PointLight(0x9fe8ff, 1.6, 4);
      m.add(glow);
      scene.add(m);
      projectiles.push({ mesh: m, vel: dir.clone().multiplyScalar(24), life: 2 });
    } else {
      // melee: damage lands MID-SWING (180ms in) so the hit matches the motion
      setTimeout(() => {
        if (won || lost) return;
        const flash = new THREE.PointLight(0xffffff, 3.5, 5);
        flash.position.copy(playerObj.position).add(dir.clone().multiplyScalar(1.2))
          .add(new THREE.Vector3(0, P.height_m * 0.5, 0));
        scene.add(flash);
        setTimeout(() => scene.remove(flash), 110);
        for (const n of npcs) {
          if (n.behavior !== 'hostile' || n.dead) continue;
          const dx = n.obj.position.x - playerObj.position.x;
          const dz = n.obj.position.z - playerObj.position.z;
          const d = Math.hypot(dx, dz);
          if (d > 2.3) continue;
          let a = Math.atan2(dx, dz) - modelYaw;
          while (a > Math.PI) a -= 2 * Math.PI;
          while (a < -Math.PI) a += 2 * Math.PI;
          if (Math.abs(a) < 1.05) dmgEnemy(n, 1);
        }
      }, 180);
    }
  }
  // controls per device: keyboard F/Space · touch ATTACK button · gamepad A/X or RT
  addEventListener('keydown', e => {
    if (e.code === 'KeyF' || e.code === 'Space') { e.preventDefault(); doAttack(); }
  });
  const atkBtn = document.getElementById('atkbtn');
  if (atkBtn && ATTACK !== 'none') {
    atkBtn.style.display = matchMedia('(pointer:coarse)').matches ? 'flex' : 'none';
    atkBtn.textContent = ATTACK === 'ranged' ? 'SHOOT' : 'ATTACK';
    atkBtn.addEventListener('pointerdown', e => { e.preventDefault(); doAttack(); });
  }
  let gpAtkHeld = false;
  function pollGamepadAttack() {
    const gps = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const gp of gps) {
      if (!gp) continue;
      const pressed = (gp.buttons[0] && gp.buttons[0].pressed) ||   // A / Cross
                      (gp.buttons[7] && gp.buttons[7].pressed);     // RT / R2
      if (pressed && !gpAtkHeld) doAttack();
      gpAtkHeld = pressed;
    }
  }

  // exposed for the verify harness (synthetic input, position probes, dev teleport)
  window.__game = {
    pos: () => playerObj.position.toArray(), keys, ready: true,
    tp: (x, z) => body.setTranslation({ x, y: P.height_m / 2 + 0.1, z }, true),
    attack: doAttack,
    combat: () => ({ hp: php, kills, mode: ATTACK, lost,
                     hostiles: npcs.filter(n => n.behavior === 'hostile' && !n.dead).length }),
    quest: () => ({ step: stepIdx, total: steps.length,
                    active: steps[stepIdx] ? stepLabel(steps[stepIdx]) : null, won }),
    objectives: () => ({ collected: steps.filter(s => s.kind === 'collect').reduce((a, s) => a + (s._got || 0), 0),
                         left: collectibles.filter(c => c.mesh.parent).map(c => c.mesh.position.toArray()) }),
    npcs: () => npcs.filter(n => !n.gone).map(n => ({ behavior: n.behavior, dead: !!n.dead, pos: n.obj.position.toArray() })),
  };

  // QUALITY PACK — cinematic post chain: subtle bloom + vignette + filmic out
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(
    new THREE.Vector2(innerWidth, innerHeight), 0.25, 0.65, 0.85);
  composer.addPass(bloom);
  const vignette = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, strength: { value: 0.42 } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform float strength; varying vec2 vUv;
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        float d = distance(vUv, vec2(0.5));
        c.rgb *= smoothstep(0.92, 0.35, d * strength * 2.0) * 0.25 + 0.75;
        gl_FragColor = c;
      }`,
  });
  composer.addPass(vignette);
  composer.addPass(new OutputPass());

  advanceStep();                          // mission begins: activate step 1

  // ── main loop ────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  const fpsEl = document.getElementById('fps');
  let fCount = 0, fTime = 0, modelYaw = 0;
  const DRIVE = SPEC.player.mode === 'drive';    // arcade car physics
  if (DRIVE && PATH && PATH.length > 1) {        // face down the street at spawn
    modelYaw = Math.atan2(PATH[1][0] - PATH[0][0], PATH[1][1] - PATH[0][1]);
  }
  if (DRIVE) {                                   // driving instructions in the HUD
    const hint = document.querySelector('#hud .hint');
    if (hint) {
      hint.textContent = 'W throttle · S brake/reverse · A/D steer · Shift boost'
        + ((SPEC.objectives || []).some(o => o.kind === 'race')
           ? ' — follow the orange gates to the checkered finish' : '');
    }
  }
  let vSpeed = 0, hudTick = 0, prevV = 0, leanP = 0, leanR = 0;
  const camTarget = new THREE.Vector3();

  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.05);
    const mv = readMove();
    let speed;
    const dir = new THREE.Vector3();
    if (DRIVE) {
      // CAR PHYSICS: throttle/brake + speed-scaled steering — no crab-walking
      const throttle = -mv.z;                       // W/up = forward
      const steer = mv.x;
      const maxV = mv.run ? P.run_speed : P.walk_speed;
      if (throttle > 0.05) vSpeed += 11 * throttle * dt;
      else if (throttle < -0.05) vSpeed -= 14 * -throttle * dt;   // brake/reverse
      else vSpeed *= Math.max(0, 1 - 1.6 * dt);                   // coast friction
      vSpeed = THREE.MathUtils.clamp(vSpeed, -maxV * 0.35, maxV);
      const grip = Math.min(Math.abs(vSpeed) / 5, 1);
      modelYaw -= steer * 1.9 * grip * Math.sign(vSpeed || 1) * dt;
      dir.set(Math.sin(modelYaw), 0, Math.cos(modelYaw));
      speed = Math.abs(vSpeed);
      vy = Math.max(vy - 9.81 * dt, -25);
      var desired = { x: dir.x * vSpeed * dt, y: vy * dt, z: dir.z * vSpeed * dt };
    } else {
      speed = (mv.run ? P.run_speed : P.walk_speed) * mv.mag;
      dir.set(mv.x, 0, mv.z);
      if (dir.lengthSq() > 1e-4) {
        dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
        modelYaw = THREE.MathUtils.damp(modelYaw, Math.atan2(dir.x, dir.z),
          P.turn_speed, dt);
      }
      vy = Math.max(vy - 9.81 * dt, -25);
      var desired = { x: dir.x * speed * dt, y: vy * dt, z: dir.z * speed * dt };
    }
    kcc.computeColliderMovement(collider, desired);
    const cm = kcc.computedMovement();
    if (kcc.computedGrounded()) vy = 0;
    const t = body.translation();
    body.setNextKinematicTranslation({ x: t.x + cm.x, y: t.y + cm.y, z: t.z + cm.z });
    world.step();

    let nt = body.translation();
    if (nt.y < -10) {   // fall-recovery safety net: respawn at origin
      body.setNextKinematicTranslation({ x: 0, y: P.height_m / 2 + 0.1, z: 0 });
      vy = 0; nt = { x: 0, y: P.height_m / 2 + 0.1, z: 0 };
      console.warn('[game] fell out of world — respawned');
    }
    playerObj.position.set(nt.x, nt.y - (capHalf + capR), nt.z);
    holder.rotation.y = modelYaw + THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);
    if (DRIVE) {
      // suspension feel: pitch under accel/brake, roll into turns
      const accel = (vSpeed - prevV) / Math.max(dt, 1e-3); prevV = vSpeed;
      leanP = THREE.MathUtils.damp(leanP,
        THREE.MathUtils.clamp(-accel * 0.012, -0.06, 0.06), 6, dt);
      leanR = THREE.MathUtils.damp(leanR,
        THREE.MathUtils.clamp(mv.x * Math.min(Math.abs(vSpeed) / 8, 1) * 0.07, -0.08, 0.08), 6, dt);
      holder.rotation.x = leanP; holder.rotation.z = leanR;
    }

    // animation state machine
    if (mixer) {
      setAnim(speed < 0.1 ? actions.__idle : (mv.run && mv.mag > 0.3 ? actions.__run : actions.__walk));
      if (current && current.getClip()) {
        const base = current === actions.__run ? P.run_speed : P.walk_speed;
        current.timeScale = speed > 0.1 ? Math.max(speed / base, 0.5) : 1.0;
      }
      mixer.update(dt);
    }

    stepNPCs(dt, nt, performance.now() / 1000);
    stepDynamics(dt, nt, performance.now() / 1000);

    // goal beacon: pulse; completes REACH steps, decides RACE steps
    if (goalPos && !won && !lost) {
      if (goalMesh) goalMesh.rotation.z += dt * 0.8;
      const st = steps[stepIdx];
      const gd = Math.hypot(goalPos.x - nt.x, goalPos.z - nt.z);
      if (st && st.kind === 'reach' && gd < 2.2) advanceStep();
      else if (st && st.kind === 'race') {
        // live standings: position = cars already finished + cars closer to goal
        hudTick += dt;
        const rivals = npcs.filter(n => n.behavior === 'vehicle');
        if (hudTick > 0.25) {
          hudTick = 0;
          const ahead = raceFinishers + rivals.filter(n => !n.finished &&
            Math.hypot(goalPos.x - n.obj.position.x, goalPos.z - n.obj.position.z) < gd).length;
          objEl.style.display = 'block';
          objEl.textContent = `Race to the beacon — position ${ahead + 1} / ${rivals.length + 1}`;
        }
        if (gd < 2.6) {
          const rank = raceFinishers + 1;
          if (rank === 1) advanceStep();
          else doLose(`Finished #${rank} — the ${st.label || 'cars'} beat you. Try again!`);
        }
      }
    }

    // combat: attack cooldown + projectiles + gamepad attack edge
    pollGamepadAttack();
    if (atkCd > 0) atkCd -= dt;
    for (let i = projectiles.length - 1; i >= 0; i--) {
      const pr = projectiles[i];
      pr.mesh.position.addScaledVector(pr.vel, dt);
      pr.life -= dt;
      let hit = false;
      for (const n of npcs) {
        if (n.behavior !== 'hostile' || n.dead) continue;
        const dd = pr.mesh.position.distanceTo(n.obj.position.clone().add(new THREE.Vector3(0, 0.5, 0)));
        if (dd < 0.9) { dmgEnemy(n, 1); hit = true; break; }
      }
      if (hit || pr.life <= 0 || pr.mesh.position.y < hAt(pr.mesh.position.x, pr.mesh.position.z) - 0.2) {
        scene.remove(pr.mesh);
        projectiles.splice(i, 1);
      }
    }

    // collectibles: bob + spin + proximity pickup
    if (collectibles.length) {
      const t = performance.now() / 1000;
      for (const c of collectibles) {
        if (!c.mesh.parent) continue;
        c.mesh.position.y = c.baseY + Math.sin(t * 2.2 + c.phase) * 0.22;
        c.mesh.rotation.y += dt * 2;
        const dx = c.mesh.position.x - nt.x, dz = c.mesh.position.z - nt.z;
        if (dx * dx + dz * dz < 1.4 * 1.4) {
          scene.remove(c.mesh);
          const st = steps[stepIdx];
          if (st && st.kind === 'collect') {
            st._got = (st._got || 0) + 1;
            renderQuest();
            if (st._got >= st.count) advanceStep();
          }
        }
      }
    }

    // third-person follow camera
    camTarget.set(nt.x, nt.y + SPEC.camera.height_m * 0.5, nt.z);
    const cd = SPEC.camera.distance_m;
    const cx = nt.x + Math.sin(yaw) * Math.cos(pitch) * cd;   // camera BEHIND
    const cz = nt.z + Math.cos(yaw) * Math.cos(pitch) * cd;   // (W walks away)
    const cy = nt.y + Math.sin(pitch) * cd + SPEC.camera.height_m * 0.4;
    camera.position.lerp(new THREE.Vector3(cx, cy, cz), 1 - Math.exp(-8 * dt));
    camera.lookAt(camTarget);

    composer.render();
    fCount++; fTime += dt;
    if (fTime >= 0.5) { fpsEl.textContent = Math.round(fCount / fTime) + ' fps'; fCount = 0; fTime = 0; }
  });

  addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
    composer.setSize(innerWidth, innerHeight);
  });
  console.log('[game] ready:', SPEC.title);
}

main().catch(e => fail(e.message || String(e)));
