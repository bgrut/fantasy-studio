// FLORA (2026-10-01): forests that read as forests. The old region forest
// was a cylinder under a few icospheres, 300 at most; the owner asked for
// the dense, crisp kind of woodland where a valley holds hundreds of
// thousands of trees. Three parts:
//
// 1. Trees are GROWN, not stamped: a trunk and limbs as tapered tubes on a
//    bending path, branching by the golden angle, with leaf (or needle, or
//    frond) cards at the tips drawn on a canvas here, so nothing is
//    downloaded and everything is this world's colour. Normals on the cards
//    point out of the crown, so the crown shades as one soft volume rather
//    than a pile of flat planes.
// 2. Up close every tree is that geometry. Past NEAR metres it is a picture
//    of itself: each variant is rendered from eight sides under this
//    world's own sun, sky and environment into an atlas, and a far tree is
//    one camera-facing quad showing the side the camera is on. Near and far
//    dissolve into each other with complementary screen-space dithering, so
//    the hand-over has no pop and no blend sorting.
// 3. Far trees cost one quad and five floats each, so the land past the
//    playfield can carry a whole forest to the horizon.
//
// +Y up, metres. Imported by main.js; nothing here reads SPEC directly.
import * as THREE from 'three';

const TAU = Math.PI * 2;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export function mulberry(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ── textures ───────────────────────────────────────────────────────────────
// A 2x2 atlas of foliage clusters (four variations), alpha outside the leaves.
function hsl(h, s, l, a = 1) {
  return `hsla(${((h % 1) + 1) % 1 * 360},${Math.max(0, Math.min(1, s)) * 100}%,${Math.max(0, Math.min(1, l)) * 100}%,${a})`;
}

function foliageAtlas(kind, leaf, seed) {
  const N = 1024, Q = N / 2;
  const c = document.createElement('canvas'); c.width = c.height = N;
  const g = c.getContext('2d');
  const r = mulberry(seed);
  g.clearRect(0, 0, N, N);
  for (let qi = 0; qi < 4; qi++) {
    const ox = (qi % 2) * Q, oy = Math.floor(qi / 2) * Q;
    g.save(); g.beginPath(); g.rect(ox, oy, Q, Q); g.clip();
    const cx = ox + Q / 2, cy = oy + Q / 2;
    if (kind === 'pine') {
      // a conifer branchlet: a twig up the middle with side shoots, every
      // shoot furred with short needles, dark inside and lighter at the tips
      g.lineCap = 'round';
      const bx = cx + (r() - 0.5) * Q * 0.05, by = oy + Q * 0.97, ty = oy + Q * 0.04;
      const shoots = [[bx, by, bx + (r() - 0.5) * Q * 0.1, ty, 1.0]];
      for (let s = 0; s < 9; s++) {
        const t = 0.15 + (s / 9) * 0.75;
        const px = bx + (shoots[0][2] - bx) * t, py = by + (ty - by) * t;
        const side = s % 2 ? 1 : -1;
        const a = -Math.PI / 2 + side * (0.75 + r() * 0.35);
        const L = Q * (0.38 - t * 0.22) * (0.85 + r() * 0.3);
        shoots.push([px, py, px + Math.cos(a) * L, py + Math.sin(a) * L, 0.7]);
      }
      for (const pass of [0, 1]) {
        for (const [x0, y0, x1, y1, w] of shoots) {
          const a0 = Math.atan2(y1 - y0, x1 - x0);
          const n = Math.round(60 * w);
          for (let i = 0; i < n; i++) {
            const t = 0.05 + (i / n) * 0.95;
            const px = x0 + (x1 - x0) * t, py = y0 + (y1 - y0) * t;
            for (const side of [-1, 1]) {
              const na = a0 + side * (0.6 + r() * 0.5) * (pass ? 0.8 : 1.1);
              const nl = Q * (0.045 + 0.045 * (1 - t) + r() * 0.02) * (pass ? 0.85 : 1.05);
              const sh = (r() - 0.5) * 0.06;
              const lum = leaf.l + sh + (pass ? 0.04 + t * 0.05 : -0.05);
              g.strokeStyle = hsl(leaf.h + sh * 0.3, leaf.s + sh, lum);
              g.lineWidth = pass ? 2.0 : 3.2;
              g.beginPath(); g.moveTo(px, py);
              g.lineTo(px + Math.cos(na) * nl, py + Math.sin(na) * nl); g.stroke();
            }
          }
        }
      }
      g.strokeStyle = hsl(0.07, 0.3, 0.16); g.lineWidth = 4;
      for (const [x0, y0, x1, y1] of shoots) { g.beginPath(); g.moveTo(x0, y0); g.lineTo(x0 + (x1 - x0) * 0.5, y0 + (y1 - y0) * 0.5); g.stroke(); }
    } else if (kind === 'palm') {
      // one frond: a rib with long leaflets falling off it
      const bx = ox + Q * 0.06, by = cy;
      g.strokeStyle = hsl(leaf.h - 0.02, leaf.s * 0.6, leaf.l * 0.8); g.lineWidth = 6;
      g.beginPath(); g.moveTo(bx, by); g.lineTo(ox + Q * 0.97, cy); g.stroke();
      for (let i = 0; i < 46; i++) {
        const t = i / 46, px = bx + (Q * 0.9) * t;
        for (const side of [-1, 1]) {
          const ll = Q * 0.42 * Math.sin(Math.PI * Math.min(1, t * 1.15 + 0.05));
          const sh = (r() - 0.5) * 0.08;
          g.fillStyle = hsl(leaf.h + sh * 0.3, leaf.s + sh, leaf.l + sh);
          g.beginPath(); g.moveTo(px, by);
          g.quadraticCurveTo(px + ll * 0.35, by + side * ll * 0.6, px + ll * 0.55, by + side * ll);
          g.quadraticCurveTo(px + ll * 0.2, by + side * ll * 0.45, px + 5, by);
          g.fill();
        }
      }
    } else {
      // a broadleaf cluster: leaves from a few twigs, darker ones underneath
      const twigs = 4 + Math.floor(r() * 3);
      const tips = [];
      g.lineCap = 'round';
      for (let tw = 0; tw < twigs; tw++) {
        const a = -Math.PI / 2 + (r() - 0.5) * 2.4;
        const len = Q * (0.22 + r() * 0.2);
        const ex = cx + Math.cos(a) * len, ey = cy + Q * 0.22 + Math.sin(a) * len;
        g.strokeStyle = hsl(0.07, 0.3, 0.2); g.lineWidth = 3;
        g.beginPath(); g.moveTo(cx, cy + Q * 0.3); g.lineTo(ex, ey); g.stroke();
        tips.push([ex, ey, a]);
      }
      for (let layer = 0; layer < 2; layer++) {
        const n = layer === 0 ? 55 : 75;
        for (let i = 0; i < n; i++) {
          const [tx, ty, ta] = tips[Math.floor(r() * tips.length)];
          const rr = Q * (0.04 + r() * 0.2);
          const pa = ta + (r() - 0.5) * 2.6;
          const px = tx + Math.cos(pa) * rr * 0.9, py = ty + Math.sin(pa) * rr * 0.9;
          const L = Q * (0.07 + r() * 0.05) * (leaf.size || 1), W = L * (leaf.width || 0.45);
          const ang = pa + (r() - 0.5) * 0.9;
          const sh = (r() - 0.5) * 0.1;
          const lum = leaf.l + sh - (layer === 0 ? 0.08 : 0) + (r() < 0.15 ? 0.08 : 0);
          g.save(); g.translate(px, py); g.rotate(ang);
          const grd = g.createLinearGradient(0, -W, 0, W);
          grd.addColorStop(0, hsl(leaf.h + sh * 0.4, leaf.s + sh, lum + 0.05));
          grd.addColorStop(1, hsl(leaf.h + sh * 0.4, leaf.s + sh, lum - 0.06));
          g.fillStyle = grd;
          g.beginPath(); g.moveTo(0, 0);
          g.bezierCurveTo(L * 0.3, -W, L * 0.75, -W * 0.8, L, 0);
          g.bezierCurveTo(L * 0.75, W * 0.8, L * 0.3, W, 0, 0);
          g.fill();
          g.strokeStyle = hsl(leaf.h, leaf.s * 0.7, lum + 0.1, 0.55); g.lineWidth = 1.2;
          g.beginPath(); g.moveTo(0, 0); g.lineTo(L * 0.92, 0); g.stroke();
          g.restore();
        }
      }
    }
    g.restore();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  return t;
}

// ── geometry ───────────────────────────────────────────────────────────────
class Builder {
  constructor() { this.p = []; this.n = []; this.u = []; this.i = []; this.c = []; this.s = []; }
  get vc() { return this.p.length / 3; }
  geometry() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.u, 2));
    g.setAttribute('sway', new THREE.Float32BufferAttribute(this.c, 1));
    // self-shadow baked per vertex: deep in the crown and at the foot of the
    // trunk is darker, so a crown has an inside and a trunk stands in its
    // own shade
    while (this.s.length < this.vc) this.s.push(1);
    g.setAttribute('shade', new THREE.Float32BufferAttribute(this.s, 1));
    g.setIndex(this.i);
    return g;
  }
}

// a tapered tube along points [{p, r}]
function tube(b, path, sides, sway0, sway1) {
  const base = b.vc;
  let len = 0;
  const T = new THREE.Vector3(), N = new THREE.Vector3(), B = new THREE.Vector3();
  const up = new THREE.Vector3(0, 1, 0);
  for (let k = 0; k < path.length; k++) {
    const pk = path[k].p;
    const nxt = path[Math.min(k + 1, path.length - 1)].p, prv = path[Math.max(k - 1, 0)].p;
    T.subVectors(nxt, prv).normalize();
    if (k === 0) {
      N.crossVectors(T, Math.abs(T.y) > 0.95 ? new THREE.Vector3(1, 0, 0) : up).normalize();
    } else {                                // parallel transport keeps the seam straight
      N.sub(T.clone().multiplyScalar(N.dot(T))).normalize();
    }
    B.crossVectors(T, N);
    if (k > 0) len += pk.distanceTo(path[k - 1].p);
    const sw = sway0 + (sway1 - sway0) * (k / (path.length - 1));
    for (let s = 0; s <= sides; s++) {
      const a = (s / sides) * TAU;
      const ca = Math.cos(a), sa = Math.sin(a);
      const nx = N.x * ca + B.x * sa, ny = N.y * ca + B.y * sa, nz = N.z * ca + B.z * sa;
      const rr = path[k].r;
      b.p.push(pk.x + nx * rr, pk.y + ny * rr, pk.z + nz * rr);
      b.n.push(nx, ny, nz);
      b.u.push(s / sides, len / (TAU * Math.max(path[0].r, 0.05)) * 0.5);
      b.c.push(sw);
      b.s.push(0.62 + 0.38 * Math.min(1, Math.max(0, pk.y / 2.5)));
    }
  }
  const row = sides + 1;
  for (let k = 0; k < path.length - 1; k++) {
    for (let s = 0; s < sides; s++) {
      const a = base + k * row + s, c = a + row;
      b.i.push(a, c, a + 1, a + 1, c, c + 1);
    }
  }
}

// a foliage card: centre c, size w x h, facing n, long axis along ax, atlas quadrant q
function card(b, c, w, h, n, ax, q, crown, sway) {
  const A = ax.clone().normalize();
  const S = new THREE.Vector3().crossVectors(n, A).normalize();
  const base = b.vc;
  const u0 = (q % 2) * 0.5, v0 = Math.floor(q / 2) * 0.5;
  const corners = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]];
  for (const [sx, sy] of corners) {
    const x = c.x + S.x * sx * w + A.x * sy * h;
    const y = c.y + S.y * sx * w + A.y * sy * h;
    const z = c.z + S.z * sx * w + A.z * sy * h;
    b.p.push(x, y, z);
    // crown normals: out of the crown's centre, a little skyward
    const o = new THREE.Vector3(x - crown.x, (y - crown.y) * 0.8 + 0.35, z - crown.z);
    const dc = o.length() / Math.max(crown.r || 3, 0.5);
    o.normalize();
    b.n.push(o.x, o.y, o.z);
    b.u.push(u0 + (sx + 0.5) * 0.5, v0 + (sy + 0.5) * 0.5);
    b.c.push(sway);
    const k = Math.min(1, Math.max(0, (dc - 0.25) / 0.75));
    b.s.push(0.42 + 0.58 * k * k * (3 - 2 * k));
  }
  b.i.push(base, base + 1, base + 2, base, base + 2, base + 3);
}

function randUnitPerp(d, r) {
  const a = new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5);
  return a.sub(d.clone().multiplyScalar(a.dot(d))).normalize();
}

function growBroadleaf(r, P) {
  const bark = new Builder(), leaf = new Builder();
  const tips = [];
  const H = P.height, maxDepth = P.depth;
  function branch(o, d, len, rad, depth, az) {
    const steps = depth === 0 ? 9 : Math.max(2, 5 - depth);
    const path = [];
    const p = o.clone(), dir = d.clone();
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      path.push({ p: p.clone(), r: Math.max(rad * (1 - t * (depth === 0 ? 0.55 : 0.8)), 0.012) });
      dir.addScaledVector(randUnitPerp(dir, r), P.kink * (depth === 0 ? 0.35 : 1));
      dir.y += (depth === 0 ? 0.04 : P.lift) - P.droop * t;
      dir.normalize();
      p.addScaledVector(dir, len / steps);
    }
    tube(bark, path, depth === 0 ? 9 : depth === 1 ? 6 : depth === 2 ? 4 : 3,
         depth === 0 ? 0 : 0.15 * depth, depth === 0 ? 0.12 : 0.3 + 0.25 * depth);
    if (depth >= P.leafFrom) tips.push(path);
    if (depth < maxDepth) {
      const kids = depth === 0 ? P.limbs : P.twigs;
      const from = depth === 0 ? P.crownStart : 0.3;
      for (let k = 0; k < kids; k++) {
        const t = from + (1 - from) * ((k + 0.5) / kids) * (0.92 + r() * 0.08);
        const fi = t * steps, i0 = Math.min(Math.floor(fi), steps - 1);
        const at = path[i0].p.clone().lerp(path[i0 + 1].p, fi - i0);
        const pd = path[i0 + 1].p.clone().sub(path[i0].p).normalize();
        az += GOLDEN + (r() - 0.5) * 0.4;
        const side = new THREE.Vector3(Math.cos(az), 0, Math.sin(az));
        side.sub(pd.clone().multiplyScalar(side.dot(pd))).normalize();
        const ang = P.spread[0] + r() * (P.spread[1] - P.spread[0]);
        const nd = pd.clone().multiplyScalar(Math.cos(ang)).addScaledVector(side, Math.sin(ang)).normalize();
        const nl = len * P.lenRatio * (1 - t * 0.45) * (0.8 + r() * 0.4);
        const nr = path[i0].r * P.radRatio;
        branch(at, nd, nl, nr, depth + 1, az * 1.7);
      }
    }
  }
  const lean = new THREE.Vector3((r() - 0.5) * 0.12, 1, (r() - 0.5) * 0.12).normalize();
  branch(new THREE.Vector3(0, -0.3, 0), lean, H * P.trunkFrac, P.trunkR, 0, r() * TAU);
  // the crown: where the leaves are
  if (P.leaves) {
    const crown = new THREE.Vector3();
    let nC = 0;
    for (const path of tips) for (const q of path) { crown.add(q.p); nC++; }
    crown.multiplyScalar(1 / Math.max(nC, 1));
    crown.r = 0.5;
    for (const path of tips) for (const q of path) crown.r = Math.max(crown.r, q.p.distanceTo(crown));
    for (const path of tips) {
      const n = P.cardsPer;
      for (let k = 0; k < n; k++) {
        const t = 0.35 + 0.65 * ((k + r()) / n);
        const fi = t * (path.length - 1), i0 = Math.min(Math.floor(fi), path.length - 2);
        const at = path[i0].p.clone().lerp(path[i0 + 1].p, fi - i0);
        at.add(new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).multiplyScalar(P.card * 0.5));
        const nrm = new THREE.Vector3(r() - 0.5, r() * 0.8, r() - 0.5).normalize();
        const ax = randUnitPerp(nrm, r);
        const s = P.card * (0.75 + r() * 0.5);
        card(leaf, at, s, s, nrm, ax, Math.floor(r() * 4), crown, 1.0);
      }
    }
  }
  return { bark: bark.geometry(true), leaf: P.leaves ? leaf.geometry(true) : null };
}

function growPine(r, P) {
  const bark = new Builder(), leaf = new Builder();
  const H = P.height;
  const lean = new THREE.Vector3((r() - 0.5) * 0.05, 1, (r() - 0.5) * 0.05).normalize();
  const path = [];
  for (let s = 0; s <= 10; s++) {
    const t = s / 10;
    path.push({ p: lean.clone().multiplyScalar(-0.3 + H * t), r: Math.max(P.trunkR * (1 - t * 0.97), 0.015) });
  }
  tube(bark, path, 8, 0, 0.25);
  const crown = lean.clone().multiplyScalar(H * 0.55);
  const y0 = H * P.crownStart, whorls = Math.round((H - y0) / P.whorlGap);
  let az = r() * TAU;
  for (let w = 0; w <= whorls; w++) {
    const t = w / Math.max(whorls, 1);
    const y = y0 + (H * 0.97 - y0) * t;
    const L = (P.branchLen * Math.pow(1 - t, 0.85) + 0.35) * (0.85 + r() * 0.3);
    const k = P.perWhorl - (t > 0.75 ? 2 : 0);
    for (let i = 0; i < k; i++) {
      az += TAU / k + (r() - 0.5) * 0.5;
      const droop = P.droop * (0.6 + r() * 0.8);
      const d = new THREE.Vector3(Math.cos(az), -droop, Math.sin(az)).normalize();
      const o = lean.clone().multiplyScalar(y);
      const bp = [];
      const p = o.clone(), dd = d.clone();
      for (let s = 0; s <= 2; s++) {
        bp.push({ p: p.clone(), r: Math.max(0.05 * (1 - t * 0.6) * (1 - s / 2.2), 0.008) });
        dd.y += 0.09; dd.normalize();
        p.addScaledVector(dd, L / 2);
      }
      // the wood stops inside the foliage: a bare stick past the needles
      // read as a coat-hanger
      const wood = bp.map((q, s) => ({ p: bp[0].p.clone().lerp(q.p, 0.72), r: q.r }));
      tube(bark, wood, 3, 0.2, 0.7);
      // needle sprays laid along the branch, two crossed planes each
      // this whorl's own crown: the trunk at its height, as wide as its branches
      const cw = o.clone(); cw.r = L + 0.4;
      const sprays = Math.max(2, Math.round(L / 0.95));
      for (let s = 0; s < sprays; s++) {
        const tt = 0.25 + 0.75 * ((s + 0.5) / sprays);
        const at = bp[0].p.clone().lerp(bp[2].p, tt);
        const ax = bp[2].p.clone().sub(bp[0].p).normalize();
        const w2 = P.card * (1.05 - tt * 0.3) * (0.9 + r() * 0.2);
        const nUp = new THREE.Vector3(0, 1, 0).sub(ax.clone().multiplyScalar(ax.y)).normalize();
        card(leaf, at, w2, w2 * 1.15, nUp, ax, Math.floor(r() * 4), cw, 0.7 + tt * 0.3);
        const nSide = new THREE.Vector3().crossVectors(ax, nUp).normalize()
          .lerp(nUp, 0.35).normalize();
        card(leaf, at, w2 * 0.85, w2, nSide, ax, Math.floor(r() * 4), cw, 0.7 + tt * 0.3);
      }
    }
  }
  // the leader at the very top
  const top = lean.clone().multiplyScalar(H * 0.98);
  crown.r = H * 0.5;
  card(leaf, top, P.card * 0.7, P.card * 1.1, new THREE.Vector3(1, 0, 0), lean, 0, crown, 1.0);
  card(leaf, top, P.card * 0.7, P.card * 1.1, new THREE.Vector3(0, 0, 1), lean, 1, crown, 1.0);
  return { bark: bark.geometry(true), leaf: leaf.geometry(true) };
}

function growPalm(r, P) {
  const bark = new Builder(), leaf = new Builder();
  const H = P.height;
  const bend = new THREE.Vector3(Math.cos(r() * TAU), 0, Math.sin(r() * TAU)).multiplyScalar(H * (0.12 + r() * 0.12));
  const path = [];
  for (let s = 0; s <= 16; s++) {
    const t = s / 16;
    const p = new THREE.Vector3(0, -0.3 + H * t, 0).addScaledVector(bend, t * t);
    // the ringed trunk of a palm
    path.push({ p, r: P.trunkR * (1 - t * 0.35) * (s % 2 ? 0.94 : 1.0) });
  }
  tube(bark, path, 8, 0, 0.35);
  const top = path[path.length - 1].p;
  const crown = top.clone();
  crown.r = P.frondLen;
  const fronds = P.fronds;
  for (let f = 0; f < fronds; f++) {
    const az = (f / fronds) * TAU + r() * 0.4;
    const dir = new THREE.Vector3(Math.cos(az), 0.35 + r() * 0.5, Math.sin(az)).normalize();
    const segs = 5;
    let prev = top.clone();
    const d = dir.clone();
    const L = P.frondLen * (0.8 + r() * 0.35);
    for (let s = 0; s < segs; s++) {
      d.y -= 0.22; d.normalize();
      const next = prev.clone().addScaledVector(d, L / segs);
      const mid = prev.clone().lerp(next, 0.5);
      const side = new THREE.Vector3(-d.z, 0, d.x).normalize();
      const nrm = new THREE.Vector3().crossVectors(d, side).normalize();
      if (nrm.y < 0) nrm.negate();
      card(leaf, mid, L / segs * 1.25, P.frondW * (1 - s / segs * 0.4), nrm, d.clone(), f % 4, crown, 0.4 + s / segs);
      prev = next;
    }
  }
  return { bark: bark.geometry(true), leaf: leaf.geometry(true) };
}

function growBush(r, P) {
  const bark = new Builder(), leaf = new Builder();
  const crown = new THREE.Vector3(0, P.height * 0.45, 0);
  crown.r = P.height * 0.75;
  const stems = 5 + Math.floor(r() * 4);
  for (let s = 0; s < stems; s++) {
    const az = r() * TAU;
    const d = new THREE.Vector3(Math.cos(az) * 0.5, 1, Math.sin(az) * 0.5).normalize();
    const path = [];
    for (let k = 0; k <= 3; k++) path.push({ p: d.clone().multiplyScalar(P.height * 0.85 * k / 3).add(new THREE.Vector3(0, -0.1, 0)), r: 0.03 * (1 - k / 3.5) });
    tube(bark, path, 4, 0.1, 0.6);
  }
  const n = P.cards;
  for (let k = 0; k < n; k++) {
    const u = r() * TAU, v = Math.acos(1 - r() * 1.2);
    const rr = P.height * 0.55 * (0.55 + r() * 0.45);
    const at = new THREE.Vector3(Math.sin(v) * Math.cos(u) * rr * 1.25, P.height * 0.4 + Math.cos(v) * rr * 0.8, Math.sin(v) * Math.sin(u) * rr * 1.25);
    const nrm = at.clone().sub(crown).normalize().lerp(new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5), 0.6).normalize();
    const s = P.card * (0.7 + r() * 0.6);
    card(leaf, at, s, s, nrm, randUnitPerp(nrm, r), Math.floor(r() * 4), crown, 0.6);
  }
  return { bark: bark.geometry(true), leaf: leaf.geometry(true) };
}

const KINDS = {
  broadleaf: (r) => ({ grow: growBroadleaf, height: 9 + r() * 6, trunkFrac: 0.5, trunkR: 0.28 + r() * 0.1, depth: 3,
    limbs: 6 + Math.floor(r() * 3), twigs: 4, crownStart: 0.42, spread: [0.55, 1.05], lenRatio: 0.62, radRatio: 0.55,
    kink: 0.16, lift: 0.07, droop: 0.05, leafFrom: 2, leaves: true, cardsPer: 5, card: 1.5 }),
  oak: (r) => ({ grow: growBroadleaf, height: 8 + r() * 4, trunkFrac: 0.38, trunkR: 0.42 + r() * 0.12, depth: 3,
    limbs: 7, twigs: 4, crownStart: 0.35, spread: [0.85, 1.35], lenRatio: 0.78, radRatio: 0.55,
    kink: 0.24, lift: 0.02, droop: 0.06, leafFrom: 2, leaves: true, cardsPer: 5, card: 1.7 }),
  birch: (r) => ({ grow: growBroadleaf, height: 11 + r() * 5, trunkFrac: 0.7, trunkR: 0.18 + r() * 0.05, depth: 3,
    limbs: 7, twigs: 3, crownStart: 0.45, spread: [0.35, 0.75], lenRatio: 0.45, radRatio: 0.5,
    kink: 0.12, lift: 0.04, droop: 0.12, leafFrom: 2, leaves: true, cardsPer: 5, card: 1.2 }),
  pine: (r) => ({ grow: growPine, height: 13 + r() * 9, trunkR: 0.3 + r() * 0.1, crownStart: 0.28 + r() * 0.12,
    whorlGap: 1.05, branchLen: 3.4 + r() * 0.8, perWhorl: 6, droop: 0.22, card: 1.6 }),
  spruce: (r) => ({ grow: growPine, height: 16 + r() * 8, trunkR: 0.32 + r() * 0.08, crownStart: 0.12,
    whorlGap: 0.95, branchLen: 3.0 + r() * 0.6, perWhorl: 6, droop: 0.38, card: 1.45 }),
  palm: (r) => ({ grow: growPalm, height: 8 + r() * 5, trunkR: 0.22, fronds: 11 + Math.floor(r() * 4), frondLen: 4.2, frondW: 1.6 }),
  dead: (r) => ({ grow: growBroadleaf, height: 7 + r() * 5, trunkFrac: 0.55, trunkR: 0.24 + r() * 0.1, depth: 3,
    limbs: 5, twigs: 3, crownStart: 0.4, spread: [0.6, 1.2], lenRatio: 0.6, radRatio: 0.5,
    kink: 0.38, lift: 0.05, droop: 0.04, leafFrom: 9, leaves: false, cardsPer: 0, card: 1 }),
  bush: (r) => ({ grow: growBush, height: 1.1 + r() * 0.8, cards: 46, card: 0.75 }),
};

// ── materials ──────────────────────────────────────────────────────────────
// opts.live: wind and the near/far dissolve (the trees in the world);
// opts.foliage: one normal for both faces of a card, and light through it
function patchTree(mat, U, opts) {
  const live = !!opts.live, fol = !!opts.foliage;
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uWind = U.wind;
    sh.uniforms.uNear = U.near;
    sh.uniforms.uSunDir = U.sunDir;
    sh.uniforms.uSunCol = U.sunCol;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        attribute float sway;
        attribute float shade;
        uniform float uWind;
        varying vec3 vBase;
        varying vec3 vWPos;
        varying float vShade;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        vShade = shade;
        {
          #ifdef USE_INSTANCING
            mat4 im = modelMatrix * instanceMatrix;
          #else
            mat4 im = modelMatrix;
          #endif
          vBase = (im * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
          ${live ? `
          float ph = vBase.x * 0.31 + vBase.z * 0.23;
          float hgt = max(position.y, 0.0);
          float bend = sway * (0.035 + 0.012 * hgt) * (sin(uWind * 1.6 + ph) + 0.4 * sin(uWind * 3.7 + ph * 2.1));
          float flutter = sway * sway * 0.05 * sin(uWind * 9.0 + position.x * 3.0 + position.z * 2.0 + ph);
          transformed.x += bend + flutter;
          transformed.z += bend * 0.6 - flutter * 0.5;
          transformed.y += flutter * 0.4;` : ''}
          vWPos = (im * vec4(transformed, 1.0)).xyz;
        }`);
    let fs = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform float uNear;
        uniform vec3 uSunDir, uSunCol;
        varying vec3 vBase;
        varying vec3 vWPos;
        varying float vShade;
        float ign(vec2 p) { return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715)))); }`)
      .replace('#include <map_fragment>', `#include <map_fragment>
        diffuseColor.rgb *= vShade;`);
    if (live) {
      fs = fs.replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
        {
          float d = distance(vBase.xz, cameraPosition.xz);
          float f = smoothstep(uNear, uNear * 0.82, d);   // 1 near, 0 past the band
          // and nothing grows in the lens: leaves and twigs within a few
          // metres of the camera dissolve, so a chase camera behind the hero
          // never films the inside of a crown
          f *= smoothstep(1.6, 3.6, distance(vWPos, cameraPosition));
          if (ign(gl_FragCoord.xy) > f) discard;
        }`);
    }
    if (fol) {
      fs = fs
        .replace('#include <normal_fragment_begin>', `#include <normal_fragment_begin>
          normal = normalize(vNormal);           // both faces of a leaf face out of the crown
          nonPerturbedNormal = normal;
          {
            // ...but the side turned away from the light is the leaf's
            // underside: seen from below a crown is darker than from above
            float facing = dot(normal, normalize(vViewPosition));
            diffuseColor.rgb *= mix(0.55, 1.0, smoothstep(-0.55, 0.15, facing));
          }`)
        .replace('#include <opaque_fragment>', `{
            // light through the leaf: the sun behind a crown lights it from within
            vec3 Vw = normalize(cameraPosition - vWPos);
            float bl = pow(max(dot(-Vw, uSunDir), 0.0), 3.0);
            outgoingLight += diffuseColor.rgb * uSunCol * bl * 0.6 * vShade;
          }
          #include <opaque_fragment>`);
    }
    sh.fragmentShader = fs;
  };
  mat.customProgramCacheKey = () => 'flora-' + (live ? 'L' : 'B') + (fol ? 'F' : 'W');
}

function makeMaterials(kind, leafHSL, barkTex, barkN, seed, U) {
  const barkTint = kind === 'birch' ? new THREE.Color(0xe8e4dc) : kind === 'dead' ? new THREE.Color(0x9c8f84) : new THREE.Color(0xffffff);
  const bark = new THREE.MeshStandardMaterial({ map: barkTex, normalMap: barkN, color: barkTint, roughness: 0.95 });
  if (kind === 'birch') bark.map = null;
  bark.userData.noAutoTex = true;
  patchTree(bark, U, { live: true });
  let leaf = null;
  if (kind !== 'dead') {
    const ak = kind === 'pine' || kind === 'spruce' ? 'pine' : kind === 'palm' ? 'palm' : 'broad';
    // matte, and only half the sky's reflection: foliage is a scatterer,
    // and a glossy card under an open sky read as frosted
    leaf = new THREE.MeshStandardMaterial({
      map: foliageAtlas(ak, leafHSL, seed), alphaTest: 0.42, side: THREE.DoubleSide,
      roughness: 1.0, metalness: 0.0, envMapIntensity: 0.45,
    });
    leaf.alphaToCoverage = true;
    leaf.userData.noAutoTex = true;
    patchTree(leaf, U, { live: true, foliage: true });
  }
  return { bark, leaf };
}

// ── impostors ──────────────────────────────────────────────────────────────
const VIEWS = 8, CELL_W = 256, CELL_H = 384;

function bakeImpostors(renderer, variants, lightRig) {
  const rows = variants.length;
  const rt = new THREE.WebGLRenderTarget(CELL_W * VIEWS, CELL_H * rows, {
    type: THREE.HalfFloatType, samples: 4,
    minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter, generateMipmaps: true,
  });
  const sc = new THREE.Scene();
  for (const l of lightRig.lights) sc.add(l);
  if (lightRig.environment) { sc.environment = lightRig.environment; sc.environmentIntensity = lightRig.environmentIntensity ?? 1; }
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200);
  const prevRT = renderer.getRenderTarget();
  const prevClear = renderer.getClearColor(new THREE.Color()), prevAlpha = renderer.getClearAlpha();
  const prevAuto = renderer.autoClear;
  const prevTM = renderer.toneMapping;
  renderer.setClearColor(0x000000, 0);
  renderer.setRenderTarget(rt);
  renderer.clear(true, true, true);
  renderer.autoClear = false;
  const frames = [];
  variants.forEach((v, row) => {
    const grp = new THREE.Group();
    const bm = new THREE.Mesh(v.bark, v.matsBake.bark); grp.add(bm);
    if (v.leaf) grp.add(new THREE.Mesh(v.leaf, v.matsBake.leaf));
    sc.add(grp);
    const box = new THREE.Box3().setFromObject(grp);
    const hw = Math.max(Math.abs(box.min.x), box.max.x, Math.abs(box.min.z), box.max.z) * 1.04;
    const hTop = box.max.y * 1.03, hBot = Math.min(box.min.y, 0);
    // the cell's aspect is fixed; the frame fits the taller of width and height
    const fh = Math.max(hTop - hBot, hw * 2 * CELL_H / CELL_W);
    const fw = fh * CELL_W / CELL_H;
    cam.left = -fw / 2; cam.right = fw / 2; cam.top = fh; cam.bottom = 0;
    cam.updateProjectionMatrix();
    for (let k = 0; k < VIEWS; k++) {
      const a = (k / VIEWS) * TAU;
      // a level gaze: the camera sits at the base and the frame rises from it
      cam.position.set(Math.sin(a) * 60, hBot, Math.cos(a) * 60);
      cam.lookAt(0, hBot, 0);
      rt.viewport.set(k * CELL_W, row * CELL_H, CELL_W, CELL_H);
      rt.scissor.set(k * CELL_W, row * CELL_H, CELL_W, CELL_H);
      rt.scissorTest = true;
      renderer.setRenderTarget(rt);
      renderer.render(sc, cam);
    }
    frames.push({ w: fw, h: fh, base: hBot });
    sc.remove(grp);
  });
  rt.scissorTest = false;
  rt.viewport.set(0, 0, CELL_W * VIEWS, CELL_H * rows);
  renderer.autoClear = prevAuto;
  renderer.setRenderTarget(prevRT);
  renderer.setClearColor(prevClear, prevAlpha);
  renderer.toneMapping = prevTM;
  for (const l of lightRig.lights) sc.remove(l);
  return { tex: rt.texture, rt, frames, rows };
}

function farMaterial(atlas, row, U) {
  const m = new THREE.MeshBasicMaterial({ map: atlas.tex, alphaTest: 0.5, side: THREE.DoubleSide, fog: true });
  m.alphaToCoverage = true;
  m.userData.noAutoTex = true;
  const fr = atlas.frames[row];
  m.onBeforeCompile = (sh) => {
    sh.uniforms.uWind = U.wind;
    sh.uniforms.uNear = U.near;
    sh.uniforms.uRow = { value: row };
    sh.uniforms.uRows = { value: atlas.rows };
    sh.uniforms.uFrame = { value: new THREE.Vector2(fr.w, fr.h) };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec4 iPos;   // x y z scale
        attribute float iYaw;
        uniform float uWind, uRow, uRows;
        uniform vec2 uFrame;
        varying vec3 vBase;
        varying vec2 vCell;`)
      .replace('#include <uv_vertex>', `#include <uv_vertex>
        {
          vec3 base = iPos.xyz;
          vec3 toCam = cameraPosition - base;
          float az = atan(toCam.x, toCam.z) - iYaw;
          float fk = mod(floor(az / 6.2831853 * ${VIEWS}.0 + 0.5), ${VIEWS}.0);
          vCell = vec2(fk, uRow);
          vMapUv = vec2((fk + uv.x) / ${VIEWS}.0, (uRow + uv.y) / uRows);
        }`)
      .replace('#include <begin_vertex>', `
        vec3 base = iPos.xyz;
        vBase = base;
        vec3 toCam = normalize(vec3(cameraPosition.x - base.x, 0.0, cameraPosition.z - base.z));
        vec3 right = vec3(toCam.z, 0.0, -toCam.x);
        float ph = base.x * 0.31 + base.z * 0.23;
        vec3 transformed = base
          + right * (position.x * uFrame.x * iPos.w)
          + vec3(0.0, position.y * uFrame.y * iPos.w, 0.0);
        transformed.x += position.y * 0.025 * iPos.w * sin(uWind * 1.6 + ph);
        transformed.z += position.y * 0.015 * iPos.w * sin(uWind * 1.6 + ph);`)
      .replace('#include <project_vertex>', `
        vec4 mvPosition = viewMatrix * vec4(transformed, 1.0);
        gl_Position = projectionMatrix * mvPosition;`)
      .replace('#include <worldpos_vertex>', '');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform float uNear;
        varying vec3 vBase;
        float ign(vec2 p) { return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715)))); }`)
      .replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
        {
          float d = distance(vBase.xz, cameraPosition.xz);
          float f = smoothstep(uNear, uNear * 0.82, d);   // the near tree's share
          if (ign(gl_FragCoord.xy) <= f) discard;          // its complement
        }`);
  };
  m.customProgramCacheKey = () => 'flora-far-' + row;
  return m;
}

function farGeometry(list) {
  // list: Float32Array [x, y, z, scale, yaw] * n
  const n = list.length / 5;
  const q = new THREE.PlaneGeometry(1, 1);
  q.translate(0, 0.5, 0);
  const g = new THREE.InstancedBufferGeometry();
  g.index = q.index;
  g.setAttribute('position', q.getAttribute('position'));
  g.setAttribute('uv', q.getAttribute('uv'));
  g.setAttribute('normal', q.getAttribute('normal'));
  const pos = new Float32Array(n * 4), yaw = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    pos[i * 4] = list[i * 5]; pos[i * 4 + 1] = list[i * 5 + 1]; pos[i * 4 + 2] = list[i * 5 + 2];
    pos[i * 4 + 3] = list[i * 5 + 3]; yaw[i] = list[i * 5 + 4];
  }
  g.setAttribute('iPos', new THREE.InstancedBufferAttribute(pos, 4));
  g.setAttribute('iYaw', new THREE.InstancedBufferAttribute(yaw, 1));
  g.instanceCount = n;
  return g;
}

// ── the forest ─────────────────────────────────────────────────────────────
// opts:
//   renderer, scene, seed, kinds: [{kind, weight}], leaf: {h,s,l},
//   barkTex, barkN, lightRig: {lights: [cloned lights], environment, environmentIntensity},
//   windU: {value}, near: metres, variants: per kind,
//   trees: Float32Array [x, y, z, scale, yaw, kindIndex] * n (kindIndex into kinds)
//   shadows: bool
// returns { update(camera), count, kindsOf, dispose }
export function plantForest(o) {
  const U = { wind: o.windU || { value: 0 }, near: { value: o.near || 50 },
              sunDir: { value: (o.sunDir || new THREE.Vector3(0.4, 0.8, 0.3)).clone().normalize() },
              sunCol: { value: o.sunCol || new THREE.Color(1, 0.95, 0.85) } };
  const rng = mulberry(o.seed >>> 0);
  const kinds = o.kinds;
  const varPer = o.variants || 3;
  // grow the variants
  const variants = [];   // {kind, ki, bark, leaf, mats, matsBake}
  kinds.forEach((K, ki) => {
    const mats = makeMaterials(K.kind, o.leaf, o.barkTex, o.barkN, (o.seed + ki * 97) >>> 0, U);
    const matsBake = {
      bark: new THREE.MeshStandardMaterial({ map: mats.bark.map, normalMap: mats.bark.normalMap, color: mats.bark.color, roughness: 0.95 }),
      leaf: mats.leaf ? new THREE.MeshStandardMaterial({ map: mats.leaf.map, alphaTest: 0.42, side: THREE.DoubleSide, roughness: 1.0, envMapIntensity: 0.45 }) : null,
    };
    patchTree(matsBake.bark, U, {});
    if (matsBake.leaf) patchTree(matsBake.leaf, U, { foliage: true });
    for (let v = 0; v < varPer; v++) {
      const vr = mulberry((o.seed + ki * 1013 + v * 7919) >>> 0);
      const P = KINDS[K.kind](vr);
      const geo = P.grow(vr, P);
      variants.push({ kind: K.kind, ki, bark: geo.bark, leaf: geo.leaf, mats, matsBake, P });
    }
  });
  const atlas = bakeImpostors(o.renderer, variants, o.lightRig);
  // sort the trees into variants
  const T = o.trees, n = T.length / 6;
  const perVar = variants.map(() => []);
  const byKind = kinds.map((_, ki) => variants.map((v, vi) => v.ki === ki ? vi : -1).filter(x => x >= 0));
  for (let i = 0; i < n; i++) {
    const ki = T[i * 6 + 5] | 0;
    const opts = byKind[ki];
    const vi = opts[Math.floor(rng() * opts.length)];
    perVar[vi].push(T[i * 6], T[i * 6 + 1], T[i * 6 + 2], T[i * 6 + 3], T[i * 6 + 4]);
  }
  const group = new THREE.Group();
  group.name = 'flora';
  const far = [], near = [];
  const NEAR_CAP = o.nearCap || 900;
  variants.forEach((v, vi) => {
    const list = new Float32Array(perVar[vi]);
    if (!list.length) { far.push(null); near.push(null); return; }
    const fm = new THREE.Mesh(farGeometry(list), farMaterial(atlas, vi, U));
    fm.frustumCulled = false;
    fm.matrixAutoUpdate = false;
    group.add(fm);
    far.push(fm);
    const cap = Math.min(NEAR_CAP, list.length / 5);
    const nb = new THREE.InstancedMesh(v.bark, v.mats.bark, cap);
    nb.count = 0; nb.frustumCulled = false; nb.castShadow = !!o.shadows; nb.receiveShadow = true;
    group.add(nb);
    let nl = null;
    if (v.leaf) {
      nl = new THREE.InstancedMesh(v.leaf, v.mats.leaf, cap);
      nl.count = 0; nl.frustumCulled = false; nl.castShadow = !!o.shadows; nl.receiveShadow = true;
      group.add(nl);
    }
    near.push({ bark: nb, leaf: nl, cap, list });
  });
  o.scene.add(group);
  // a coarse grid for the near query
  const CELL = 24;
  const grid = new Map();
  near.forEach((nr, vi) => {
    if (!nr) return;
    const L = nr.list;
    for (let i = 0; i < L.length / 5; i++) {
      const key = Math.floor(L[i * 5] / CELL) + ',' + Math.floor(L[i * 5 + 2] / CELL);
      let a = grid.get(key); if (!a) grid.set(key, a = []);
      a.push(vi, i);
    }
  });
  const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), S = new THREE.Vector3(), V = new THREE.Vector3();
  const Yax = new THREE.Vector3(0, 1, 0);
  let lastX = 1e9, lastZ = 1e9;
  function update(camera) {
    const cx = camera.position.x, cz = camera.position.z;
    if ((cx - lastX) ** 2 + (cz - lastZ) ** 2 < 9) return;
    lastX = cx; lastZ = cz;
    const R = U.near.value + 4, R2 = R * R;
    for (const nr of near) if (nr) { nr.bark.count = 0; if (nr.leaf) nr.leaf.count = 0; }
    const gx0 = Math.floor((cx - R) / CELL), gx1 = Math.floor((cx + R) / CELL);
    const gz0 = Math.floor((cz - R) / CELL), gz1 = Math.floor((cz + R) / CELL);
    for (let gx = gx0; gx <= gx1; gx++) for (let gz = gz0; gz <= gz1; gz++) {
      const a = grid.get(gx + ',' + gz); if (!a) continue;
      for (let j = 0; j < a.length; j += 2) {
        const vi = a[j], i = a[j + 1], nr = near[vi], L = nr.list;
        const x = L[i * 5], z = L[i * 5 + 2];
        if ((x - cx) ** 2 + (z - cz) ** 2 > R2) continue;
        const c = nr.bark.count; if (c >= nr.cap) continue;
        const s = L[i * 5 + 3];
        Q.setFromAxisAngle(Yax, L[i * 5 + 4]);
        M.compose(V.set(x, L[i * 5 + 1], z), Q, S.set(s, s, s));
        nr.bark.setMatrixAt(c, M); nr.bark.count = c + 1;
        if (nr.leaf) { nr.leaf.setMatrixAt(c, M); nr.leaf.count = c + 1; }
      }
    }
    for (const nr of near) if (nr) {
      nr.bark.instanceMatrix.needsUpdate = true;
      if (nr.leaf) nr.leaf.instanceMatrix.needsUpdate = true;
    }
  }
  return {
    group, update, count: n, near: U.near,
    variants: variants.map(v => v.kind),
    tris: variants.map(v => (v.bark.index.count + (v.leaf ? v.leaf.index.count : 0)) / 3),
  };
}

// the leaf colour for a world: its words first, then its ground
export function leafFor(words, groundHSL) {
  const w = (words || '').toLowerCase();
  if (/autumn|fall\b|october|harvest|maple/.test(w)) return { h: 0.07, s: 0.72, l: 0.42 };
  if (/cherry|blossom|sakura/.test(w)) return { h: 0.94, s: 0.55, l: 0.78 };
  if (/haunted|cursed|dead|graveyard|swamp|toxic/.test(w)) return { h: 0.2, s: 0.28, l: 0.24 };
  if (/jungle|rainforest|tropical/.test(w)) return { h: 0.3, s: 0.62, l: 0.3 };
  if (/snow|winter|frozen|arctic|ice/.test(w)) return { h: 0.38, s: 0.32, l: 0.17 };
  if (/pine|spruce|fir|conifer|taiga/.test(w)) return { h: 0.33, s: 0.42, l: 0.17 };
  if (groundHSL && groundHSL.h > 0.16 && groundHSL.h < 0.45 && groundHSL.s > 0.12) {
    return { h: groundHSL.h + 0.02, s: Math.min(0.62, groundHSL.s + 0.12), l: 0.22 };
  }
  return { h: 0.27, s: 0.46, l: 0.22 };
}

// which trees a world grows, weighted
export function kindsFor(arch, words) {
  const w = (words || '').toLowerCase();
  if (/palm|tropical|beach|island|oasis/.test(w)) return [{ kind: 'palm', weight: 0.8 }, { kind: 'bush', weight: 0.6 }];
  if (/birch/.test(w)) return [{ kind: 'birch', weight: 1 }, { kind: 'bush', weight: 0.5 }];
  if (/oak|orchard|meadow|farm|village/.test(w)) return [{ kind: 'oak', weight: 0.7 }, { kind: 'broadleaf', weight: 0.5 }, { kind: 'bush', weight: 0.7 }];
  if (arch === 'pine') return [{ kind: 'pine', weight: 0.7 }, { kind: 'spruce', weight: 0.5 }, { kind: 'bush', weight: 0.25 }];
  if (arch === 'dead') return [{ kind: 'dead', weight: 1 }, { kind: 'bush', weight: 0.15 }];
  if (arch === 'cypress') return [{ kind: 'spruce', weight: 0.5 }, { kind: 'palm', weight: 0.3 }, { kind: 'bush', weight: 0.5 }];
  return [{ kind: 'broadleaf', weight: 0.7 }, { kind: 'oak', weight: 0.35 }, { kind: 'birch', weight: 0.2 }, { kind: 'bush', weight: 0.7 }];
}
