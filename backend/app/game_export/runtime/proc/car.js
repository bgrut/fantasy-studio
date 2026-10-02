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
  const cabLen = cp.cabinLen || T.cabinLen || 0.46, cabH = cp.cabinH || T.cabinH || 0.52;
  const cabX = cp.cabinX !== undefined ? cp.cabinX : (T.cabinX !== undefined ? T.cabinX : -0.04);
  const wr = cp.wheelR || T.wheelR || 0.34;
  const wb = cp.wheelBase || T.wheelBase || 0.31;
  const paintHex = cp.paint || 0xb5202a;
  const wear = 0.25 + hashPaint(paintHex) * 0.75;
  const paint = new THREE.MeshPhysicalMaterial({
    color: new THREE.Color(paintHex), metalness: 0.28,
    roughness: 0.22 + wear * 0.36, clearcoat: 1.0 - wear * 0.45,
    clearcoatRoughness: 0.03 + wear * 0.22, envMapIntensity: 1.15 - wear * 0.5 });
  const glass = new THREE.MeshPhysicalMaterial({
    color: 0x0b0f15, metalness: 0.1, roughness: 0.04, clearcoat: 1.0, clearcoatRoughness: 0.02,
    envMapIntensity: 1.5 });
  const black = new THREE.MeshStandardMaterial({ color: 0x0d0e10, roughness: 0.55, metalness: 0.2 });
  const chrome = new THREE.MeshStandardMaterial({ color: 0xd2d6dc, metalness: 0.95, roughness: 0.16 });

  // ── the car's lines, t = 0 nose .. 1 tail ─────────────────────────────
  const yb = Math.max(0.16, bodyY - bodyH * 0.5);     // sill
  const yt = yb + bodyH;                              // beltline
  const cabF = Math.min(Math.max(0.5 - cabX - cabLen * 0.5, 0.30), 0.60);
  const cabR = Math.min(cabF + cabLen, 0.92);
  const rake = Math.min(0.16, cabLen * 0.36);         // how far the windscreen leans
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
  const aF = wb, aR = 1 - wb;
  const archR = wr * 1.12;
  const bottom = (t) => {
    let y = yb;
    for (const a of [aF, aR]) {
      const dx = Math.abs(t - a) * L;
      if (dx < archR) y = Math.max(y, wr + Math.sqrt(archR * archR - dx * dx) * 0.86);
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
    const f = t < 0.5 ? Math.min(1, t / 0.055) : Math.min(1, (1 - t) / 0.045);
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
    const wRoof = lerp(wBelt, hw * (tall ? 0.9 : 0.70), c);
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
  const body = new THREE.Mesh(geo, [paint, glass, black]);
  body.castShadow = body.receiveShadow = true;
  body.name = 'body';
  g.add(body);

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
  const rimDish = new THREE.LatheGeometry([
    new THREE.Vector2(0.001, wheelW * 0.30), new THREE.Vector2(wr * 0.16, wheelW * 0.30),
    new THREE.Vector2(wr * 0.2, wheelW * 0.18), new THREE.Vector2(wr * 0.62, wheelW * 0.10),
    new THREE.Vector2(wr * 0.68, wheelW * 0.32), new THREE.Vector2(wr * 0.70, wheelW * 0.30)], 30);
  rimDish.rotateX(Math.PI / 2);
  const nSpokes = [5, 6, 10][Math.floor(hashPaint(paintHex + 7) * 3)];
  const spokes = [];
  for (let s = 0; s < nSpokes; s++) {
    const sp = new THREE.BoxGeometry(wr * 0.09, wr * 0.52, wheelW * 0.08);
    sp.translate(0, wr * 0.40, wheelW * 0.26);
    sp.rotateZ((s / nSpokes) * Math.PI * 2);
    spokes.push(sp);
  }
  const rimG = mergeGeometries([rimDish, ...spokes].map(q => q.index ? q.toNonIndexed() : q), false);
  const disc = new THREE.CylinderGeometry(wr * 0.52, wr * 0.52, 0.03, 24);
  disc.rotateX(Math.PI / 2); disc.translate(0, 0, -wheelW * 0.05);
  const tyres = [], rims = [], discs = [], liners = [];
  const trackZ = Wd * 0.5 - wheelW * 0.42;
  for (const t of [aF, aR]) {
    for (const side of [-1, 1]) {
      const m4 = new THREE.Matrix4().makeTranslation(xAt(t), wr, side * trackZ);
      if (side < 0) m4.multiply(new THREE.Matrix4().makeRotationY(Math.PI));
      tyres.push(tyreBase.clone().applyMatrix4(m4));
      rims.push(rimG.clone().applyMatrix4(m4));
      discs.push(disc.clone().applyMatrix4(m4));
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
  const rimMesh = new THREE.Mesh(mergeGeometries(rims, false), chrome);
  rimMesh.userData.noShadow = 1; rimMesh.name = 'rims'; g.add(rimMesh);
  const linerMesh = new THREE.Mesh(mergeGeometries(liners, false),
    new THREE.MeshBasicMaterial({ color: 0x050506, side: THREE.DoubleSide }));
  linerMesh.userData.noShadow = 1; g.add(linerMesh);

  // ── lights, grille, plate, mirrors, bumpers ─────────────────────────────
  const atSkin = (t, yFrac, zFrac) => {
    // a point on the skin at station t, height fraction of the side, lateral fraction
    const x = xAt(t), y = lerp(bottom(t), top(t), yFrac);
    return new THREE.Vector3(x, y, zFrac * half(t));
  };
  const lampG = [], tailG = [], trimG = [];
  for (const sz of [1, -1]) {
    // the lamps sit ON the skin where the nose has rounded off, proud of it
    const hp = atSkin(0.045, 0.62, 0.66 * sz);
    const lens = new THREE.SphereGeometry(0.1, 20, 12);
    lens.scale(0.7, 0.7, 2.0); lens.rotateY(sz * 0.35); lens.translate(hp.x + 0.02, hp.y, hp.z);
    lampG.push(lens);
    const tp = atSkin(0.965, 0.64, 0.58 * sz);
    const bar = new THREE.CapsuleGeometry(0.045, Wd * 0.18, 4, 10);
    bar.rotateX(Math.PI / 2); bar.rotateY(-sz * 0.25); bar.translate(tp.x - 0.03, tp.y, tp.z);
    tailG.push(bar);
    // mirror on a stalk at the base of the A pillar
    const mp = atSkin(cabF + 0.01, 1.0, 1.0 * sz);
    const stalk = new THREE.BoxGeometry(0.06, 0.03, 0.09); stalk.translate(mp.x, yt + 0.06, sz * (half(cabF) + 0.03)); trimG.push(stalk);
    const mir = new THREE.SphereGeometry(0.09, 12, 8); mir.scale(0.6, 0.55, 1.0); mir.translate(mp.x, yt + 0.09, sz * (half(cabF) + 0.12)); trimG.push(mir);
  }
  // grille: a dark recess low in the nose
  const gp = atSkin(0.01, 0.38, 0);
  const grille = new THREE.BoxGeometry(0.05, bodyH * 0.22, Wd * 0.52); grille.translate(gp.x, gp.y, 0); trimG.push(grille);
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
  const trims = new THREE.Mesh(mergeGeometries(trimG.map(q => q.index ? q.toNonIndexed() : q), false), black);
  trims.castShadow = true; trims.name = 'trim'; g.add(trims);

  // ── the pickup's bed and the taxi's sign ─────────────────────────────
  if (T.bed) {
    const bF = xAt(Math.min(cabR + 0.04, 0.95)), bR = xAt(0.97);
    const bL = Math.abs(bF - bR), bC = (bF + bR) / 2;
    const bed = new THREE.Mesh(new THREE.BoxGeometry(bL, 0.05, Wd * 0.86),
      new THREE.MeshStandardMaterial({ color: 0x1e2024, roughness: 0.9 }));
    bed.position.set(bC, yt - 0.02, 0); g.add(bed);
    for (const sz of [1, -1]) {
      const wall = new THREE.Mesh(new THREE.BoxGeometry(bL, 0.3, 0.06), paint);
      wall.position.set(bC, yt + 0.14, sz * Wd * 0.44); wall.castShadow = true; g.add(wall);
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
