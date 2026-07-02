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
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(gsize, gsize),
    new THREE.MeshStandardMaterial({ map: gtex, roughness: 1.0 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  world.createCollider(RAPIER.ColliderDesc.cuboid(gsize / 2, 0.05, gsize / 2)
    .setTranslation(0, -0.05, 0));
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
  const rng = mulberry32(SPEC.seed);
  for (const sct of SPEC.world.scatter || []) {
    try {
      const gltf = await loadGLB(sct.asset);
      for (let i = 0; i < sct.count; i++) {
        const inst = gltf.scene.clone(true);
        inst.traverse(o => { if (o.isMesh) o.castShadow = true; });
        let x, z, tries = 0;
        do {
          x = (rng() - 0.5) * gsize * 0.85; z = (rng() - 0.5) * gsize * 0.85; tries++;
        } while (Math.hypot(x, z) < sct.min_dist_m && tries < 20);
        const jitter = 1 + (rng() - 0.5) * 2 * sct.scale_jitter;
        inst.scale.multiplyScalar(jitter);
        inst.rotation.y = rng() * Math.PI * 2;
        const bb = new THREE.Box3().setFromObject(inst);
        inst.position.set(x, -bb.min.y, z);
        scene.add(inst);
        if (sct.collide) {
          const r = Math.max(bb.max.x - bb.min.x, bb.max.z - bb.min.z) * 0.25;
          world.createCollider(RAPIER.ColliderDesc.cylinder((bb.max.y - bb.min.y) / 2, Math.max(r, 0.1))
            .setTranslation(x, (bb.max.y - bb.min.y) / 2, z));
        }
      }
    } catch (e) { fail(e.message); }
  }

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

  // exposed for the verify harness (synthetic input + position probes)
  window.__game = { pos: () => playerObj.position.toArray(), keys, ready: true };

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
