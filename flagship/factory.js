// CRYSTAL WORKS — 3D incremental automation, core-loop prototype.
//
// The hook of this genre is one conversion: chaotic manual clicking becomes a
// machine that runs without you. So this builds exactly that loop and nothing
// else — mine, move, deliver. If it is not satisfying inside thirty seconds no
// upgrade tree will save it, and the brief is right that this is the thing to
// prove before writing thousands of lines.
//
// Performance shape: items on belts are NOT meshes. ONE InstancedMesh carries
// every crystal in the world and the tick writes matrices into it, so a
// thousand items across a hundred belts cost a single draw call.
import * as THREE from 'three';

const N = 24, T = 2, TICK = 0.42, HALF = (N * T) / 2;
const EMPTY = 0, MINER = 1, BELT = 2, HUB = 3, NODE = 4;
const DIRS = [[1, 0], [0, 1], [-1, 0], [0, -1]];        // E S W N

const cells = [];
for (let x = 0; x < N; x++) {
  cells[x] = [];
  for (let z = 0; z < N; z++) cells[x][z] = { t: EMPTY, d: 0, item: 0 };
}
const inGrid = (x, z) => x >= 0 && z >= 0 && x < N && z < N;
const wx = x => -HALF + x * T + T / 2;
const wz = z => -HALF + z * T + T / 2;

// ── scene ──────────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0d18);
scene.fog = new THREE.Fog(0x0b0d18, 52, 120);
const camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, 0.1, 500);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.06;
document.body.appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0x9fc4ff, 0x1b2038, 1.1));
const sun = new THREE.DirectionalLight(0xfff0d8, 2.2);
sun.position.set(30, 46, 20);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -HALF * 1.5;
sun.shadow.camera.right = HALF * 1.5;
sun.shadow.camera.top = HALF * 1.5;
sun.shadow.camera.bottom = -HALF * 1.5;
sun.shadow.camera.near = 1;
sun.shadow.camera.far = 170;
sun.shadow.camera.updateProjectionMatrix();
scene.add(sun);

// ── the island, chamfered underneath so it reads as FLOATING ───────────────
{
  const slab = new THREE.Mesh(new THREE.BoxGeometry(N * T, 1.2, N * T),
    new THREE.MeshStandardMaterial({ color: 0x2b3252, roughness: 0.96 }));
  slab.position.y = -0.6;
  slab.receiveShadow = true;
  scene.add(slab);

  const keel = new THREE.Mesh(new THREE.ConeGeometry(N * T * 0.6, 14, 6),
    new THREE.MeshStandardMaterial({ color: 0x1c2137, roughness: 1, flatShading: true }));
  keel.rotation.x = Math.PI;
  keel.position.y = -7.6;
  scene.add(keel);

  const pts = [];
  for (let i = 0; i <= N; i++) {
    const p = -HALF + i * T;
    pts.push(-HALF, 0.02, p, HALF, 0.02, p, p, 0.02, -HALF, p, 0.02, HALF);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  scene.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial(
    { color: 0x46527d, transparent: true, opacity: 0.22 })));
}

// ── crystal nodes: the only tiles a miner can stand on ─────────────────────
const nodeMat = new THREE.MeshStandardMaterial({
  color: 0x39e6ff, emissive: 0x1d7f9c, emissiveIntensity: 1.5,
  roughness: 0.25, flatShading: true });
const nodeGeo = new THREE.OctahedronGeometry(0.62, 0);
let rngState = 1337;
const rnd = () => (rngState = (rngState * 1664525 + 1013904223) % 4294967296) / 4294967296;
for (let k = 0; k < 16; k++) {
  const x = 2 + Math.floor(rnd() * (N - 4));
  const z = 2 + Math.floor(rnd() * (N - 4));
  if (cells[x][z].t !== EMPTY) continue;
  cells[x][z].t = NODE;
  const m = new THREE.Mesh(nodeGeo, nodeMat);
  m.position.set(wx(x), 0.7, wz(z));
  m.castShadow = true;
  m.userData.spin = 0.4 + rnd() * 0.6;
  scene.add(m);
  cells[x][z].mesh = m;
}

// ── build meshes ───────────────────────────────────────────────────────────
const MAT = {
  miner: new THREE.MeshStandardMaterial({ color: 0xff5d73, roughness: 0.4, metalness: 0.35 }),
  belt: new THREE.MeshStandardMaterial({ color: 0x3ad39a, roughness: 0.6, metalness: 0.2 }),
  hub: new THREE.MeshStandardMaterial({ color: 0xffc75a, roughness: 0.35, metalness: 0.45,
    emissive: 0x6b4a00, emissiveIntensity: 0.6 }),
};
const GEO = {
  miner: new THREE.BoxGeometry(T * 0.74, 1.5, T * 0.74),
  belt: new THREE.BoxGeometry(T * 0.9, 0.22, T * 0.9),
  arrow: new THREE.ConeGeometry(0.2, 0.5, 4),
  hub: new THREE.CylinderGeometry(T * 0.5, T * 0.58, 1.1, 8),
};

function refreshCounts() {
  let m = 0, b = 0;
  for (let x = 0; x < N; x++) {
    for (let z = 0; z < N; z++) {
      if (cells[x][z].t === MINER) m++;
      else if (cells[x][z].t === BELT) b++;
    }
  }
  document.getElementById('nmine').textContent = m;
  document.getElementById('nbelt').textContent = b;
}

function removeAt(x, z) {
  const c = cells[x][z];
  if (c.build) { scene.remove(c.build); c.build = null; }
  c.t = c.mesh ? NODE : EMPTY;               // a node outlives its miner
  c.item = 0;
  refreshCounts();
}

function place(x, z, type, dir) {
  const c = cells[x][z];
  if (type === MINER && c.t !== NODE && c.t !== MINER) return false;
  if (type !== MINER && c.t === NODE) return false;      // keep nodes clear
  if (c.build) { scene.remove(c.build); c.build = null; }
  const g = new THREE.Group();
  if (type === MINER) {
    const b = new THREE.Mesh(GEO.miner, MAT.miner);
    b.position.y = 0.75; b.castShadow = true; g.add(b);
  } else if (type === BELT) {
    const b = new THREE.Mesh(GEO.belt, MAT.belt);
    b.position.y = 0.11; b.castShadow = true; b.receiveShadow = true; g.add(b);
    const a = new THREE.Mesh(GEO.arrow, MAT.belt);
    a.position.set(0.55, 0.3, 0);
    a.rotation.z = -Math.PI / 2;
    g.add(a);
    g.rotation.y = -dir * Math.PI / 2;
  } else if (type === HUB) {
    const b = new THREE.Mesh(GEO.hub, MAT.hub);
    b.position.y = 0.55; b.castShadow = true; g.add(b);
  }
  g.position.set(wx(x), 0, wz(z));
  scene.add(g);
  c.build = g;
  c.t = type;
  c.d = dir;
  c.item = 0;
  refreshCounts();
  return true;
}

// ── items: one InstancedMesh for every crystal in transit ──────────────────
const MAX_ITEMS = 4000;
const items = new THREE.InstancedMesh(
  new THREE.OctahedronGeometry(0.26, 0),
  new THREE.MeshStandardMaterial({ color: 0x7df9ff, emissive: 0x2aa6c4,
    emissiveIntensity: 1.4, roughness: 0.3, flatShading: true }),
  MAX_ITEMS);
items.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
items.frustumCulled = false;
items.count = 0;
scene.add(items);

const _m = new THREE.Matrix4();
const _p = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3(1, 1, 1);
const _up = new THREE.Vector3(0, 1, 0);

// ── the tick: belts advance, miners feed, the hub banks ────────────────────
let ore = 0;
let sinceTick = 0;
let minedWindow = 0;
let rateWindow = 0;

function step() {
  // Collect first, THEN commit. Moving in place would let one item ride the
  // whole line in a single tick depending on iteration order.
  const moves = [];
  for (let x = 0; x < N; x++) {
    for (let z = 0; z < N; z++) {
      const c = cells[x][z];
      if (c.t !== BELT || !c.item) continue;
      const d = DIRS[c.d];
      const nx = x + d[0], nz = z + d[1];
      if (!inGrid(nx, nz)) continue;
      const dst = cells[nx][nz];
      if (dst.t === HUB) moves.push([x, z, null]);
      else if (dst.t === BELT && !dst.item) moves.push([x, z, [nx, nz]]);
    }
  }
  for (const mv of moves) {
    const c = cells[mv[0]][mv[1]];
    if (mv[2]) cells[mv[2][0]][mv[2][1]].item = c.item;
    else ore += c.item;
    c.item = 0;
  }
  for (let x = 0; x < N; x++) {
    for (let z = 0; z < N; z++) {
      const c = cells[x][z];
      if (c.t !== MINER) continue;
      const d = DIRS[c.d];
      const nx = x + d[0], nz = z + d[1];
      if (!inGrid(nx, nz)) continue;
      const dst = cells[nx][nz];
      if (dst.t === BELT && !dst.item) dst.item = 1;
      else if (dst.t === HUB) ore += 1;
    }
  }
}

// Items are drawn BETWEEN their tile and the next, so the motion reads smooth
// even though the simulation is a discrete grid step. A blocked item sits
// still, which is what makes a jam legible.
function drawItems(alpha) {
  let n = 0;
  const spin = performance.now() * 0.002;
  for (let x = 0; x < N && n < MAX_ITEMS; x++) {
    for (let z = 0; z < N && n < MAX_ITEMS; z++) {
      const c = cells[x][z];
      if (c.t !== BELT || !c.item) continue;
      const d = DIRS[c.d];
      const nx = x + d[0], nz = z + d[1];
      const ahead = inGrid(nx, nz) ? cells[nx][nz] : null;
      const free = ahead && (ahead.t === HUB || (ahead.t === BELT && !ahead.item));
      const a = free ? alpha : 0;
      _p.set(wx(x) + d[0] * T * a, 0.42, wz(z) + d[1] * T * a);
      _q.setFromAxisAngle(_up, spin);
      _m.compose(_p, _q, _s);
      items.setMatrixAt(n++, _m);
    }
  }
  items.count = n;
  items.instanceMatrix.needsUpdate = true;
  return n;
}

// ── input: raycast the ground plane, drag to draw belts ────────────────────
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const hitPt = new THREE.Vector3();
let tool = 'miner';
let drawing = false;
let lastCell = null;

// In first person you aim with the CROSSHAIR, not the cursor — the pointer is
// locked and has no position. Overhead keeps the cursor. Reach is limited on
// foot for the obvious reason: a build game where you can place a machine on
// the far side of the island from where you stand is a board game again.
function cellUnder(ev) {
  if (overhead && ev) {
    ndc.set((ev.clientX / innerWidth) * 2 - 1, -(ev.clientY / innerHeight) * 2 + 1);
  } else {
    ndc.set(0, 0);
  }
  ray.setFromCamera(ndc, camera);
  if (!ray.ray.intersectPlane(plane, hitPt)) return null;
  if (!overhead && hitPt.distanceTo(camera.position) > REACH) return null;
  const x = Math.floor((hitPt.x + HALF) / T);
  const z = Math.floor((hitPt.z + HALF) / T);
  return inGrid(x, z) ? [x, z] : null;
}

// the ghost: what you are about to build, where you are about to build it
const ghost = new THREE.Mesh(
  new THREE.BoxGeometry(T * 0.92, 0.5, T * 0.92),
  new THREE.MeshBasicMaterial({ color: 0x6cf5d0, transparent: true, opacity: 0.28,
    depthWrite: false }));
ghost.visible = false;
scene.add(ghost);
const ghostEdge = new THREE.LineSegments(
  new THREE.EdgesGeometry(new THREE.BoxGeometry(T * 0.92, 0.5, T * 0.92)),
  new THREE.LineBasicMaterial({ color: 0x9dffe8, transparent: true, opacity: 0.85 }));
ghost.add(ghostEdge);

function updateGhost() {
  const c = cellUnder(null);
  if (!c) { ghost.visible = false; return; }
  const legal = tool === 'erase'
    ? cells[c[0]][c[1]].t !== EMPTY && cells[c[0]][c[1]].t !== NODE
    : tool === 'miner' ? cells[c[0]][c[1]].t === NODE
    : cells[c[0]][c[1]].t !== NODE;
  ghost.visible = true;
  ghost.position.set(wx(c[0]), 0.26, wz(c[1]));
  ghost.material.color.setHex(legal ? 0x6cf5d0 : 0xff6b7d);
  ghostEdge.material.color.setHex(legal ? 0x9dffe8 : 0xffa8b4);
}

function dirBetween(a, b) {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  for (let i = 0; i < 4; i++) if (DIRS[i][0] === dx && DIRS[i][1] === dz) return i;
  return null;
}

function apply(cell, dir) {
  const x = cell[0], z = cell[1];
  if (tool === 'erase') { removeAt(x, z); return; }
  if (tool === 'miner') { place(x, z, MINER, dir == null ? 0 : dir); return; }
  if (tool === 'hub') { place(x, z, HUB, 0); return; }
  if (tool === 'belt') { place(x, z, BELT, dir == null ? 0 : dir); }
}

renderer.domElement.addEventListener('pointerdown', e => {
  if (e.button !== 0) return;
  const c = cellUnder(e);
  if (!c) return;
  drawing = true;
  lastCell = c;
  apply(c, null);
});
renderer.domElement.addEventListener('pointermove', e => {
  if (!drawing || !lastCell) return;
  const c = cellUnder(e);
  if (!c || (c[0] === lastCell[0] && c[1] === lastCell[1])) return;
  const d = dirBetween(lastCell, c);
  if (d == null) { lastCell = c; return; }
  // the tile we just left now points at the one we moved to
  const prev = cells[lastCell[0]][lastCell[1]];
  if (prev.t === BELT || prev.t === MINER) {
    prev.d = d;
    if (prev.build && prev.t === BELT) prev.build.rotation.y = -d * Math.PI / 2;
  }
  apply(c, d);
  lastCell = c;
});
addEventListener('pointerup', () => { drawing = false; lastCell = null; });

function pickTool(name) {
  tool = name;
  document.querySelectorAll('.tool').forEach(o =>
    o.classList.toggle('on', o.dataset.tool === name));
}
document.querySelectorAll('.tool').forEach(el => {
  el.addEventListener('pointerdown', ev => { ev.stopPropagation(); pickTool(el.dataset.tool); });
});
addEventListener('keydown', e => {
  const k = { '1': 'miner', '2': 'belt', '3': 'hub', '4': 'erase' }[e.key];
  if (k) pickTool(k);
});

// ── YOU ARE ON THE ISLAND ───────────────────────────────────────────────────
// Arranging a factory on a board and STANDING IN ONE are different games. The
// second is the one people lose evenings to, because a belt you walked beside
// is yours in a way a belt you dragged on a grid is not. First person is the
// default; the overhead view stays on Tab because routing a junction from eye
// level is genuinely worse than seeing it from above, and a build game needs
// both.
const EYE = 1.68, REACH = 12;
const player = {
  pos: new THREE.Vector3(0, EYE, HALF - 4),
  vel: new THREE.Vector3(),
  // starts looking DOWN at the ground. Level-eyed, the ground plane is
  // metres beyond arm's reach and the build ghost simply never appears —
  // you would be standing in a build game with no way to tell why nothing
  // can be placed.
  yaw: Math.PI, pitch: -0.38, onGround: true,
};
let overhead = false;
let orbYaw = 0.72, orbPitch = 0.92, orbDist = 46;

const keys = Object.create(null);
addEventListener('keydown', e => {
  keys[e.code] = true;
  if (e.code === 'Tab') { e.preventDefault(); overhead = !overhead; }
});
addEventListener('keyup', e => { keys[e.code] = false; });
addEventListener('contextmenu', e => e.preventDefault());

// pointer lock is what makes it feel embodied rather than operated
renderer.domElement.addEventListener('click', () => {
  if (!overhead && document.pointerLockElement !== renderer.domElement) {
    renderer.domElement.requestPointerLock();
  }
});
addEventListener('mousemove', e => {
  if (document.pointerLockElement !== renderer.domElement) return;
  player.yaw -= e.movementX * 0.0022;
  player.pitch = Math.max(-1.45, Math.min(1.35, player.pitch - e.movementY * 0.0022));
});
addEventListener('wheel', e => {
  if (overhead) orbDist = Math.max(18, Math.min(96, orbDist * (1 + Math.sign(e.deltaY) * 0.09)));
}, { passive: true });
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

function movePlayer(dt) {
  const f = new THREE.Vector3(Math.sin(player.yaw), 0, Math.cos(player.yaw));
  const r = new THREE.Vector3(f.z, 0, -f.x);
  const wish = new THREE.Vector3();
  if (keys['KeyW']) wish.add(f);
  if (keys['KeyS']) wish.sub(f);
  if (keys['KeyD']) wish.add(r);
  if (keys['KeyA']) wish.sub(r);
  if (wish.lengthSq() > 0) wish.normalize();
  const speed = keys['ShiftLeft'] ? 11 : 6.2;
  player.vel.x = wish.x * speed;
  player.vel.z = wish.z * speed;
  if (keys['Space'] && player.onGround) { player.vel.y = 6.4; player.onGround = false; }
  player.vel.y -= 19 * dt;
  player.pos.addScaledVector(player.vel, dt);
  // the island is a slab, so the ground rule is simply its top face
  if (player.pos.y <= EYE) { player.pos.y = EYE; player.vel.y = 0; player.onGround = true; }
  // and you cannot walk off it — falling off a floating island is a death
  // this prototype has no answer for
  const lim = HALF - 0.6;
  player.pos.x = Math.max(-lim, Math.min(lim, player.pos.x));
  player.pos.z = Math.max(-lim, Math.min(lim, player.pos.z));
}

// ── a starter line, so the loop is legible the moment it loads ─────────────
(function seed() {
  // Pick a node with a CLEAR run east of it. The first version just took the
  // first node it found and drew six tiles east regardless — a second node
  // sitting in that line silently refused two placements, so the demo line
  // ended in mid-air with no hub and delivered nothing. A starter line that
  // does not complete the loop teaches the player the wrong thing.
  const RUN = 6;
  let found = null;
  for (let x = 2; x < N - RUN - 1 && !found; x++) {
    for (let z = 2; z < N - 2 && !found; z++) {
      if (cells[x][z].t !== NODE) continue;
      let clear = true;
      for (let i = 1; i <= RUN && clear; i++) clear = cells[x + i][z].t === EMPTY;
      if (clear) found = [x, z];
    }
  }
  if (!found) return;
  const x = found[0], z = found[1];
  place(x, z, MINER, 0);
  for (let i = 1; i < RUN; i++) place(x + i, z, BELT, 0);
  place(x + RUN, z, HUB, 0);
})();

// ── frame ──────────────────────────────────────────────────────────────────
let last = performance.now();
renderer.setAnimationLoop(() => {
  const now = performance.now();
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;

  sinceTick += dt;
  rateWindow += dt;
  const before = ore;
  while (sinceTick >= TICK) { sinceTick -= TICK; step(); }
  minedWindow += ore - before;
  if (rateWindow >= 1) {
    document.getElementById('rate').textContent =
      Math.round(minedWindow / rateWindow * 60);
    minedWindow = 0;
    rateWindow = 0;
  }
  document.getElementById('ore').textContent = ore;
  document.getElementById('nitem').textContent = drawItems(sinceTick / TICK);

  scene.traverse(o => { if (o.userData.spin) o.rotation.y += dt * o.userData.spin; });

  if (overhead) {
    camera.position.set(
      Math.sin(orbYaw) * Math.cos(orbPitch) * orbDist,
      Math.sin(orbPitch) * orbDist,
      Math.cos(orbYaw) * Math.cos(orbPitch) * orbDist);
    camera.lookAt(0, 0, 0);
    ghost.visible = false;
  } else {
    movePlayer(dt);
    camera.position.copy(player.pos);
    // YXZ, set directly: rotateY-then-rotateX accumulates roll and the
    // horizon slowly tilts as you look around
    camera.rotation.order = 'YXZ';
    camera.rotation.set(player.pitch, player.yaw, 0);
    updateGhost();
  }
  document.body.classList.toggle('overhead', overhead);
  renderer.render(scene, camera);
});

window.__factory = {
  cells, items, N, T, player,
  get ore() { return ore; },
  place, removeAt,
  camPos: () => camera.position.toArray(),
  ghostVisible: () => ghost.visible,
};
