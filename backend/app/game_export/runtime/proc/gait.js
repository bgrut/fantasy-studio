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
//   THE BODY OVER THE LEGS. The arms only ever swung behind the body; they
//   now counter-swing against the opposite leg (about 25 degrees each way in
//   a walk, driven with a 90-degree elbow in a run), the trunk leans forward
//   with speed (5 to 8 degrees in a run) and the head stays level.
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
    const rate = THREE.MathUtils.clamp(Math.sqrt(Math.max(ratio, 0.01)), 0.72, 1.35 + 0.1 * rk);
    st.rate = rate;
    st.warp = THREE.MathUtils.clamp(ratio / rate, 0.55, 1.95);
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

    // TRUNK LEAN, MEASURED: a walk stands nearly upright, a run leans 5-8
    // degrees forward, more while it accelerates. Clips disagree (the CMU jog
    // retargets reclined fifteen degrees), so the trunk's own lean is read,
    // averaged over about half a second so the stride's sway survives, and
    // only the difference to the target is applied; the head is held level.
    const rk = st.runK;
    const target = THREE.MathUtils.degToRad(1.5 + 4.5 * rk) * mvK + THREE.MathUtils.clamp(o.accel || 0, -3, 6) * 0.01;
    // the TRUNK is hips to chest: a head tipped back or forward must not
    // read as the whole body leaning
    const top = B.chest || B.neck || B.head;
    if (top) {
      const tr = wp(top).sub(wp(B.hips));
      const cur = Math.atan2(tr.dot(_fw), tr.y);
      st.trunkAvg = st.trunkAvg === undefined ? cur : THREE.MathUtils.damp(st.trunkAvg, cur, 2.5, dt);
    }
    const wantCorr = (typeof window !== 'undefined' && window.__gaitLean != null) ? window.__gaitLean
      : THREE.MathUtils.clamp(target - (st.trunkAvg || 0), -0.45, 0.45) * mvK;
    st.lean = THREE.MathUtils.damp(st.lean, wantCorr, 6, dt);
    if (!OFF.lean && Math.abs(st.lean) > 1e-4) {
      _q1.setFromAxisAngle(_lat, st.lean);
      rotateWorld(B.spine, _q1);
    }
    // THE HEAD STAYS LEVEL (LOCOMOTION.md: the head barely pitches in space
    // while walking or running): the neck-to-head line is measured after the
    // trunk has leant and turned back to a few degrees forward of vertical,
    // whatever the clip and the lean did to it
    if (!OFF.lean && B.head && mvK > 0.02) {
      // the skull's own axis (the head bone's +Y, up through the crown)
      B.head.getWorldQuaternion(_q2);
      const hv = _v3.set(0, 1, 0).applyQuaternion(_q2);
      const cur = Math.atan2(hv.dot(_fw), hv.y);
      const fix = THREE.MathUtils.clamp(THREE.MathUtils.degToRad(4) - cur, -0.6, 0.6) * mvK;
      st.headFix = THREE.MathUtils.damp(st.headFix || 0, fix, 10, dt);
      _q1.setFromAxisAngle(_lat, st.headFix);
      rotateWorld(B.head, _q1);
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

    // ARM SWING, AS MEASURED (2026-10-02, second pass). Each arm moves with
    // the OPPOSITE leg, but not by copying its angle: the thigh's swing is
    // normalised to -1..1 (its own running peak) and mapped onto a human
    // arm's range, which is asymmetric: the arm goes further BACK than
    // forward (walk about 17 forward / 24 back; jog 22 / 35). The elbow is
    // 20-35 degrees in a walk; in a jog about 70 at the back of the swing,
    // closing to about 90 in front, where the forearm also angles in toward
    // the body's midline, so the hands travel hip to mid-chest and never up
    // to the face. The upper arm stays against the torso (abduction under
    // about 7 degrees).
    if (!OFF.arms && hasArms && mvK > 0.02) {
      for (const [s, o2] of [['l', 'r'], ['r', 'l']]) {
        const th = wp(B['lowleg_' + o2]).sub(wp(B['upleg_' + o2]));
        const legAng = Math.atan2(th.dot(_fw), -th.y);           // + = that thigh forward
        st.legPk = Math.max(0.12, Math.abs(legAng), (st.legPk || 0.4) - 0.25 * dt);   // a peak that eases down over seconds
        const legN = THREE.MathUtils.clamp(legAng / st.legPk, -1, 1);
        const fwdMax = THREE.MathUtils.lerp(0.30, 0.40, rk), backMax = THREE.MathUtils.lerp(0.42, 0.68, rk);
        let armAng = legN > 0 ? legN * fwdMax : legN * backMax;
        if (armed[s]) armAng *= 0.4;
        const key = 'arm_' + s;
        st[key] = st[key] === undefined ? armAng : THREE.MathUtils.damp(st[key], armAng, 18, dt);
        armAng = st[key];
        st['dbg_' + s] = [+legN.toFixed(2), +armAng.toFixed(2)];
        const sh = wp(B['uparm_' + s]), el = wp(B['lowarm_' + s]);
        const cur = el.clone().sub(sh).normalize();
        const side = s === 'l' ? 1 : -1;
        let lat = cur.dot(_lat) * side;                           // outboard positive
        lat = THREE.MathUtils.clamp(lat, -0.03, 0.12);
        const r = Math.sqrt(1 - lat * lat);
        const want = _v1.copy(_lat).multiplyScalar(lat * side)
          .addScaledVector(_fw, r * Math.sin(armAng)).addScaledVector(UP, -r * Math.cos(armAng));
        aimSegment(B['uparm_' + s], B['lowarm_' + s], want, mvK);
        // the elbow, bent forward in the arm's swing plane
        const n = wp(B['lowarm_' + s]).sub(wp(B['uparm_' + s])).normalize();
        const front = (legN + 1) / 2;                             // 0 at the back of the swing, 1 in front
        const eWalk = 0.35 + 0.26 * Math.max(0, legN);
        const eRun = THREE.MathUtils.lerp(0.78, 1.3, front * front);    // ~45 deg behind, ~75 in front
        const e = armed[s] ? THREE.MathUtils.lerp(0.45, 0.8, rk) : THREE.MathUtils.lerp(eWalk, eRun, rk);
        const pf = _v2.copy(_fw).addScaledVector(n, -_fw.dot(n));
        if (pf.lengthSq() > 1e-6) {
          pf.normalize();
          const fdir = n.clone().multiplyScalar(Math.cos(e)).addScaledVector(pf, Math.sin(e));
          // in front of the body the forearm angles in toward the midline
          const inward = rk * 0.32 * Math.max(0, legN) * (armed[s] ? 0.3 : 1);
          fdir.addScaledVector(_lat, -side * inward).normalize();
          aimSegment(B['lowarm_' + s], B['hand_' + s], fdir, mvK);
        }
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
    facts: () => ({ phase: +phase.toFixed(3), rate: +st.rate.toFixed(2), warp: +st.warp.toFixed(2), lean_deg: +THREE.MathUtils.radToDeg(st.lean).toFixed(1), head_fix_deg: +THREE.MathUtils.radToDeg(st.headFix || 0).toFixed(1), pelvis: +(st.pelvis || 0).toFixed(3), locks: [!!(st.lock_l && st.lock_l.pos), !!(st.lock_r && st.lock_r.pos)], trunk_deg: st.trunkAvg === undefined ? null : +THREE.MathUtils.radToDeg(st.trunkAvg).toFixed(1),
                    cadence_spm: Math.round(st.cadence), armed, dbg: [st.dbg_l, st.dbg_r, +(st.legPk || 0).toFixed(2)],
                    walk_period: C.walk ? +C.walk.period.toFixed(3) : null, run_period: C.run ? +C.run.period.toFixed(3) : null }),
  };
}
