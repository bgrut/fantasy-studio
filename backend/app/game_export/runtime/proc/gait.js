// THE GAIT ENGINE (2026-10-02)
// ---------------------------------------------------------------------------
// A layer between the mocap clips and the screen that moves a biped the way a
// motion analyst says people move (LOCOMOTION.md), on any rig that names its
// bones hips / spine / chest / head / uparm_* / lowarm_* / hand_* / upleg_* /
// lowleg_* / foot_*. What it fixes, measured on the knight before it existed:
//
//   ONE WHOLE CYCLE. The bake samples a fixed number of mocap frames, which
//   was 1.7 gait cycles for the walk and the run; the loop wrapped mid-stride
//   and once every loop the leg jumped from behind the body to in front of it.
//   The true period is found by autocorrelating the thighs' swing, and only
//   one whole cycle is ever played.
//
//   ONE PHASE. Walk and run were blended with each clip on its own clock, so
//   a blend mixed one clip's left step with the other's right. Both clips are
//   now driven from one gait phase, aligned on the left foot's contact.
//
//   CADENCE AND STRIDE. Speed was matched by play rate alone: a 1.2 m/s walk
//   cranked to 2.5 m/s and a 2.1 m/s jog to 6 m/s, legs cycling at three
//   hundred steps a minute. Speed is now split, as stride warping does in
//   UE5: play rate takes the square root of the ratio inside human cadence
//   limits, stride length takes the rest, and a two-bone leg IK stretches
//   each foot's reach along the direction of travel so a planted foot holds.
//
//   THE BODY IS THE MOCAP'S (2026-10-03). Arm swing, trunk lean and head
//   carriage come from the clip itself now that the retarget transfers
//   rotations (retarget_rot.py); this layer only adds what a looping clip
//   cannot know, a lean into a change of speed and a bank into a turn.
import * as THREE from 'three';

const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3();
const _q1 = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _q3 = new THREE.Quaternion();
const UP = new THREE.Vector3(0, 1, 0);

// Turn a bone by a WORLD-space rotation, keeping its parent where it is.
function rotateWorld(bone, qWorld) {
  bone.getWorldQuaternion(_q2);
  _q2.premultiply(qWorld);
  if (bone.parent) { bone.parent.getWorldQuaternion(_q3); _q3.invert(); _q2.premultiply(_q3); }
  bone.quaternion.copy(_q2);
  bone.updateMatrixWorld(true);
}
// Aim the segment from bone to its child joint at a world direction.
const _aimW = new THREE.Vector3(), _aimA = new THREE.Vector3(), _aimB = new THREE.Vector3();
function aimSegment(bone, child, dirWorld, k = 1) {
  const want = _aimW.copy(dirWorld).normalize();     // copied first: callers pass scratch vectors
  bone.getWorldPosition(_aimA); child.getWorldPosition(_aimB);
  const cur = _aimB.sub(_aimA).normalize();
  _q1.setFromUnitVectors(cur, want);
  if (k < 1) _q1.slerp(new THREE.Quaternion(), 1 - k);
  rotateWorld(bone, _q1);
}
const wp = (b, out) => b.getWorldPosition(out || new THREE.Vector3());

export function createGait({ root, actions, mixer, rates }) {
  let sk = null;
  root.traverse(o => { if (!sk && o.isSkinnedMesh && o.skeleton) sk = o.skeleton; });
  if (!sk) return null;
  const B = {};
  for (const b of sk.bones) B[b.name.toLowerCase()] = b;
  const need = ['hips', 'spine', 'upleg_l', 'lowleg_l', 'foot_l', 'upleg_r', 'lowleg_r', 'foot_r'];
  if (!need.every(n => B[n])) return null;
  const hasArms = ['uparm_l', 'lowarm_l', 'hand_l', 'uparm_r', 'lowarm_r', 'hand_r'].every(n => B[n]);

  // ── the clip's own cycle ────────────────────────────────────────────────
  // With the body still, sample a clip; the left thigh's fore-aft swing (in
  // the hips' frame) is the signal. Its autocorrelation peak past the first
  // half-cycle is the period; the left ankle's lowest point in the first
  // period is foot contact.
  const solo = (act) => {
    const muted = [];
    for (const k of Object.keys(actions)) {
      const a2 = actions[k];
      if (!a2 || a2 === act || typeof a2.getEffectiveWeight !== 'function') continue;
      muted.push([a2, a2.getEffectiveWeight(), a2.enabled]); a2.setEffectiveWeight(0);
    }
    return () => { for (const [a2, w, en] of muted) { a2.setEffectiveWeight(w); a2.enabled = en; } };
  };
  function analyse(act) {
    const clip = act.getClip(), dur = clip.duration;
    const back = solo(act);
    const wasT = act.time, wasS = act.timeScale, wasW = act.getEffectiveWeight();
    act.play(); act.setEffectiveWeight(1); act.timeScale = 1;
    const N = 96, sig = [], ank = [], rel = [];
    const hipQ = new THREE.Quaternion();
    for (let i = 0; i < N; i++) {
      act.time = (i / N) * dur; mixer.update(0); root.updateMatrixWorld(true);
      B.hips.getWorldQuaternion(hipQ); hipQ.invert();
      const th = wp(B.lowleg_l).sub(wp(B.upleg_l)).applyQuaternion(hipQ);
      const tr = wp(B.lowleg_r).sub(wp(B.upleg_r)).applyQuaternion(hipQ);
      sig.push([th.x, th.z, tr.x, tr.z]);
      ank.push(wp(B.foot_l).y - wp(B.hips).y);
      // the left ankle relative to the hips, in the model's own frame
      rel.push(root.worldToLocal(wp(B.foot_l)).sub(root.worldToLocal(wp(B.hips))));
    }
    // THE LEGS SAY WHERE FORWARD IS: a planted foot moves backward under the
    // body, so the clip's forward, in the model's frame, is against the mean
    // motion of the ankle while it is low
    const yLo = Math.min(...ank), yHi = Math.max(...ank);
    const fwd = new THREE.Vector3();
    for (let i = 1; i < N; i++) {
      if (ank[i] > yLo + (yHi - yLo) * 0.2 || ank[i - 1] > yLo + (yHi - yLo) * 0.2) continue;
      fwd.add(rel[i - 1].clone().sub(rel[i]));
    }
    fwd.y = 0; if (fwd.lengthSq() > 1e-10) fwd.normalize();
    act.time = wasT; act.timeScale = wasS; act.setEffectiveWeight(wasW); back();
    // the swing axis: whichever horizontal axis the thighs move along most
    const varOf = (c) => { const m = sig.reduce((s, r) => s + r[c], 0) / N; return sig.reduce((s, r) => s + (r[c] - m) ** 2, 0); };
    const ax = varOf(0) > varOf(1) ? 0 : 1;
    const x = sig.map(r => r[ax] - r[ax + 2]);           // left minus right: one clean wave per cycle
    const m = x.reduce((s, v) => s + v, 0) / N;
    const xs = x.map(v => v - m);
    let bestLag = N, best = -Infinity;
    for (let lag = Math.floor(N * 0.3); lag < N - 2; lag++) {
      let c = 0;
      for (let i = 0; i + lag < N; i++) c += xs[i] * xs[i + lag];
      c /= (N - lag);
      if (c > best) { best = c; bestLag = lag; }
    }
    // a clip that is already one whole cycle autocorrelates best at N itself
    let c0 = 0; for (let i = 0; i < N; i++) c0 += xs[i] * xs[(i + N - 1) % N]; c0 /= N;
    const whole = best < c0 * 0.6;
    const period = whole ? dur : (bestLag / N) * dur;
    const pN = Math.max(4, Math.round(period / dur * N));
    let lo = 0;
    for (let i = 1; i < Math.min(pN, N); i++) if (ank[i] < ank[lo]) lo = i;
    return { dur, period, contact: (lo / N) * dur, whole, fwd };
  }
  const C = {};
  for (const k of ['walk', 'run']) {
    const a = actions['__' + k];
    if (!a) continue;
    try { C[k] = analyse(a); C[k].v = rates.get(a) || 0; } catch (e) { /* the clip keeps its own clock */ }
  }
  if (!C.walk && !C.run) return null;
  // A HAND THAT HOLDS SOMETHING SWINGS LESS: a weapon or a torch on a hand
  // is carried, close and steady, not pumped overhead. Weapons are attached
  // after the engine starts and change with the loadout, so the hands are
  // looked at again every half second for a visible held mesh.
  const armed = { l: false, r: false };
  let _armedT = 0;
  function checkArmed(dt) {
    _armedT -= dt;
    if (_armedT > 0) return;
    _armedT = 0.5;
    for (const s of ['l', 'r']) {
      const h = B['hand_' + s];
      let held = false;
      if (h) h.traverse(o => { if (!held && o !== h && o.isMesh && !o.isSkinnedMesh) { let v = true, q = o; while (q && q !== h) { if (!q.visible) { v = false; break; } q = q.parent; } if (v) held = true; } });
      armed[s] = held;
    }
  }
  mixer.update(0);

  // leg lengths for the IK
  root.updateMatrixWorld(true);
  const legLen = {};
  for (const s of ['l', 'r']) {
    legLen[s] = [wp(B['upleg_' + s]).distanceTo(wp(B['lowleg_' + s])), wp(B['lowleg_' + s]).distanceTo(wp(B['foot_' + s]))];
  }

  let phase = 0;            // 0..1 of one gait cycle; 0 = left foot contact
  const st = { rate: 1, warp: 1, lean: 0, swing: 0, runK: 0, cadence: 0 };

  // ── the clock ───────────────────────────────────────────────────────────
  // called in place of per-clip timeScale: w = { walk, run } blend weights
  function drive(dt, speed, w) {
    const mv = (w.walk || 0) + (w.run || 0);
    if (mv < 1e-3) return;
    const rk = (w.run || 0) / mv;
    st.runK = rk;
    const per = (C.walk ? C.walk.period : C.run.period) * (1 - rk) + (C.run ? C.run.period : C.walk.period) * rk;
    const vn = Math.max(0.3, ((C.walk && C.walk.v) || 1.2) * (1 - rk) + ((C.run && C.run.v) || 2.2) * rk);
    // cadence: the square root of the speed ratio, inside a human's range
    // (a walk 0.75-1.35 of its clip, a run up to 1.45), stride takes the rest
    const ratio = speed / vn;
    // STRIDE WARP STAYS SMALL (2026-10-03): past about 0.8-1.4 of the clip's
    // own stride a warped leg reads as a different, wrong gait (the research
    // ranges UE5 ships use); cadence carries more of the change instead, and
    // past both the planted foot's lock holds it while the body travels on
    const rate = THREE.MathUtils.clamp(Math.sqrt(Math.max(ratio, 0.01)), 0.72, 1.35 + 0.15 * rk);
    st.rate = rate;
    st.warp = THREE.MathUtils.clamp(ratio / rate, 0.8, 1.4);
    st.cadence = 2 * 60 * rate / per;              // steps a minute, for the facts
    phase = (phase + dt * rate / per) % 1;
    for (const k of ['walk', 'run']) {
      const a = actions['__' + k], c = C[k];
      if (!a || !c) continue;
      a.timeScale = 0;
      a.time = (c.contact + phase * c.period) % c.period;
    }
  }

  // ── the biomechanics, after the mixer has posed the clip ────────────────
  const _fw = new THREE.Vector3(), _lat = new THREE.Vector3();
  const _H = new THREE.Vector3(), _K = new THREE.Vector3(), _A = new THREE.Vector3(), _T = new THREE.Vector3();
  const _p = new THREE.Vector3(), _u = new THREE.Vector3(), _Kn = new THREE.Vector3(), _fq = new THREE.Quaternion();
  function legIK(s, target) {
    const up = B['upleg_' + s], lo = B['lowleg_' + s], ft = B['foot_' + s];
    ft.getWorldQuaternion(_fq);                          // the foot keeps its own angle
    wp(up, _H); wp(lo, _K); wp(ft, _A);
    const [L1, L2] = legLen[s];
    const d = _T.copy(target).sub(_H);
    const D = THREE.MathUtils.clamp(d.length(), Math.abs(L1 - L2) + 1e-3, (L1 + L2) * 0.995);
    _u.copy(d).normalize();
    // the knee bends in the plane it already bends in
    _p.copy(_K).sub(_H); _p.addScaledVector(_u, -_p.dot(_u));
    if (_p.lengthSq() < 1e-8) _p.copy(_fw); _p.normalize();
    const ca = THREE.MathUtils.clamp((L1 * L1 + D * D - L2 * L2) / (2 * L1 * D), -1, 1);
    _Kn.copy(_H).addScaledVector(_u, L1 * ca).addScaledVector(_p, L1 * Math.sqrt(1 - ca * ca));
    aimSegment(up, lo, _v1.copy(_Kn).sub(_H));
    wp(lo, _K);
    aimSegment(lo, ft, _v2.copy(_H).addScaledVector(_u, D).sub(_K));
    // restore the foot's world angle
    if (ft.parent) { ft.parent.getWorldQuaternion(_q3); _q3.invert(); ft.quaternion.copy(_q3.multiply(_fq)); ft.updateMatrixWorld(true); }
  }

  function post(dt, o) {
    // o: { speed, forward (world unit), moving 0..1, grounded, accel }
    const OFF = (typeof window !== 'undefined' && window.__gaitOff) || {};
    checkArmed(dt);
    const mvK = THREE.MathUtils.clamp(o.moving, 0, 1);
    _fw.copy(o.forward).setY(0).normalize();
    _lat.crossVectors(UP, _fw).normalize();             // anatomical left
    root.updateMatrixWorld(true);

    // THE MOCAP CARRIES THE BODY (2026-10-03). This used to correct the
    // trunk toward a target lean, level the head and drive the arms from the
    // legs, because the old aim retarget lost the source's own posture and
    // swing. The rotation-transfer retarget keeps them, so the overrides only
    // fought real motion ('too much lean', 'too robotic'). What is added now is
    // what a looping clip cannot know: the body leaning into a change of speed
    // and banking into a turn, each k*atan(a/g) with k 0.4 and a few degrees
    // at most, as the motion-matching references do it.
    const rk = st.runK;
    const g = 9.81;
    const aFwd = THREE.MathUtils.clamp(o.accel || 0, -12, 12);
    if (st.prevFw) {
      const turn = Math.atan2(st.prevFw.clone().cross(_fw).y, st.prevFw.dot(_fw));
      const yawRate = turn / Math.max(dt, 1e-3);
      st.aLat = THREE.MathUtils.damp(st.aLat || 0, THREE.MathUtils.clamp((o.speed || 0) * yawRate, -15, 15), 8, dt);
    } else st.aLat = 0;
    st.prevFw = (st.prevFw || new THREE.Vector3()).copy(_fw);
    const pitchT = THREE.MathUtils.clamp(0.4 * Math.atan(aFwd / g), -0.07, 0.1) * mvK;
    const rollT = THREE.MathUtils.clamp(0.4 * Math.atan(st.aLat / g), -0.1, 0.1) * mvK;
    st.lean = THREE.MathUtils.damp(st.lean, (typeof window !== 'undefined' && window.__gaitLean != null) ? window.__gaitLean : pitchT, 5, dt);
    st.bank = THREE.MathUtils.damp(st.bank || 0, rollT, 5, dt);
    if (!OFF.lean && (Math.abs(st.lean) > 1e-4 || Math.abs(st.bank) > 1e-4)) {
      // pitch about the body's left axis, roll about its forward axis (into
      // the turn: a left turn tips the body left)
      _q1.setFromAxisAngle(_lat, st.lean);
      _q3.setFromAxisAngle(_fw, -st.bank);
      _q1.multiply(_q3);
      rotateWorld(B.spine, _q1);
    }
    const top = B.chest || B.neck || B.head;
    if (top) {
      const tr = wp(top).sub(wp(B.hips));
      const cur = Math.atan2(tr.dot(_fw), tr.y);
      st.trunkAvg = st.trunkAvg === undefined ? cur : THREE.MathUtils.damp(st.trunkAvg, cur, 2.5, dt);
    }

    // THE LEGS (2026-10-02, second pass): one IK target per foot, built from
    //   stride warping - the foot's reach along travel scaled by the warp;
    //   the ground     - each foot reaches the terrain under it, and the
    //                    pelvis lowers so the downhill foot can (slopes);
    //   foot locking   - a planted foot is pinned where it landed until the
    //                    gait lifts it; standing or turning on the spot, a
    //                    pinned foot that falls too far behind where the body
    //                    wants it releases and takes a small lifted step
    //                    (stops and turns no longer slide or twist the feet)
    if (!OFF.ik && o.grounded !== false) {
      const w = 1 + (st.warp - 1) * mvK;
      const g0 = o.groundY !== undefined ? o.groundY : 0;
      const ga = (typeof o.groundAt === 'function') ? o.groundAt : null;
      // the terrain is only trusted where the body stands on it (not a floor,
      // a platform or a deck above it)
      const onTerrain = ga && Math.abs(ga(wp(B.hips).x, wp(B.hips).z) - g0) < 0.2;
      const T = {}, off = {}, stance = {};
      for (const s of ['l', 'r']) {
        wp(B['upleg_' + s], _H); wp(B['foot_' + s], _A);
        const along = _v3.copy(_A).sub(_H).dot(_fw);
        const t = _A.clone().addScaledVector(_fw, along * (w - 1));
        off[s] = onTerrain ? THREE.MathUtils.clamp(ga(t.x, t.z) - g0, -0.5, 0.5) : 0;
        t.y += off[s];
        T[s] = t;
        // stance: the foot near its lowest height over the ground this gait
        const fh = _A.y - g0;
        const fk = 'fmin_' + s;
        st[fk] = st[fk] === undefined ? fh : Math.min(fh, st[fk] + 0.05 * dt);
        stance[s] = fh < st[fk] + 0.04;
      }
      // the pelvis lowers by the deeper foot's drop, smoothly
      const drop = THREE.MathUtils.clamp(Math.min(0, off.l, off.r), -0.4, 0);
      st.pelvis = THREE.MathUtils.damp(st.pelvis || 0, drop, 10, dt);
      if (Math.abs(st.pelvis) > 1e-3 && B.hips.parent) {
        const hw = wp(B.hips); hw.y += st.pelvis;
        B.hips.parent.worldToLocal(hw);
        B.hips.position.copy(hw);
        B.hips.updateMatrixWorld(true);
      }
      const still = (o.speed || 0) < 0.35;
      for (const s of ['l', 'r']) {
        const L = st['lock_' + s] || (st['lock_' + s] = { pos: null, w: 0, rel: false });
        const t = T[s];
        if (stance[s] && !L.pos && !L.rel) { L.pos = t.clone(); L.w = 0; }
        if (L.pos) {
          const d = Math.hypot(t.x - L.pos.x, t.z - L.pos.z);
          if (!L.rel && (!stance[s] || d > (still ? 0.13 : 0.45))) L.rel = true;
          L.w = THREE.MathUtils.damp(L.w, L.rel ? 0 : 1, L.rel ? (still ? 9 : 16) : 28, dt);
          t.x = THREE.MathUtils.lerp(t.x, L.pos.x, L.w);
          t.z = THREE.MathUtils.lerp(t.z, L.pos.z, L.w);
          // a recovery step lifts the foot on its way to the new spot
          if (L.rel && still) t.y += Math.sin(Math.min(1, L.w) * Math.PI) * 0.07;
          if (L.rel && L.w < 0.03) { L.pos = null; L.rel = false; }
        } else if (L.rel) { L.rel = false; }
        legIK(s, t);
      }
    }
  }

  const _clipFwdLocal = (C.walk && C.walk.fwd.lengthSq() > 0.5) ? C.walk.fwd : (C.run ? C.run.fwd : null);
  const _rq = new THREE.Quaternion();
  return {
    drive, post, cycles: C,
    /** where the clips walk, in world space, given the model's current turn */
    clipForward(out) {
      if (!_clipFwdLocal) return null;
      root.getWorldQuaternion(_rq);
      return out.copy(_clipFwdLocal).applyQuaternion(_rq).setY(0).normalize();
    },
    facts: () => ({ phase: +phase.toFixed(3), rate: +st.rate.toFixed(2), warp: +st.warp.toFixed(2), lean_deg: +THREE.MathUtils.radToDeg(st.lean).toFixed(1), bank_deg: +THREE.MathUtils.radToDeg(st.bank || 0).toFixed(1), pelvis: +(st.pelvis || 0).toFixed(3), locks: [!!(st.lock_l && st.lock_l.pos), !!(st.lock_r && st.lock_r.pos)], trunk_deg: st.trunkAvg === undefined ? null : +THREE.MathUtils.radToDeg(st.trunkAvg).toFixed(1),
                    cadence_spm: Math.round(st.cadence), armed,
                    walk_period: C.walk ? +C.walk.period.toFixed(3) : null, run_period: C.run ? +C.run.period.toFixed(3) : null }),
  };
}
