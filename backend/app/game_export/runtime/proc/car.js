// CARS THAT ARE CARS (2026-10-01). The owner called the cars blocky, and
// they were: a profile extruded sideways is a slab with a lid, whatever the
// curve on its side, and the cabin was a glass box under a flat roof plate.
// A car's body is one skin. Here it is LOFTED: forty cross-sections from
// nose to tail, each a rounded superellipse whose width, height, roundness
// and tumblehome follow the car's own lines (bonnet, windscreen, roof,
// backlight, boot), with the wheel arches lifted out of the sill. The glass
// is the same skin, the faces that lie in the greenhouse, flush with the
// paint, framed by pillars that are the skin too. Wheels are turned, not
// stacked: a tyre with a rounded sidewall, a dished rim with spokes, a
// brake disc behind.
//
// Convention (the runtime's, unchanged): length on X with the NOSE AT +X,
// Y up, width on Z, wheels on the ground at y = 0. Same presets as before.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from '../vendor/jsm/utils/BufferGeometryUtils.js';

const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const lerp = (a, b, t) => a + (b - a) * t;

// a monotone cubic through [t, v] points
function curve(pts) {
  return (t) => {
    if (t <= pts[0][0]) return pts[0][1];
    for (let i = 0; i < pts.length - 1; i++) {
      const [t0, v0] = pts[i], [t1, v1] = pts[i + 1];
      if (t <= t1) {
        const u = (t - t0) / (t1 - t0);
        const m0 = i > 0 ? (v1 - pts[i - 1][1]) / (t1 - pts[i - 1][0]) * (t1 - t0) : (v1 - v0);
        const m1 = i < pts.length - 2 ? (pts[i + 2][1] - v0) / (pts[i + 2][0] - t0) * (t1 - t0) : (v1 - v0);
        const u2 = u * u, u3 = u2 * u;
        return (2 * u3 - 3 * u2 + 1) * v0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * v1 + (u3 - u2) * m1;
      }
    }
    return pts[pts.length - 1][1];
  };
}

function hashPaint(p) { return ((p * 2654435761) >>> 0) % 1000 / 1000; }

export function buildCarHQ(cp, T = {}) {
  const g = new THREE.Group();
  const L = cp.length || T.length || 4.4, Wd = cp.width || T.width || 1.85;
  const bodyH = cp.bodyH || T.bodyH || 0.62, bodyY = cp.bodyY || T.bodyY || 0.52;
  // a greenhouse runs from the base of the A pillar to the C pillar: longer
  // than the presets' old cabin boxes, which read as a phone booth on a deck
  const cabLen = (cp.cabinLen || T.cabinLen || 0.46) * 1.22, cabH = cp.cabinH || T.cabinH || 0.52;
  const cabX = cp.cabinX !== undefined ? cp.cabinX : (T.cabinX !== undefined ? T.cabinX : -0.04);
  const wr = cp.wheelR || T.wheelR || 0.34;
  const wb = cp.wheelBase || T.wheelBase || 0.31;
  const paintHex = cp.paint || 0xb5202a;
  const wear = 0.25 + hashPaint(paintHex) * 0.75;
  const paint = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(paintHex), metalness: 0.28,
    roughness: 0.22 + wear * 0.36, clearcoat: 1.0 - wear * 0.45,
    clearcoatRoughness: 0.03 + wear * 0.22, envMapIntensity: 1.15 - wear * 0.5 });
  // TINTED, NOT PAINTED (2026-10-02): the glass was an opaque black mirror,
  // so every car was a shell with nobody in it. It is tinted glass now, and
  // there is a cabin behind it.
  const glass = new THREE.MeshPhysicalMaterial({
    color: 0x1a222c, metalness: 0.1, roughness: 0.04, clearcoat: 1.0, clearcoatRoughness: 0.02,
    envMapIntensity: 1.3, transparent: true, opacity: 0.62, depthWrite: false });
  const black = new THREE.MeshStandardMaterial({ color: 0x0d0e10, roughness: 0.55, metalness: 0.2 });
  const chrome = new THREE.MeshStandardMaterial({ color: 0xd2d6dc, metalness: 0.95, roughness: 0.16 });

  // ── the car's lines, t = 0 nose .. 1 tail ─────────────────────────────
  const yb = Math.max(0.16, bodyY - bodyH * 0.5);     // sill
  const yt = yb + bodyH;                              // beltline
  const cabF = Math.min(Math.max(0.5 - cabX - cabLen * 0.5, 0.30), 0.60);
  const cabR = Math.min(cabF + cabLen, 0.92);
  const rake = Math.min(0.2, cabLen * 0.42);          // how far the windscreen leans
  const wsTop = Math.min(cabF + rake, cabR - 0.08);
  const blTop = Math.max(cabR - rake * 0.75, wsTop + 0.06);
  const roofY = yt + cabH;
  const tall = bodyH > 0.95;                          // vans and box trucks: square shoulders
  // the top line: bumper, bonnet, cowl, screen, roof, backlight, deck, tail
  const top = curve([
    [0.0, yb + bodyH * 0.45], [0.03, yt - bodyH * 0.18], [0.12, yt - 0.06], [cabF * 0.98, yt],
    [wsTop, roofY], [lerp(wsTop, blTop, 0.5), roofY + 0.03], [blTop, roofY],
    [Math.min(cabR + 0.02, 0.95), yt + 0.02], [0.96, yt + 0.03], [1.0, yb + bodyH * 0.62],
  ]);
  // half-width in plan: drawn in at both ends
  const half = (t) => Wd * 0.5 * (1 - 0.13 * (1 - smooth(0, 0.16, t)) - 0.09 * (1 - smooth(1.0, 0.86, t)));
  const xAt = (t) => L * 0.5 - t * L;
  // the sill, lifted over each wheel into an arch
  // wheelBase is the HALF-distance from the middle, as the extruded build has
  // always read it (wheels at 0.5 -/+ wb). Read here as distance from the
  // nose, it put the axles at 31% and 69% of the length: a wheelbase of 38%
  // with overhangs like a parade float, which was most of the toy look.
  const aF = 0.5 - wb, aR = 0.5 + wb;
  const archR = wr * 1.12;
  const bottom = (t) => {
    let y = yb;
    for (const a of [aF, aR]) {
      const dx = Math.abs(t - a) * L;
      if (dx < archR) y = Math.max(y, Math.min(wr + Math.sqrt(archR * archR - dx * dx) * 0.86, yb + bodyH * 0.72));
    }
    // the nose and tail tuck up a little
    y += 0.05 * (1 - smooth(0, 0.06, t)) + 0.04 * (1 - smooth(1, 0.95, t));
    return y;
  };

  // ── loft ──────────────────────────────────────────────────────────────
  // A car's section is not a blob: from the centreline of the roof (or the
  // bonnet) it crowns out to the roof's edge, falls inboard down the side
  // glass to the beltline, steps OUT over a shoulder crease, runs down a
  // near-vertical flank and tucks under at the rocker. Each of those
  // landmarks sits on a fixed index around every section, so the glass, the
  // roof and the frame are bands of the skin with clean edges, and a crease
  // stays a crease from nose to tail.
  const NS = 96;
  // segment lengths (points) between landmarks, centre-top -> centre-bottom
  const SEG = [5, 3, 7, 2, 2, 7, 3, 4];
  const K = [0]; for (const n of SEG) K.push(K[K.length - 1] + n);
  const HALF = K[K.length - 1];               // points on one half, top to bottom
  const NR = HALF * 2;                         // around the whole section
  const kRoofEdge = K[1], kGlassTop = K[2], kBelt = K[3], kCrease = K[4];
  const cabSpan = (t) => smooth(cabF - 0.01, cabF + 0.03, t) * (1 - smooth(cabR - 0.03, cabR + 0.02, t));
  // the ends are rounded in every direction: within the last few percent of
  // its length a car closes toward its centre, not as a flat wall
  const endRound = (t) => {
    const f = t < 0.5 ? Math.min(1, t / 0.035) : Math.min(1, (1 - t) / 0.03);
    return Math.sqrt(Math.max(0, 1 - (1 - f) * (1 - f)));
  };
  function section(t) {
    const e = endRound(t);
    const yBot0 = bottom(t), yTop0 = top(t);
    const yMid = lerp(yBot0, yTop0, 0.45);
    const yTop = lerp(yMid, yTop0, 0.35 + 0.65 * e), yBot = lerp(yMid, yBot0, 0.5 + 0.5 * e);
    const hw = half(t) * (0.62 + 0.38 * e);
    const c = cabSpan(t);                     // 1 under the greenhouse
    const belt = Math.min(yt, yTop - 0.01);
    const wBody = hw;
    const wBelt = hw * (tall ? 0.97 : 0.93);
    const wRoof = lerp(wBelt, hw * (tall ? 0.9 : 0.8), c);
    const crown = 0.035 + 0.02 * c;
    // landmarks (z, y), half section
    const L0 = [0, yTop];
    const L1 = [wRoof * 0.72, yTop - crown * 0.6];
    const L2 = [wRoof, yTop - crown - 0.05 * c];
    const L3 = [lerp(wBelt * 0.985, wBelt, c), lerp(Math.max(belt, yTop - crown - 0.07), belt, c)];
    const L4 = [wBody, belt - 0.05];
    const L5 = [wBody * 0.995, lerp(belt - 0.05, yBot, 0.55)];
    const L6 = [wBody * 0.96, yBot + 0.07];
    const L7 = [wBody * 0.84, yBot];
    const L8 = [0, yBot + 0.01];
    const LM = [L0, L1, L2, L3, L4, L5, L6, L7, L8];
    const out = [];
    for (let s = 0; s < SEG.length; s++) {
      const p0 = LM[Math.max(0, s - 1)], p1 = LM[s], p2 = LM[s + 1], p3 = LM[Math.min(LM.length - 1, s + 2)];
      for (let j = 0; j < SEG[s]; j++) {
        const u = j / SEG[s], u2 = u * u, u3 = u2 * u;
        // Catmull-Rom through the landmarks; the crease segments stay tight
        const tight = (s === 3) ? 0.0 : 0.5;
        const m1 = [(p2[0] - p0[0]) * tight, (p2[1] - p0[1]) * tight];
        const m2 = [(p3[0] - p1[0]) * tight, (p3[1] - p1[1]) * tight];
        const h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u, h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
        out.push([h00 * p1[0] + h10 * m1[0] + h01 * p2[0] + h11 * m2[0],
                  h00 * p1[1] + h10 * m1[1] + h01 * p2[1] + h11 * m2[1]]);
      }
    }
    out.push(L8);
    return out;                                // HALF + 1 points, top centre to bottom centre
  }
  const ring = [];
  for (let i = 0; i <= NS; i++) {
    const t = i / NS, x = xAt(t);
    const hs = section(t);
    const r = [];
    // one side (z > 0) top to bottom, then the other side bottom to top
    for (let k = 0; k < HALF; k++) r.push(new THREE.Vector3(x, hs[k][1], hs[k][0]));
    for (let k = HALF; k > 0; k--) r.push(new THREE.Vector3(x, hs[k][1], -hs[k][0]));
    ring.push(r);
  }
  const pos = [], uv = [];
  for (let i = 0; i <= NS; i++) for (let k = 0; k <= NR; k++) {
    const p = ring[i][k % NR];
    pos.push(p.x, p.y, p.z);
    uv.push(i / NS, k / NR);
  }
  const row = NR + 1;
  // the bands: which index range around the section is which surface
  const tB = lerp(cabF, cabR, 0.52);
  const quads = [[], [], []];                  // paint, glass, black frame
  const sideIdx = (k) => (k < HALF ? k : NR - k);   // distance from the top centre, either side
  for (let i = 0; i < NS; i++) for (let k = 0; k < NR; k++) {
    const a = i * row + k, b = a + row;
    const t = (i + 0.5) / NS;
    const kk = sideIdx(k + 0.5);
    let gI = 0;
    const inCab = t > cabF + 0.012 && t < cabR - 0.004;
    if (inCab) {
      const onTop = kk < kRoofEdge;
      const onSide = kk > kGlassTop - 1 && kk < kBelt;
      const upperEdge = kk >= kRoofEdge && kk <= kGlassTop - 1;
      if (onTop) {
        // the top band is glass where it is the windscreen or the backlight
        if (t < wsTop - 0.005 || t > blTop + 0.005) gI = 1;
      } else if (upperEdge) {
        gI = (t < wsTop - 0.005 || t > blTop + 0.005) ? 1 : 2;   // drip rail, black
      } else if (onSide) {
        const pillar = Math.abs(t - tB) < 0.012 && L > 3.9;
        gI = pillar ? 2 : 1;
      }
      // the A and C pillars: a narrow band of paint where screen meets side
      if ((onSide || upperEdge) && (Math.abs(t - wsTop) < 0.012 || Math.abs(t - blTop) < 0.012)) gI = 0;
    }
    quads[gI].push(a, b, a + 1, a + 1, b, b + 1);
  }
  // the end caps join the body's paint (one draw, not three): a fan from the
  // section's centre, facing +X at the nose and -X at the tail
  for (const i of [0, NS]) {
    const c = ring[i].reduce((s, p) => s.add(p), new THREE.Vector3()).multiplyScalar(1 / NR);
    const ci = pos.length / 3;
    pos.push(c.x, c.y, c.z); uv.push(i / NS, 0.5);
    for (let k = 0; k < NR; k++) {
      const p1 = i * row + k, p2 = i * row + k + 1;
      if (i === 0) quads[0].push(ci, p1, p2); else quads[0].push(ci, p2, p1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  const all = quads[0].concat(quads[1], quads[2]);
  geo.setIndex(all);
  geo.addGroup(0, quads[0].length, 0);
  geo.addGroup(quads[0].length, quads[1].length, 1);
  geo.addGroup(quads[0].length + quads[1].length, quads[2].length, 2);
  geo.computeVertexNormals();
  // SHUT LINES (2026-10-02): a body with no seams reads as a toy cast in one
  // piece. The doors, bonnet and boot lid are drawn as fine dark cuts into
  // the paint's own map (u runs nose to tail, v around the section), with a
  // handle on each door, so the shell reads as panels that open.
  if (typeof document !== 'undefined') {
    const cv = document.createElement('canvas'); cv.width = 2048; cv.height = 512;
    const x2 = cv.getContext('2d');
    x2.fillStyle = '#ffffff'; x2.fillRect(0, 0, cv.width, cv.height);
    x2.strokeStyle = 'rgba(0,0,0,0.75)'; x2.lineWidth = 2.2;
    const U = (t) => t * cv.width, V = (k) => (k / NR) * cv.height;
    const kSill = K[6];
    const sides = [[kBelt, kSill], [NR - kSill, NR - kBelt]];
    const doorCuts = [cabF + 0.012, cabR - 0.03];
    if (L > 3.9 && !T.bed) doorCuts.splice(1, 0, tB);
    for (const [k0, k1] of sides) {
      for (const t of doorCuts) { x2.beginPath(); x2.moveTo(U(t), V(k0) + 3); x2.lineTo(U(t), V(k1) - 2); x2.stroke(); }
      // handles: a short dark slot behind each door's leading edge, just under the crease
      x2.fillStyle = 'rgba(0,0,0,0.6)';
      const kh = lerp(k0, k1, k0 < NR / 2 ? 0.16 : 0.84);
      const doors = doorCuts.length - 1;
      for (let d = 0; d < doors; d++) {
        const t = lerp(doorCuts[d], doorCuts[d + 1], 0.78);
        x2.fillRect(U(t) - 22, V(kh) - 3, 44, 6);
      }
    }
    // the bonnet and boot lids: across the top, short of the wings
    for (const t of [Math.max(0.045, cabF - 0.03), Math.min(0.955, cabR + 0.03)]) {
      for (const [k0, k1] of [[0, kBelt - 1], [NR - kBelt + 1, NR]]) {
        x2.beginPath(); x2.moveTo(U(t), V(k0)); x2.lineTo(U(t), V(k1)); x2.stroke();
      }
    }
    const tx = new THREE.CanvasTexture(cv);
    tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 8;
    paint.map = tx;
  }
  const body = new THREE.Mesh(geo, [paint, glass, black]);
  body.castShadow = body.receiveShadow = true;
  body.name = 'body';
  g.add(body);

  // ── the cabin: seats, a dashboard, a wheel ───────────────────────────────
  {
    const trimTone = [0x1c1b1e, 0x3a2a20, 0x8a7458][Math.floor(hashPaint(paintHex + 19) * 3)];
    const inM = new THREE.MeshStandardMaterial({ color: trimTone, roughness: 0.85 });
    const dashM = new THREE.MeshStandardMaterial({ color: 0x141416, roughness: 0.6 });
    const parts = [], dparts = [];
    const tF = cabF + 0.03, tR = cabR - 0.04;
    const xF = xAt(tF), xR = xAt(tR);
    const floorY = yb + 0.12, cush = Math.max(floorY + 0.12, yt - 0.34);
    const hwC = half(lerp(tF, tR, 0.4)) * 0.78;
    const seat = (x, z, w) => {
      const base = new THREE.BoxGeometry(0.5, 0.14, w); base.translate(x, cush, z); parts.push(base);
      const backH = Math.min(0.62, roofY - cush - 0.12);
      const back = new THREE.BoxGeometry(0.12, backH, w * 0.92);
      back.translate(0, backH / 2, 0); back.rotateZ(-0.22); back.translate(x - 0.24, cush + 0.05, z); parts.push(back);
      if (w < 0.7) { const hr = new THREE.BoxGeometry(0.1, 0.16, w * 0.55); hr.rotateZ(-0.22); hr.translate(x - 0.24 - backH * 0.22 - 0.02, cush + backH + 0.1, z); parts.push(hr); }
    };
    const span = xF - xR;
    const frontX = xF - Math.min(0.75, span * 0.42);
    seat(frontX, hwC * 0.48, 0.5); seat(frontX, -hwC * 0.48, 0.5);
    if (span > 1.45 && !T.bed) seat(frontX - Math.min(0.9, span * 0.45), 0, hwC * 1.6);
    // the dashboard under the screen, a wheel on the driver's side
    const dash = new THREE.BoxGeometry(0.4, 0.22, hwC * 2); dash.translate(xF - 0.16, yt - 0.06, 0); dparts.push(dash);
    const wheel = new THREE.TorusGeometry(0.17, 0.022, 6, 20); wheel.rotateY(Math.PI / 2); wheel.rotateZ(0.45);
    wheel.translate(xF - 0.42, yt + 0.06, hwC * 0.48); dparts.push(wheel);
    const col = new THREE.CylinderGeometry(0.03, 0.03, 0.3, 6); col.rotateZ(Math.PI / 2 + 0.45); col.translate(xF - 0.3, yt, hwC * 0.48); dparts.push(col);
    const cabin = new THREE.Mesh(mergeGeometries(parts.map(q => q.index ? q.toNonIndexed() : q), false), inM);
    cabin.name = 'cabin'; cabin.userData.noShadow = 1; g.add(cabin);
    const dashMesh = new THREE.Mesh(mergeGeometries(dparts.map(q => q.index ? q.toNonIndexed() : q), false), dashM);
    dashMesh.userData.noShadow = 1; g.add(dashMesh);
    // the inside of the shell: dark, so the cabin is a room and not the paint's back
    const shellIn = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0x0e0e10, roughness: 0.9, side: THREE.BackSide }));
    shellIn.userData.noShadow = 1; shellIn.scale.setScalar(0.995); g.add(shellIn);
  }

  // ── wheels: turned tyre, dished rim, spokes, a disc behind ──────────────
  const wheelW = Math.max(0.19, Wd * 0.125);
  const tyreProfile = [];
  const sideR = wheelW * 0.22;
  for (let k = 0; k <= 12; k++) {
    // inner rim lip -> sidewall -> tread -> sidewall -> outer lip, (radius, z)
    const a = (k / 12) * Math.PI;
    tyreProfile.push(new THREE.Vector2(wr - sideR + Math.sin(a) * sideR, -wheelW * 0.5 + (1 - Math.cos(a)) * 0.5 * wheelW));
  }
  tyreProfile.unshift(new THREE.Vector2(wr * 0.66, -wheelW * 0.5));
  tyreProfile.push(new THREE.Vector2(wr * 0.66, wheelW * 0.5));
  const tyreBase = new THREE.LatheGeometry(tyreProfile, 36);
  tyreBase.rotateX(Math.PI / 2);                   // lathe axis Y -> Z (the axle)
  // OPEN SPOKES (2026-10-02): the rim was a solid dish with spokes laid on
  // it, so a wheel read as a flat white plate. A rim is a lip and a barrel
  // with a hub, and between the spokes you see into the dark wheel and the
  // brake behind it.
  const rimLip = new THREE.LatheGeometry([
    new THREE.Vector2(wr * 0.56, wheelW * 0.30), new THREE.Vector2(wr * 0.64, wheelW * 0.33),
    new THREE.Vector2(wr * 0.69, wheelW * 0.31), new THREE.Vector2(wr * 0.70, wheelW * 0.22),
    new THREE.Vector2(wr * 0.66, wheelW * 0.18)], 36);
  rimLip.rotateX(Math.PI / 2);
  const hub = new THREE.LatheGeometry([
    new THREE.Vector2(0.001, wheelW * 0.34), new THREE.Vector2(wr * 0.07, wheelW * 0.34),
    new THREE.Vector2(wr * 0.15, wheelW * 0.30), new THREE.Vector2(wr * 0.17, wheelW * 0.22)], 20);
  hub.rotateX(Math.PI / 2);
  const nSpokes = [5, 6, 10][Math.floor(hashPaint(paintHex + 7) * 3)];
  const spokes = [];
  const spW = nSpokes > 6 ? 0.05 : 0.085;
  for (let s = 0; s < nSpokes; s++) {
    // each spoke tapers from the hub and dishes back toward the lip
    const sp = new THREE.CylinderGeometry(wr * spW * 0.75, wr * spW * 1.15, wr * 0.44, 6, 1);
    sp.scale(1, 1, 0.55);
    sp.rotateX(-0.12);
    sp.translate(0, wr * 0.37, wheelW * 0.27);
    sp.rotateZ((s / nSpokes) * Math.PI * 2);
    spokes.push(sp);
  }
  const rimG = mergeGeometries([rimLip, hub, ...spokes].map(q => q.index ? q.toNonIndexed() : q), false);
  // the barrel and brake behind the spokes: dark, so the gaps read as depth
  const barrel = new THREE.CylinderGeometry(wr * 0.66, wr * 0.66, wheelW * 0.5, 30, 1, true);
  barrel.rotateX(Math.PI / 2); barrel.translate(0, 0, wheelW * 0.02);
  const disc = new THREE.CylinderGeometry(wr * 0.5, wr * 0.5, 0.03, 28);
  disc.rotateX(Math.PI / 2); disc.translate(0, 0, wheelW * 0.04);
  const caliper = new THREE.BoxGeometry(wr * 0.22, wr * 0.34, 0.06);
  caliper.translate(wr * 0.38, wr * 0.12, wheelW * 0.08);
  const tyres = [], rims = [], discs = [], liners = [], calipers = [];
  const trackZ = Wd * 0.5 - wheelW * 0.42;
  for (const t of [aF, aR]) {
    for (const side of [-1, 1]) {
      const m4 = new THREE.Matrix4().makeTranslation(xAt(t), wr, side * trackZ);
      if (side < 0) m4.multiply(new THREE.Matrix4().makeRotationY(Math.PI));
      tyres.push(tyreBase.clone().applyMatrix4(m4));
      rims.push(rimG.clone().applyMatrix4(m4));
      discs.push(disc.clone().applyMatrix4(m4), barrel.clone().applyMatrix4(m4));
      calipers.push(caliper.clone().applyMatrix4(m4));
      // the arch liner: a dark disc inboard of the wheel, the well's shadow
      const lg = new THREE.CircleGeometry(archR * 0.98, 20);
      lg.translate(xAt(t), wr, side * (trackZ - wheelW * 0.55));
      if (side < 0) lg.rotateY(0);
      liners.push(lg);
    }
  }
  const tyreM = new THREE.MeshStandardMaterial({ color: 0x141518, roughness: 0.9, side: THREE.DoubleSide });
  chrome.side = THREE.DoubleSide;
  const tyreMesh = new THREE.Mesh(mergeGeometries(tyres.map(q => q.toNonIndexed ? (q.index ? q.toNonIndexed() : q) : q), false), tyreM);
  tyreMesh.castShadow = true; tyreMesh.name = 'tyres'; g.add(tyreMesh);
  const rimM = new THREE.MeshStandardMaterial({ color: [0xb9bec6, 0x2a2c30, 0x8d9096][Math.floor(hashPaint(paintHex + 3) * 3)],
                                                metalness: 1.0, roughness: 0.3, side: THREE.DoubleSide });
  const rimMesh = new THREE.Mesh(mergeGeometries(rims, false), rimM);
  rimMesh.userData.noShadow = 1; rimMesh.name = 'rims'; g.add(rimMesh);
  const wellM = new THREE.MeshStandardMaterial({ color: 0x1a1b1e, metalness: 0.6, roughness: 0.5, side: THREE.DoubleSide });
  const wellMesh = new THREE.Mesh(mergeGeometries(discs.map(q => q.index ? q.toNonIndexed() : q), false), wellM);
  wellMesh.userData.noShadow = 1; wellMesh.name = 'brakes'; g.add(wellMesh);
  const calM = new THREE.MeshStandardMaterial({ color: [0xb81d1d, 0x222326, 0xc9a227][Math.floor(hashPaint(paintHex + 11) * 3)], roughness: 0.45 });
  const calMesh = new THREE.Mesh(mergeGeometries(calipers.map(q => q.index ? q.toNonIndexed() : q), false), calM);
  calMesh.userData.noShadow = 1; g.add(calMesh);
  const linerMesh = new THREE.Mesh(mergeGeometries(liners, false),
    new THREE.MeshBasicMaterial({ color: 0x050506, side: THREE.DoubleSide }));
  linerMesh.userData.noShadow = 1; g.add(linerMesh);

  // ── lights, grille, plate, mirrors, bumpers ─────────────────────────────
  const atSkin = (t, yFrac, zFrac) => {
    // a point on the skin at station t, height fraction of the side, lateral fraction
    const x = xAt(t), y = lerp(bottom(t), top(t), yFrac);
    return new THREE.Vector3(x, y, zFrac * half(t));
  };
  const lampG = [], tailG = [], trimG = [], mirG = [], plateG = [], chromeG = [];
  // A FACE ON THE CAR (2026-10-02): the lamps and grille were placed by
  // formula and sank inside the rounded nose, so the front was a blank bar
  // of soap. They are laid on the skin itself now: a ray from in front finds
  // the nose (or the tail) and each part sits on the surface it hits,
  // turned to its normal.
  const _ray = new THREE.Raycaster();
  const _bodyProbe = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  const onEnd = (front, y, z) => {
    const sx = front ? 1 : -1;
    _ray.set(new THREE.Vector3(sx * (L * 0.5 + 1), y, z), new THREE.Vector3(-sx, 0, 0));
    const h = _ray.intersectObject(_bodyProbe, false)[0];
    if (!h) return null;
    const n = h.face.normal.clone();
    if (n.x * sx < 0) n.negate();
    return { p: h.point, n };
  };
  // orient a part built facing +X onto a surface normal, set into it by `sink`
  const seat = (geom, hit, sink) => {
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), hit.n);
    geom.applyQuaternion(q);
    geom.translate(hit.p.x - hit.n.x * sink, hit.p.y - hit.n.y * sink, hit.p.z - hit.n.z * sink);
    return geom;
  };
  const yLamp = yb + bodyH * 0.6, yTail = yb + bodyH * 0.66;
  for (const sz of [1, -1]) {
    const hh = onEnd(true, yLamp, sz * half(0.02) * 0.6);
    if (hh) {
      // a headlamp unit: a flat lens in a dark bezel, wider than tall
      const bez = new THREE.BoxGeometry(0.05, 0.13, Wd * 0.2); trimG.push(seat(bez, hh, 0.012));
      const lens = new THREE.CapsuleGeometry(0.045, Wd * 0.13, 4, 10);
      lens.rotateX(Math.PI / 2); lens.scale(0.55, 1, 1); lampG.push(seat(lens, hh, -0.004));
    }
    const th = onEnd(false, yTail, sz * half(0.98) * 0.58);
    if (th) {
      const bar = new THREE.CapsuleGeometry(0.05, Wd * 0.2, 4, 10);
      bar.rotateX(Math.PI / 2); bar.scale(0.5, 1, 1); tailG.push(seat(bar, th, -0.004));
    }
    // mirror on a stalk at the base of the A pillar
    const mt = cabF + 0.035, mx = xAt(mt), mz = half(mt) * 0.93;
    const stalk = new THREE.BoxGeometry(0.07, 0.035, 0.1); stalk.translate(mx, yt + 0.05, sz * (mz + 0.04)); trimG.push(stalk);
    const mir = new THREE.SphereGeometry(0.1, 14, 10); mir.scale(0.55, 0.62, 1.15); mir.translate(mx - 0.02, yt + 0.09, sz * (mz + 0.15));
    mirG.push(mir);
  }
  // the grille: a dark opening low in the nose, slatted, and the plates
  const gh = onEnd(true, yb + bodyH * 0.36, 0);
  if (gh) {
    const grH = bodyH * 0.2, grW = Wd * 0.44;
    trimG.push(seat(new THREE.BoxGeometry(0.06, grH, grW), gh, 0.02));
    for (let i = 0; i < 3; i++) {
      const slat = new THREE.BoxGeometry(0.02, 0.012, grW * 0.94);
      slat.translate(0, (i - 1) * grH * 0.3, 0);
      chromeG.push(seat(slat, gh, -0.012));
    }
  }
  for (const front of [true, false]) {
    const ph = onEnd(front, yb + bodyH * (front ? 0.16 : 0.34), 0);
    if (ph) plateG.push(seat(new THREE.BoxGeometry(0.012, 0.11, 0.52), ph, -0.003));
  }
  // bumper lips front and back
  // bumper lips as wide as the rounded nose and tail actually are there
  const fbW = half(0.03) * 2 * (0.62 + 0.38 * endRound(0.03)) * 0.82;
  const fb = new THREE.CapsuleGeometry(0.045, Math.max(0.2, fbW - 0.09), 4, 12); fb.rotateX(Math.PI / 2); fb.translate(xAt(0.03), bottom(0.03) + 0.07, 0); trimG.push(fb);
  const rbW = half(0.97) * 2 * (0.62 + 0.38 * endRound(0.97)) * 0.82;
  const rb = new THREE.CapsuleGeometry(0.045, Math.max(0.2, rbW - 0.09), 4, 12); rb.rotateX(Math.PI / 2); rb.translate(xAt(0.97), bottom(0.97) + 0.09, 0); trimG.push(rb);
  const heads = new THREE.Mesh(mergeGeometries(lampG, false), new THREE.MeshStandardMaterial({ color: 0xfff6e0, emissive: 0xffeec2, emissiveIntensity: 0.6, roughness: 0.08, metalness: 0.1 }));
  heads.userData.noShadow = 1; heads.name = 'headlights'; g.add(heads);
  const tails = new THREE.Mesh(mergeGeometries(tailG, false), new THREE.MeshStandardMaterial({ color: 0x8c1414, emissive: 0xd11a1a, emissiveIntensity: 0.6, roughness: 0.2 }));
  tails.userData.noShadow = 1; tails.name = 'taillights'; g.add(tails);
  // mirror housings in the body colour
  const mirrors = new THREE.Mesh(mergeGeometries(mirG.map(q => q.index ? q.toNonIndexed() : q), false), paint.clone());
  mirrors.material.map = null; mirrors.castShadow = true; mirrors.name = 'mirrors'; g.add(mirrors);
  const trims = new THREE.Mesh(mergeGeometries(trimG.map(q => q.index ? q.toNonIndexed() : q), false), black);
  trims.castShadow = true; trims.name = 'trim'; g.add(trims);
  if (chromeG.length) {
    const ch = new THREE.Mesh(mergeGeometries(chromeG.map(q => q.index ? q.toNonIndexed() : q), false),
      new THREE.MeshStandardMaterial({ color: 0xc7ccd3, metalness: 1, roughness: 0.25 }));
    ch.userData.noShadow = 1; ch.name = 'grilleSlats'; g.add(ch);
  }
  if (plateG.length) {
    const pl = new THREE.Mesh(mergeGeometries(plateG.map(q => q.index ? q.toNonIndexed() : q), false),
      new THREE.MeshStandardMaterial({ color: 0xe9e6dc, roughness: 0.5 }));
    pl.userData.noShadow = 1; pl.name = 'plates'; g.add(pl);
  }

  // ── the pickup's bed and the taxi's sign ─────────────────────────────
  if (T.bed) {
    const bF = xAt(Math.min(cabR + 0.04, 0.95)), bR = xAt(0.97);
    const bL = Math.abs(bF - bR), bC = (bF + bR) / 2;
    const bed = new THREE.Mesh(new THREE.BoxGeometry(bL, 0.05, Wd * 0.86),
      new THREE.MeshStandardMaterial({ color: 0x1e2024, roughness: 0.9 }));
    bed.position.set(bC, yt - 0.02, 0); g.add(bed);
    for (const sz of [1, -1]) {
      const wall = new THREE.Mesh(new THREE.BoxGeometry(bL, 0.3, 0.06), paint);
      wall.position.set(bC, yt + 0.06, sz * Wd * 0.455); wall.castShadow = true; g.add(wall);
    }
  }
  if (T.taxi) {
    const tl = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.42, 4, 10),
      new THREE.MeshStandardMaterial({ color: 0xf7d045, emissive: 0xf7d045, emissiveIntensity: 0.7 }));
    tl.rotation.x = Math.PI / 2; tl.scale.set(1, 1, 0.8);
    tl.position.set(xAt(lerp(wsTop, blTop, 0.5)), roofY + 0.12, 0);
    g.add(tl);
  }
  g.userData.car = { lofted: true, stations: NS, ring: NR, glassFaces: quads[1].length / 6, spokes: nSpokes };
  g.traverse(o => {
    if (!o.isMesh) return;
    for (const m of [].concat(o.material)) if (m) m.userData.noAutoTex = true;
  });
  return g;
}
