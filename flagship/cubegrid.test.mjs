// Tests for the cube coordinate core. Run: node cubegrid.test.mjs
//
// Every one of these is a property that, if broken, produces no crash and no
// visible error — just items quietly arriving somewhere wrong. That is the
// entire reason this file exists before any rendering does.
import { FACES, stepTile, tileWorld, dirVec, cross, dot, faceOfPoint }
  from './cubegrid.js';

const N = 8, T = 2;
let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) pass++; else { fail++; console.log('  FAIL ' + msg); } };

// 1. every basis is right-handed and axis-aligned
for (const f of FACES) {
  const n = cross(f.u, f.v);
  ok(Math.abs(dot(n, n) - 1) < 1e-9, `${f.name}: normal is unit`);
  ok(Math.abs(dot(f.u, f.v)) < 1e-9, `${f.name}: u perpendicular to v`);
}
// 2. six distinct normals — a duplicate would silently merge two faces
{
  const seen = new Set(FACES.map(f => f.n.join(',')));
  ok(seen.size === 6, `six distinct face normals (got ${seen.size})`);
}

// 3. inside a face, stepping stays on the face and moves exactly one tile
{
  const r = stepTile(0, 3, 3, 0, N);
  ok(r.face === 0 && r.i === 4 && r.j === 3, 'interior step moves one tile');
}

// 4. THE PROPERTY THAT MATTERS: walking off any edge, from any tile, in any
//    direction, always lands somewhere legal on a different face.
{
  let bad = 0, wraps = 0;
  for (let f = 0; f < 6; f++) {
    for (let i = 0; i < N; i++) {
      for (let j = 0; j < N; j++) {
        for (let d = 0; d < 4; d++) {
          const r = stepTile(f, i, j, d, N);
          if (!r) { bad++; continue; }
          if (r.wrapped) {
            wraps++;
            if (r.face === f) bad++;                       // must change face
            if (r.i < 0 || r.j < 0 || r.i >= N || r.j >= N) bad++;
          }
        }
      }
    }
  }
  ok(bad === 0, `every edge crossing is legal (${bad} bad of ${wraps} wraps)`);
  ok(wraps === 6 * N * 4, `edge crossings happen where expected (${wraps})`);
}

// 5. an edge crossing does not teleport: the tile you arrive on is adjacent in
//    WORLD space to the one you left
{
  let worst = 0;
  for (let f = 0; f < 6; f++) {
    for (let i = 0; i < N; i++) {
      for (let d = 0; d < 4; d++) {
        for (const j of [0, N - 1]) {
          const r = stepTile(f, i, j, d, N);
          if (!r || !r.wrapped) continue;
          const a = tileWorld(f, i, j, N, T);
          const b = tileWorld(r.face, r.i, r.j, N, T);
          const dist = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
          worst = Math.max(worst, dist);
        }
      }
    }
  }
  // neighbours across an edge sit at most one tile diagonal apart
  ok(worst <= T * 1.75, `no teleports across edges (worst ${worst.toFixed(2)}m)`);
}

// 6. the arrival heading points INTO the new face, i.e. away from its edge —
//    a belt that wraps must keep running, not immediately run back off
{
  let bad = 0;
  for (let f = 0; f < 6; f++) {
    for (let d = 0; d < 4; d++) {
      const i = d === 0 ? N - 1 : d === 2 ? 0 : 3;
      const j = d === 1 ? N - 1 : d === 3 ? 0 : 3;
      const r = stepTile(f, i, j, d, N);
      if (!r || !r.wrapped) continue;
      const nxt = stepTile(r.face, r.i, r.j, r.d, N);
      if (!nxt) { bad++; continue; }
      if (nxt.face !== r.face) bad++;      // should travel INTO the new face
    }
  }
  ok(bad === 0, `wrapped heading continues onto the new face (${bad} bad)`);
}

// 7. every tile's world position is actually on its own face
{
  let bad = 0;
  for (let f = 0; f < 6; f++) {
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
      if (faceOfPoint(tileWorld(f, i, j, N, T)) !== f) bad++;
    }
  }
  ok(bad === 0, `faceOfPoint agrees with tileWorld (${bad} bad)`);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
