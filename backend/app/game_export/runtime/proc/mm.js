// MOTION MATCHING (2026-10-03)
// ---------------------------------------------------------------------------
// The way Fortnite and The Last of Us move people (Clavet and Zadziuk, GDC
// 2016; the method follows Daniel Holden's MIT reference implementation,
// orangeduck/Motion-Matching). Instead of one walk loop and one run loop bent
// to fit, the hero plays real captured motion from a database of starts,
// stops, turns, jogs and sprints (tools/mmdb.py builds it from CMU and
// 100STYLE). Ten times a second the runtime asks which frame in all of it has
// feet moving like the hero's feet now AND is about to go where the player is
// steering (the body's path 1/3, 2/3 and 1 s ahead, and which way it will
// face), and jumps there. A jump never pops: the difference between the last
// pose shown and the new one is carried as an offset that decays away with a
// tenth of a second half-life (inertialization, Bollo GDC 2018).
//
// The database is one set of motion for every character. Each frame stores
// every bone's world rotation against a canonical T-pose; on load each rig is
// calibrated once (its bind-pose rotation per bone and the minimal turn from
// the canonical bone direction onto its own), and a frame is put on the rig as
// W_target = W_db . C^-1 . R_rest, the rotation transfer the bake uses.
import * as THREE from 'three';

const UP = new THREE.Vector3(0, 1, 0);
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _q3 = new THREE.Quaternion();
const _v = new THREE.Vector3(), _v2 = new THREE.Vector3();

function half(h) {                          // IEEE half -> float
  const s = (h & 0x8000) ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
  if (e === 0) return s * Math.pow(2, -14) * (f / 1024);
  if (e === 31) return f ? NaN : s * Infinity;
  return s * Math.pow(2, e - 15) * (1 + f / 1024);
}

export async function loadMotionDB(base) {
  const [head, buf] = await Promise.all([
    fetch(base + 'mm_db.json').then(r => { if (!r.ok) throw new Error('mm_db.json ' + r.status); return r.json(); }),
    fetch(base + 'mm_db.bin').then(r => { if (!r.ok) throw new Error('mm_db.bin ' + r.status); return r.arrayBuffer(); }),
  ]);
  const F = head.frames, NB = head.bones.length, L = head.layout;
  const rot = new Int16Array(buf, 0, F * NB * 4);
  const hips = new Int16Array(buf, L.hips_i16, F * 3);
  const fh = new Uint16Array(buf, L.feat_f16, F * 27);
  const con = new Uint8Array(buf, L.contact_u8, F);
  const lean = L.lean_i8 !== undefined ? new Int8Array(buf, L.lean_i8, F) : null;   // trunk lean per frame, degrees
  const w = head.feature.weight;
  const featW = new Float32Array(F * 27);          // normalised features times their weights
  for (let i = 0; i < F * 27; i++) featW[i] = half(fh[i]) * w[i % 27];
  // which range each frame is in, and whether a search may land there: a
  // frame needs a few frames of its take left to play (its future path is
  // carried past the take's end by the builder)
  const rangeOf = new Int32Array(F), valid = new Uint8Array(F);
  head.ranges.forEach(([a, e], r) => {
    for (let i = a; i < e; i++) { rangeOf[i] = r; valid[i] = i + 6 < e ? 1 : 0; }
  });
  return { head, F, NB, rot, hips, featW, con, lean, rangeOf, valid, ranges: head.ranges };
}

// the child that gives each bone its direction (leaves use their own +Y)
const CHILD = { hips: 'spine', spine: 'chest', chest: 'neck', neck: 'head',
  clav_l: 'uparm_l', uparm_l: 'lowarm_l', lowarm_l: 'hand_l', lowarm_tw_l: 'hand_l',
  clav_r: 'uparm_r', uparm_r: 'lowarm_r', lowarm_r: 'hand_r', lowarm_tw_r: 'hand_r',
  upleg_l: 'lowleg_l', lowleg_l: 'foot_l', upleg_r: 'lowleg_r', lowleg_r: 'foot_r' };

export function createMotionMatcher({ root, db, halflife = 0.1, searchEvery = 0.1 }) {
  let sk = null;
  root.traverse(o => { if (!sk && o.isSkinnedMesh && o.skeleton) sk = o.skeleton; });
  if (!sk || !db) return null;
  const B = {};
  for (const b of sk.bones) B[b.name.toLowerCase()] = b;
  const names = db.head.bones.map(n => n.toLowerCase());
  if (!['hips', 'upleg_l', 'lowleg_l', 'foot_l', 'upleg_r', 'lowleg_r', 'foot_r'].every(n => B[n])) return null;
  // the rig's bones that take a track: the stored ones, plus each forearm
  // twist bone reading its forearm's track
  const tracks = [];
  for (const [i, n] of names.entries()) if (B[n]) tracks.push({ name: n, bone: B[n], src: i });
  for (const s of ['l', 'r']) if (B['lowarm_tw_' + s] && names.includes('lowarm_' + s))
    tracks.push({ name: 'lowarm_tw_' + s, bone: B['lowarm_tw_' + s], src: names.indexOf('lowarm_' + s) });
  const depth = b => { let d = 0; for (let p = b.parent; p; p = p.parent) d++; return d; };
  tracks.sort((a, b) => depth(a.bone) - depth(b.bone));
  const byBone = new Map(tracks.map(t => [t.bone, t]));

  // ── calibration, in the bind pose ─────────────────────────────────────────
  // character space: the model's own frame turned so its front is +Z (the
  // runtime authors fronts on -Z), its left +X, as the database is
  const keep = sk.bones.map(b => [b.position.clone(), b.quaternion.clone(), b.scale.clone()]);
  sk.pose();
  root.updateMatrixWorld(true);
  const rootQ = root.getWorldQuaternion(new THREE.Quaternion());
  const rootP = root.getWorldPosition(new THREE.Vector3());
  const Ypi = new THREE.Quaternion().setFromAxisAngle(UP, Math.PI);
  const toChar = new THREE.Quaternion().copy(Ypi).multiply(rootQ.clone().invert());   // world -> char
  const restDirs = db.head.rest_dirs;
  const dirDbg = [];
  for (const t of tracks) {
    const bw = t.bone.getWorldQuaternion(new THREE.Quaternion());
    const Rt = toChar.clone().multiply(bw);
    let dt;
    const c = CHILD[t.name] && B[CHILD[t.name]];
    if (c) dt = c.getWorldPosition(new THREE.Vector3()).sub(t.bone.getWorldPosition(new THREE.Vector3()));
    else dt = new THREE.Vector3(0, 1, 0).applyQuaternion(bw);
    dt.applyQuaternion(toChar).normalize();
    const key = db.head.bones[t.src];
    const dc = new THREE.Vector3().fromArray(restDirs[key]).normalize();
    const C = new THREE.Quaternion().setFromUnitVectors(dc, dt);
    t.K = C.invert().multiply(Rt);                      // W_target = W_db . C^-1 . R_rest
    if (c) { const y = new THREE.Vector3(0, 1, 0).applyQuaternion(bw).applyQuaternion(toChar); dirDbg.push([t.name, +(y.angleTo(dt) * 57.3).toFixed(0)]); }
  }
  // the rig's scale against the database's 0.87 m legs, and where its hips rest
  const legLen = B.upleg_l.getWorldPosition(new THREE.Vector3()).distanceTo(B.lowleg_l.getWorldPosition(new THREE.Vector3()))
    + B.lowleg_l.getWorldPosition(new THREE.Vector3()).distanceTo(B.foot_l.getWorldPosition(new THREE.Vector3()));
  const scale = legLen / (db.head.leg || 0.87);
  const ankleRest = B.foot_l.getWorldPosition(new THREE.Vector3()).sub(rootP).applyQuaternion(toChar).y;
  sk.bones.forEach((b, i) => { b.position.copy(keep[i][0]); b.quaternion.copy(keep[i][1]); b.scale.copy(keep[i][2]); });
  root.updateMatrixWorld(true);

  // ── state ────────────────────────────────────────────────────────────────
  const st = { frame: db.ranges[0][0], range: 0, timer: 0, rate: 1, jumps: 0, lastCost: 0, searchMs: 0,
               off: tracks.map(() => new THREE.Quaternion()), offHips: new THREE.Vector3(),
               last: tracks.map(() => new THREE.Quaternion()), lastHips: new THREE.Vector3(), hasLast: false,
               pending: false, prevWant: new THREE.Vector3() };
  // start on a standing frame: the first frame of the idle take
  const lam = Math.LN2 / Math.max(1e-3, halflife);
  const NB = db.NB;
  const qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
  const outQ = tracks.map(() => new THREE.Quaternion());
  const outHips = new THREE.Vector3();
  const _pw = new THREE.Quaternion(), _wq = new THREE.Quaternion(), _rootQ = new THREE.Quaternion(), _rootP = new THREE.Vector3();
  const worldQ = new Map();

  function dbRot(i, b, out) {
    const o = (i * NB + b) * 4, r = db.rot;
    return out.set(r[o] / 32767, r[o + 1] / 32767, r[o + 2] / 32767, r[o + 3] / 32767).normalize();
  }
  // the pose of a (fractional) database frame, as local bone rotations and a
  // hips position in the model's space
  function sample(frame) {
    const r = db.rangeOf[Math.floor(frame)], end = db.ranges[r][1] - 1;
    const i0 = Math.min(Math.floor(frame), end), i1 = Math.min(i0 + 1, end), a = frame - Math.floor(frame);
    root.updateMatrixWorld(true);
    root.getWorldQuaternion(_rootQ); root.getWorldPosition(_rootP);
    const fromChar = _rootQ.clone().multiply(Ypi.clone().invert());      // char -> world
    worldQ.clear();
    tracks.forEach((t, k) => {
      dbRot(i0, t.src, qa); dbRot(i1, t.src, qb);
      if (qa.dot(qb) < 0) qb.set(-qb.x, -qb.y, -qb.z, -qb.w);
      qa.slerp(qb, a);
      _wq.copy(fromChar).multiply(qa).multiply(t.K);                      // world rotation of this bone
      worldQ.set(t.bone, _wq.clone());
      const p = t.bone.parent;
      if (p && worldQ.has(p)) _pw.copy(worldQ.get(p)); else if (p) p.getWorldQuaternion(_pw); else _pw.identity();
      outQ[k].copy(_pw.invert()).multiply(_wq);
    });
    // hips: the database's offset over the root, scaled to this rig
    const h = db.hips;
    const hx = THREE.MathUtils.lerp(h[i0 * 3] / 1e4, h[i1 * 3] / 1e4, a);
    const hy = THREE.MathUtils.lerp(h[i0 * 3 + 1] / 1e4, h[i1 * 3 + 1] / 1e4, a);
    const hz = THREE.MathUtils.lerp(h[i0 * 3 + 2] / 1e4, h[i1 * 3 + 2] / 1e4, a);
    // the database floor sits 8 cm under its ankles; ours sits ankleRest under ours
    _v.set(hx * scale, (hy - 0.08) * scale + ankleRest, hz * scale).applyQuaternion(fromChar).add(_rootP);
    if (B.hips.parent) B.hips.parent.worldToLocal(_v);
    outHips.copy(_v);
  }

  // ── the search ───────────────────────────────────────────────────────────
  const q = new Float32Array(27);
  const mean = db.head.feature.mean, std = db.head.feature.std, wt = db.head.feature.weight;
  function query(ctl) {
    const cur = Math.min(Math.floor(st.frame), db.F - 1);
    for (let i = 0; i < 15; i++) q[i] = db.featW[cur * 27 + i];             // the pose part: the frame playing now
    const y0 = ctl.yaw, cy = Math.cos(y0), sy = Math.sin(y0);
    // THE HIPS MOVE AS FAST AS THE BODY DOES (2026-10-03). Holden's
    // character is carried by its animation, so the playing frame's hip
    // velocity is the body's; here the game carries the body, and a query
    // that kept the frame's own hip velocity kept a run start's pace while
    // the hero strolled at 1.4 m/s (it played jog starts, leaning 17
    // degrees). The hips' part of the query is the body's real velocity.
    {
      const s = 1 / scale, vx = ctl.vel.x * cy - ctl.vel.z * sy, vz = ctl.vel.x * sy + ctl.vel.z * cy;
      const hv = [vx * s, 0, vz * s];
      for (let c = 0; c < 3; c++) {
        const i = 12 + c;
        if (c !== 1) q[i] = (hv[c] - mean[i]) / std[i] * wt[i];
      }
    }
    // the trajectory part: where the controller will carry the body
    const k = Math.max(0.5, ctl.velRate || 8), tk = Math.max(0.5, ctl.turnRate || 10);
    const v0 = ctl.vel, vw = ctl.wantVel;
    let dy = ctl.wantYaw - y0; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    [1 / 3, 2 / 3, 1].forEach((t, n) => {
      const e = Math.exp(-k * t), g = (1 - e) / k;
      const px = vw.x * t + (v0.x - vw.x) * g, pz = vw.z * t + (v0.z - vw.z) * g;
      const lx = px * cy - pz * sy, lz = px * sy + pz * cy;               // into the body's frame
      const yt = dy * (1 - Math.exp(-tk * t));
      const fx = Math.sin(yt), fz = Math.cos(yt);
      const s = 1 / scale;                                                // the database is 0.87 m legs
      const vals = [lx * s, lz * s], dirs = [fx, fz];
      for (let c = 0; c < 2; c++) {
        const ip = 15 + n * 2 + c, id = 21 + n * 2 + c;
        q[ip] = (vals[c] - mean[ip]) / std[ip] * wt[ip];
        q[id] = (dirs[c] - mean[id]) / std[id] * wt[id];
      }
    });
  }
  function costAt(i) {
    let c = 0; const o = i * 27, f = db.featW;
    for (let j = 0; j < 27; j++) { const d = q[j] - f[o + j]; c += d * d; }
    return c;
  }
  // A LEAN THE SPEED CAN CARRY (2026-10-03): the features describe feet and
  // path, not posture, so a jog-off after a stop played an athlete's
  // explosive restart, 22 degrees over. A frame is a candidate only if its
  // trunk lean fits the pace: 10 degrees standing, 3 more per m/s.
  let leanMax = 99;
  function search(force) {
    const t0 = performance.now();
    const cur = Math.floor(st.frame);
    const L = db.lean;
    let curCost = (!force && db.valid[cur]) ? costAt(cur) : Infinity;
    if (L && L[cur] > leanMax) curCost = Infinity;
    let best = -1, bestCost = curCost;
    const f = db.featW, F = db.F, v = db.valid;
    for (let i = 0; i < F; i++) {
      if (!v[i] || (L && L[i] > leanMax)) continue;
      let c = 0; const o = i * 27;
      for (let j = 0; j < 27 && c < bestCost; j++) { const d = q[j] - f[o + j]; c += d * d; }
      if (c < bestCost) { bestCost = c; best = i; }
    }
    st.searchMs = performance.now() - t0;
    st.lastCost = Math.min(bestCost, curCost);
    if (best < 0) return;
    // a jump of a few frames inside the take it is already playing is no jump,
    // and a jump must be worth it: a better match by a clear margin, or the
    // pose flickers between near-equal frames ten times a second
    if (!force && db.rangeOf[best] === db.rangeOf[cur] && Math.abs(best - cur) < 4) return;
    if (!force && curCost < Infinity && bestCost > curCost * 0.85 - 0.05) return;
    st.frame = best; st.range = db.rangeOf[best]; st.pending = true; st.jumps++;
  }

  // ── inertialization ──────────────────────────────────────────────────────
  // offsets = what was shown last ⊗ inverse(what is shown now), decayed
  function inertialize() {
    if (!st.hasLast) return;
    tracks.forEach((t, k) => {
      _q.copy(outQ[k]).invert();
      st.off[k].copy(st.last[k]).multiply(_q);
      if (st.off[k].w < 0) st.off[k].set(-st.off[k].x, -st.off[k].y, -st.off[k].z, -st.off[k].w);
    });
    st.offHips.copy(st.lastHips).sub(outHips);
  }
  function write(dt) {
    const d = Math.exp(-lam * dt);
    tracks.forEach((t, k) => {
      st.off[k].slerp(_q2.identity(), 1 - d);
      t.bone.quaternion.copy(st.off[k]).multiply(outQ[k]);
      st.last[k].copy(t.bone.quaternion);
    });
    st.offHips.multiplyScalar(d);
    B.hips.position.copy(outHips).add(st.offHips);
    st.lastHips.copy(B.hips.position);
    st.hasLast = true;
    root.updateMatrixWorld(true);
  }

  return {
    calibration: { scale: +scale.toFixed(3), legLen: +legLen.toFixed(3), tracks: tracks.length, dirs: dirDbg },
    /** ctl: { vel, wantVel (world Vector3, m/s), yaw, wantYaw (rad), velRate, turnRate (1/s) } */
    update(dt, ctl) {
      // the clock: one database frame per 1/30 s, a little faster or slower
      // so the actor's pace meets the body's (within what reads as natural)
      const cur = Math.floor(st.frame);
      const fx = db.featW[cur * 27 + 15] / wt[15] * std[15] + mean[15], fz = db.featW[cur * 27 + 16] / wt[16] * std[16] + mean[16];
      const animV = Math.hypot(fx, fz) * 3 * scale;                       // root speed, from 1/3 s ahead
      const bodyV = Math.hypot(ctl.vel.x, ctl.vel.z);
      const want = (animV > 0.3 && bodyV > 0.3) ? THREE.MathUtils.clamp(bodyV / animV, 0.8, 1.3) : 1;
      st.rate = THREE.MathUtils.damp(st.rate, want, 6, dt);
      st.frame += dt * db.head.fps * st.rate;
      const end = db.ranges[st.range][1];
      let force = false;
      if (st.frame >= end - 1) { st.frame = end - 1.001; force = true; }
      // a sharp change of the player's wish searches at once
      _v2.copy(ctl.wantVel).sub(st.prevWant);
      if (_v2.length() > 0.8) { st.timer = 0; st.prevWant.copy(ctl.wantVel); }
      st.timer -= dt;
      if (st.timer <= 0 || force) {
        st.timer = searchEvery;
        const sp = Math.max(Math.hypot(ctl.wantVel.x, ctl.wantVel.z), Math.hypot(ctl.vel.x, ctl.vel.z)) / scale;
        leanMax = 10 + 3 * sp;
        query(ctl);
        search(force);
      }
      sample(st.frame);
      if (st.pending) { inertialize(); st.pending = false; }
      write(dt);
    },
    /** another pose source (an attack clip) has just posed the bones: blend
     *  from what was shown into it, then call overlay(dt) each frame it plays */
    handoff() {
      if (!st.hasLast) return;
      tracks.forEach((t, k) => { outQ[k].copy(t.bone.quaternion); });
      outHips.copy(B.hips.position);
      inertialize();
    },
    overlay(dt) {
      tracks.forEach((t, k) => { outQ[k].copy(t.bone.quaternion); });
      outHips.copy(B.hips.position);
      write(dt);
    },
    /** motion matching takes the bones back: search now, blend from what was shown */
    resume() { st.timer = 0; st.pending = true; },
    /** contacts of the frame playing: [left planted, right planted] */
    contacts() { const c = db.con[Math.floor(st.frame)]; return [!!(c & 1), !!(c & 2)]; },
    facts: () => ({ frame: Math.floor(st.frame), take: (db.head.takes[st.range] || {}).take, label: (db.head.takes[st.range] || {}).label,
                    rate: +st.rate.toFixed(2), jumps: st.jumps, cost: +st.lastCost.toFixed(3), search_ms: +st.searchMs.toFixed(2) }),
  };
}
