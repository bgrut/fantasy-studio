// ── BODIES THAT FALL LIKE BODIES (2026-10-04) ──────────────────────────────
// A death used to turn the whole character into one rigid capsule: knocked
// back with a spin and tumbling, frozen in whatever pose it died in, a statue
// falling over. A body falls at its joints. At death this builds an
// articulated ragdoll over the shared rig (hips, spine, neck, head, upper
// and lower arms, upper and lower legs): eleven capsules joined at the hips,
// shoulders, elbows, knees and neck, shaped from the character's own bone
// lengths, pushed away from the blow that killed it; from then on the
// physics drives the bones and the skin follows, so a body folds at the
// knees, the arms trail, and it comes to rest along the ground it fell on.
// The parts do not collide with each other (overlapping capsules at a joint
// would fight), only with the world.
//
// And a body that is hit and lives reacts: the torso and head recoil away
// from the blow and spring back over a third of a second, layered on top of
// whatever the animation is doing (makeFlinch).
import * as THREE from 'three';

// [part, bone it drives, bone it reaches to, radius (x scale), parent part]
const PARTS = [
  ['pelvis', 'hips', 'spine', 0.12, null],
  ['torso', 'spine', 'neck', 0.13, 'pelvis'],
  ['head', 'head', null, 0.1, 'torso'],
  ['uparm_L', 'uparm_L', 'lowarm_L', 0.05, 'torso'],
  ['lowarm_L', 'lowarm_L', 'hand_L', 0.042, 'uparm_L'],
  ['uparm_R', 'uparm_R', 'lowarm_R', 0.05, 'torso'],
  ['lowarm_R', 'lowarm_R', 'hand_R', 0.042, 'uparm_R'],
  ['upleg_L', 'upleg_L', 'lowleg_L', 0.075, 'pelvis'],
  ['lowleg_L', 'lowleg_L', 'foot_L', 0.058, 'upleg_L'],
  ['upleg_R', 'upleg_R', 'lowleg_R', 0.075, 'pelvis'],
  ['lowleg_R', 'lowleg_R', 'foot_R', 0.058, 'upleg_R'],
];
// ragdoll parts are their own collision group: they meet the world, not each other
const GROUPS = (0x0002 << 16) | 0xfffd;

function boneMap(root) {
  const m = {};
  root.traverse(o => { if (o.isBone && !m[o.name]) m[o.name] = o; });
  return m;
}

/** an articulated ragdoll over `root`'s rig, or null when the rig is not the shared one */
export function makeRagdoll({ RAPIER, world, root, push = new THREE.Vector3(), rng = Math.random }) {
  const B = boneMap(root);
  if (!PARTS.every(([, from, to]) => B[from] && (to === null || B[to]))) return null;
  root.updateMatrixWorld(true);
  const W = (n) => B[n].getWorldPosition(new THREE.Vector3());
  // the character's scale, from its own height (crown to the lower foot)
  const H = Math.max(0.4, W('head').y - Math.min(W('foot_L').y, W('foot_R').y) + 0.12);
  const k = H / 1.75;
  const Y = new THREE.Vector3(0, 1, 0);
  const parts = {}, order = [];
  for (const [name, from, to, rk, parent] of PARTS) {
    const a = W(from);
    let b;
    if (to) b = W(to);
    else {                                                // the head runs on past its bone, to the crown
      const d = a.clone().sub(W('neck')).normalize();
      b = a.clone().add(d.multiplyScalar(0.2 * k));
    }
    const dir = b.clone().sub(a);
    const L = Math.max(0.04, dir.length());
    dir.normalize();
    const r = Math.min(rk * k, L * 0.45);
    const half = Math.max(0.01, L / 2 - r * 0.6);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const q = new THREE.Quaternion().setFromUnitVectors(Y, dir);
    const body = world.createRigidBody(RAPIER.RigidBodyDesc.dynamic()
      .setTranslation(mid.x, mid.y, mid.z).setRotation({ x: q.x, y: q.y, z: q.z, w: q.w })
      .setLinearDamping(0.35).setAngularDamping(name === 'pelvis' || name === 'torso' ? 1.2 : 2.2)
      .setCcdEnabled(true));
    world.createCollider(RAPIER.ColliderDesc.capsule(half, r)
      .setDensity(name === 'torso' || name === 'pelvis' ? 1.1 : 0.9).setFriction(0.95).setRestitution(0.02)
      .setCollisionGroups(GROUPS), body);
    const boneQ = B[from].getWorldQuaternion(new THREE.Quaternion());
    const off = q.clone().invert().multiply(boneQ);                       // body -> bone, rotation
    const offP = a.clone().sub(mid).applyQuaternion(q.clone().invert());  // body -> bone origin, position
    parts[name] = { name, body, bone: B[from], off, offP, a, q, mid, parent };
    order.push(parts[name]);
  }
  // the joints, at the point where each child part begins
  for (const p of order) {
    if (!p.parent) continue;
    const P = parts[p.parent];
    const anchorP = p.a.clone().sub(P.mid).applyQuaternion(P.q.clone().invert());
    const anchorC = p.a.clone().sub(p.mid).applyQuaternion(p.q.clone().invert());
    world.createImpulseJoint(RAPIER.JointData.spherical(
      { x: anchorP.x, y: anchorP.y, z: anchorP.z }, { x: anchorC.x, y: anchorC.y, z: anchorC.z }), P.body, p.body, true);
  }
  // the blow: the trunk is thrown away from it and up a little, the limbs follow
  const mass = order.reduce((s, p) => s + p.body.mass(), 0);
  const imp = push.clone().setY(0).normalize().multiplyScalar(2.6 * mass / order.length);
  for (const p of order) {
    const f = p.name === 'torso' ? 1.6 : p.name === 'pelvis' ? 1.0 : p.name === 'head' ? 1.3 : 0.6;
    p.body.applyImpulse({ x: imp.x * f, y: 0.9 * mass / order.length * f, z: imp.z * f }, true);
  }
  parts.torso.body.applyTorqueImpulse({ x: (rng() - 0.5) * 0.3 * k, y: (rng() - 0.5) * 0.2 * k, z: (rng() - 0.5) * 0.3 * k }, true);

  const _q = new THREE.Quaternion(), _pq = new THREE.Quaternion(), _v = new THREE.Vector3();
  /** the physics poses the bones (call every frame, parents first) */
  function sync() {
    for (const p of order) {
      const r = p.body.rotation(), t = p.body.translation();
      _q.set(r.x, r.y, r.z, r.w);
      const boneWQ = _q.clone().multiply(p.off);
      const par = p.bone.parent;
      par.updateMatrixWorld(true);
      par.getWorldQuaternion(_pq);
      p.bone.quaternion.copy(_pq.invert().multiply(boneWQ));
      if (p.name === 'pelvis') {
        _v.copy(p.offP).applyQuaternion(_q).add(t);
        p.bone.position.copy(par.worldToLocal(_v.clone()));
      }
      p.bone.updateMatrixWorld(true);
    }
  }
  function dispose() {
    for (const p of order) { try { world.removeRigidBody(p.body); } catch (e) {} }
  }
  /** how fast the body is still moving, for deciding when it has come to rest */
  const speed = () => { const v = parts.torso.body.linvel(); return Math.hypot(v.x, v.y, v.z); };
  return { sync, dispose, speed, parts: order.length };
}

/** a recoil layered on the animation: call hit(dir) on a blow, apply(dt) after the mixer each frame */
export function makeFlinch(root) {
  const B = boneMap(root);
  const chain = [['spine', 0.4], ['chest', 0.35], ['neck', 0.1], ['head', 0.3]].filter(([n]) => B[n]).map(([n, w]) => [B[n], w]);
  let t = 9, amt = 0;
  const axis = new THREE.Vector3(), _pq = new THREE.Quaternion(), _wq = new THREE.Quaternion(), _lq = new THREE.Quaternion();
  return {
    hit(dirWorld, strength = 1) {
      // the blow pushes along dir: the trunk bends away from it, about the axis across it
      axis.set(dirWorld.z, 0, -dirWorld.x);
      if (axis.lengthSq() < 1e-6) axis.set(1, 0, 0);
      axis.normalize();
      t = 0; amt = Math.min(1.4, strength);
    },
    apply(dt) {
      if (!chain.length || t > 0.6) return;
      t += dt;
      // up fast, back slow: a spring that is struck
      const k = Math.sin(Math.min(1, t / 0.07) * Math.PI / 2) * Math.exp(-Math.max(0, t - 0.07) * 7.5);
      const ang = 0.34 * k * amt;
      for (const [b, w] of chain) {
        b.parent.updateMatrixWorld(true);
        b.parent.getWorldQuaternion(_pq);
        _wq.setFromAxisAngle(axis, ang * w);
        // world-space rotation, carried into the bone's own frame
        _lq.copy(_pq).invert().multiply(_wq).multiply(_pq);
        b.quaternion.premultiply(_lq);
      }
    },
    active: () => t < 0.6,
  };
}
