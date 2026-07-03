// Fantasy Studio game runtime (Phase 26). Deterministic template — the
// exporter injects __GAME_SPEC__ and never edits logic. three.js r170 (MIT) +
// Rapier 0.14 (Apache-2.0), all vendored locally: works fully offline.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/jsm/loaders/GLTFLoader.js';
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
  document.getElementById('app').appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(pal.sky);
  if (SPEC.world.fog) scene.fog = new THREE.Fog(pal.fog, SPEC.world.size_m * 0.25, SPEC.world.size_m * 0.9);

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

  // ── ground (subtle procedural variation so it isn't a flat cartoon plane) ─
  const gsize = SPEC.world.size_m;
  const gcol = new THREE.Color(...SPEC.world.ground_color);
  const cnv = document.createElement('canvas'); cnv.width = cnv.height = 256;
  const ctx = cnv.getContext('2d');
  const rngTex = mulberry32(SPEC.seed + 1);
  ctx.fillStyle = '#' + gcol.getHexString(); ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2600; i++) {
    const sh = (rngTex() - 0.5) * 0.22;
    const c2 = gcol.clone().offsetHSL(0, (rngTex() - 0.5) * 0.06, sh * 0.5);
    ctx.fillStyle = '#' + c2.getHexString();
    ctx.fillRect(rngTex() * 256, rngTex() * 256, 1 + rngTex() * 3, 1 + rngTex() * 3);
  }
  const gtex = new THREE.CanvasTexture(cnv);
  gtex.wrapS = gtex.wrapT = THREE.RepeatWrapping;
  gtex.repeat.set(gsize / 8, gsize / 8);
  gtex.colorSpace = THREE.SRGBColorSpace;
  // Phase 32 LEVEL: terrain heightfield (hills, flattened path corridor) when
  // the LevelPlan is present; flat plane otherwise. hAt(x,z) is THE ground
  // sampler — scatter, objectives, NPCs and landmarks all sit on it.
  const LVL = SPEC.world.level || null;
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
      uvs[k * 2] = j / (n - 1) * gsize / 8; uvs[k * 2 + 1] = i / (n - 1) * gsize / 8;
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

  function prepModel(gltf, targetH) {
    const root = gltf.scene;
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
  for (const sct of SPEC.world.scatter || []) {
    try {
      const gltf = await loadGLB(sct.asset);
      if (!landmarkAsset) landmarkAsset = gltf;
      for (let i = 0; i < sct.count; i++) {
        const inst = gltf.scene.clone(true);
        inst.traverse(o => { if (o.isMesh) o.castShadow = true; });
        let x, z, tries = 0;
        do {
          x = (rng() - 0.5) * gsize * 0.85; z = (rng() - 0.5) * gsize * 0.85; tries++;
        } while ((Math.hypot(x, z) < sct.min_dist_m || pathDist(x, z) < CORR) && tries < 30);
        placeProp(inst, x, z, 1 + (rng() - 0.5) * 2 * sct.scale_jitter, sct.collide);
      }
    } catch (e) { fail(e.message); }
  }
  if (LVL && LVL.landmarks && landmarkAsset) {
    for (const [lx, lz, ls] of LVL.landmarks) {
      const inst = landmarkAsset.scene.clone(true);
      inst.traverse(o => { if (o.isMesh) o.castShadow = true; });
      placeProp(inst, lx, lz, ls, true);
    }
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
  for (const ent of SPEC.entities || []) {
    try {
      const gltf = await loadGLB(ent.asset);
      for (let i = 0; i < (ent.count || 1); i++) {
        const inst = i === 0 ? gltf.scene : gltf.scene.clone(true);
        inst.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
        const box = new THREE.Box3().setFromObject(inst);
        const h = Math.max(box.max.y - box.min.y, 1e-3);
        inst.scale.multiplyScalar((ent.height_m || 1.0) / h);
        const b2 = new THREE.Box3().setFromObject(inst);
        const holder = new THREE.Group();
        inst.position.y = -b2.min.y;
        holder.add(inst);
        holder.position.set((rngN() - 0.5) * gsize * 0.3, 0, (rngN() - 0.5) * gsize * 0.3);
        scene.add(holder);
        npcs.push({ obj: holder, speed: ent.speed || 1.5, behavior: ent.behavior || 'wander',
                    target: null, yaw: rngN() * Math.PI * 2, phase: rngN() * Math.PI * 2 });
      }
    } catch (e) { fail(e.message); }
  }
  function stepNPCs(dt, playerPos, t) {
    for (const n of npcs) {
      let tx = null, tz = null;
      if (n.behavior === 'follow') {
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        if (d > 2.6) { tx = playerPos.x; tz = playerPos.z; }
      } else if (n.behavior === 'wander') {
        if (!n.target || Math.hypot(n.target[0] - n.obj.position.x, n.target[1] - n.obj.position.z) < 0.6) {
          n.target = [(rngN() - 0.5) * gsize * 0.6, (rngN() - 0.5) * gsize * 0.6];
        }
        tx = n.target[0]; tz = n.target[1];
      }
      if (tx !== null) {
        const dx = tx - n.obj.position.x, dz = tz - n.obj.position.z;
        const want = Math.atan2(dx, dz);
        n.yaw = THREE.MathUtils.damp(n.yaw, want, 6, dt);
        n.obj.rotation.y = n.yaw;
        const sp = n.speed * dt;
        n.obj.position.x += Math.sin(n.yaw) * sp;
        n.obj.position.z += Math.cos(n.yaw) * sp;
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z)
                         + Math.abs(Math.sin(t * 7 + n.phase)) * 0.045;  // terrain + gait bob
      } else {
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z)
                         + Math.sin(t * 2 + n.phase) * 0.01 + 0.01;      // terrain + idle breath
      }
      // stay inside the walls
      const lim = gsize * 0.47;
      n.obj.position.x = THREE.MathUtils.clamp(n.obj.position.x, -lim, lim);
      n.obj.position.z = THREE.MathUtils.clamp(n.obj.position.z, -lim, lim);
    }
  }

  // ── objectives: glowing collectibles + counter + win state ───────────────
  const collectibles = [];
  let collected = 0, winTotal = 0, objLabel = '';
  const objEl = document.getElementById('obj');
  const obj = (SPEC.objectives || []).find(o => o.kind === 'collect');
  if (obj) {
    winTotal = obj.count; objLabel = obj.label || 'items';
    const rngC = mulberry32(SPEC.seed + 77);
    const geo = new THREE.SphereGeometry(0.11, 12, 10);
    const pts = (LVL && LVL.collect_points && LVL.collect_points.length >= winTotal)
      ? LVL.collect_points : null;             // Phase 32: along the route
    for (let i = 0; i < winTotal; i++) {
      const m = new THREE.MeshStandardMaterial({
        color: 0xfff2b0, emissive: 0xffd54a, emissiveIntensity: 2.6, roughness: 0.4 });
      const s = new THREE.Mesh(geo, m);
      let cx, cz;
      if (pts) { cx = pts[i][0]; cz = pts[i][1]; }
      else {
        const ang = rngC() * Math.PI * 2;
        const dist = 5 + rngC() * gsize * 0.32;
        cx = Math.cos(ang) * dist; cz = Math.sin(ang) * dist;
      }
      const baseY = hAt(cx, cz) + 1.0 + rngC() * 0.6;
      s.position.set(cx, baseY, cz);
      const halo = new THREE.PointLight(0xffd54a, 2.2, 6.0);
      s.add(halo);
      scene.add(s);
      collectibles.push({ mesh: s, baseY, phase: rngC() * Math.PI * 2 });
    }
    objEl.style.display = 'block';
    objEl.textContent = `${objLabel}: 0 / ${winTotal}`;
  }
  let won = false;
  function doWin(text) {
    if (won) return;
    won = true;
    document.getElementById('wintext').textContent = text;
    document.getElementById('win').style.display = 'flex';
    console.log('[game] WIN — ' + text);
  }
  function onCollect() {
    collected++;
    if (collected >= winTotal && goalPos) {
      objEl.textContent = `${objLabel}: ${collected} / ${winTotal} — reach the beacon!`;
    } else {
      objEl.textContent = `${objLabel}: ${collected} / ${winTotal}`;
    }
    if (collected >= winTotal && !goalPos) {
      doWin(`All ${winTotal} ${objLabel} collected.`);
    }
  }
  if (goalPos && !obj) { objEl.style.display = 'block'; objEl.textContent = 'reach the beacon'; }

  // ── player: animated GLB + kinematic capsule ─────────────────────────────
  let mixer = null, actions = {}, current = null;
  const P = SPEC.player;
  const pg = await loadGLB(P.asset);            // hard fail = visible error
  const { holder, radius } = prepModel(pg, P.height_m);
  holder.rotation.y = THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);
  const playerObj = new THREE.Group();
  playerObj.add(holder);
  scene.add(playerObj);

  if (pg.animations && pg.animations.length) {
    mixer = new THREE.AnimationMixer(pg.scene);
    for (const clip of pg.animations) actions[clip.name] = mixer.clipAction(clip);
    const pick = want => actions[P.anims[want]] || actions[want] ||
                         actions[Object.keys(actions)[0]];
    actions.__idle = pick('idle'); actions.__walk = pick('walk'); actions.__run = pick('run');
    current = actions.__idle; current.play();
  } else {
    console.warn('[game] player GLB has no animations — static fallback');
  }
  function setAnim(next) {
    if (!mixer || !next || next === current) return;
    next.reset(); next.crossFadeFrom(current, 0.22, true); next.play();
    current = next;
  }

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

  // exposed for the verify harness (synthetic input, position probes, dev teleport)
  window.__game = {
    pos: () => playerObj.position.toArray(), keys, ready: true,
    tp: (x, z) => body.setTranslation({ x, y: P.height_m / 2 + 0.1, z }, true),
    objectives: () => ({ collected, total: winTotal,
                         left: collectibles.filter(c => c.mesh.parent).map(c => c.mesh.position.toArray()) }),
    npcs: () => npcs.map(n => ({ behavior: n.behavior, pos: n.obj.position.toArray() })),
  };

  // ── main loop ────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  const fpsEl = document.getElementById('fps');
  let fCount = 0, fTime = 0, modelYaw = 0;
  const camTarget = new THREE.Vector3();

  renderer.setAnimationLoop(() => {
    const dt = Math.min(clock.getDelta(), 0.05);
    const mv = readMove();
    const speed = (mv.run ? P.run_speed : P.walk_speed) * mv.mag;

    // camera-relative movement direction
    const dir = new THREE.Vector3(mv.x, 0, mv.z);
    if (dir.lengthSq() > 1e-4) {
      dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
      modelYaw = THREE.MathUtils.damp(modelYaw, Math.atan2(dir.x, dir.z),
        P.turn_speed, dt);
    }
    vy = Math.max(vy - 9.81 * dt, -25);
    const desired = { x: dir.x * speed * dt, y: vy * dt, z: dir.z * speed * dt };
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

    // goal beacon: pulse + win when reached (with objectives complete)
    if (goalPos && !won) {
      if (goalMesh) goalMesh.rotation.z += dt * 0.8;
      const gd = Math.hypot(goalPos.x - nt.x, goalPos.z - nt.z);
      if (gd < 2.2 && collected >= winTotal) {
        doWin(winTotal > 0
          ? `All ${winTotal} ${objLabel} collected — beacon reached!`
          : 'Beacon reached!');
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
        if (dx * dx + dz * dz < 1.4 * 1.4) { scene.remove(c.mesh); onCollect(); }
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

    renderer.render(scene, camera);
    fCount++; fTime += dt;
    if (fTime >= 0.5) { fpsEl.textContent = Math.round(fCount / fTime) + ' fps'; fCount = 0; fTime = 0; }
  });

  addEventListener('resize', () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
  console.log('[game] ready:', SPEC.title);
}

main().catch(e => fail(e.message || String(e)));
