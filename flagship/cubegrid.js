// CUBE GRID — the spatial core for a multi-sided factory.
//
// Six N x N faces on a cube. A belt that runs off the top face heading east
// continues down the east face; a player who walks over an edge finds gravity
// rotate under them. That single idea is what separates this from every
// flat-ground automation game, and it lives or dies on this file being right.
//
// It is written as pure math with no Three.js and no rendering so it can be
// tested on its own. An edge-wrap that is subtly wrong does not crash — items
// just quietly teleport somewhere plausible, three hours into someone's save.
//
// CONVENTION: each face carries a right-handed basis (u, v, n) with u x v = n,
// n pointing OUT of the cube. A tile is [face, i, j] where i runs along u and
// j along v. Directions are 0..3 = +u, +v, -u, -v.

export const FACES = [
  // name        u              v               (n = u x v, checked in tests)
  { name: 'top', u: [1, 0, 0], v: [0, 0, -1] },   // n = +Y
  { name: 'bot', u: [1, 0, 0], v: [0, 0, 1] },    // n = -Y
  { name: 'east', u: [0, 0, -1], v: [0, -1, 0] }, // n = +X
  { name: 'west', u: [0, 0, 1], v: [0, -1, 0] },  // n = -X
  { name: 'south', u: [1, 0, 0], v: [0, -1, 0] }, // n = +Z
  { name: 'north', u: [-1, 0, 0], v: [0, -1, 0] },// n = -Z
];

export const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
export const neg = a => [-a[0], -a[1], -a[2]];
const eq = (a, b) => Math.abs(a[0] - b[0]) < 1e-9 &&
                     Math.abs(a[1] - b[1]) < 1e-9 && Math.abs(a[2] - b[2]) < 1e-9;

for (const f of FACES) f.n = cross(f.u, f.v);

/** Direction 0..3 as a world vector on a given face. */
export function dirVec(face, d) {
  const f = FACES[face];
  return [f.u, f.v, neg(f.u), neg(f.v)][d & 3];
}

/** World-space centre of tile [face,i,j] on a cube of N tiles at size T. */
export function tileWorld(face, i, j, N, T) {
  const f = FACES[face];
  const H = (N * T) / 2;
  const a = (i + 0.5 - N / 2) * T;
  const b = (j + 0.5 - N / 2) * T;
  return add(add(scale(f.n, H), scale(f.u, a)), scale(f.v, b));
}

/**
 * Step one tile from [face,i,j] heading d.
 *
 * Inside a face this is trivial. Crossing an edge is the whole point: the
 * destination face is the one whose normal matches the direction you walked
 * off in, and your heading there becomes "into the cube" — i.e. the OLD face's
 * inward normal. The new i/j are recovered by projecting the world position
 * onto the new face's basis, which avoids hand-writing twenty-four edge cases
 * and getting one of them wrong.
 */
export function stepTile(face, i, j, d, N) {
  const ni = i + [1, 0, -1, 0][d & 3];
  const nj = j + [0, 1, 0, -1][d & 3];
  if (ni >= 0 && nj >= 0 && ni < N && nj < N) return { face, i: ni, j: nj, d };

  const walkDir = dirVec(face, d);              // the way we went, in world
  const oldN = FACES[face].n;

  // the face we arrive on is the one facing the way we walked
  let dst = -1;
  for (let k = 0; k < 6; k++) if (eq(FACES[k].n, walkDir)) { dst = k; break; }
  if (dst < 0) return null;                     // unreachable for a cube

  // On the new face we are heading INTO where the old face was, which is the
  // old outward normal reversed.
  const newDirVec = neg(oldN);
  let nd = -1;
  for (let k = 0; k < 4; k++) if (eq(dirVec(dst, k), newDirVec)) { nd = k; break; }
  if (nd < 0) return null;

  // Recover the tile indices by projecting the world position of the tile we
  // just left onto the destination face's basis. The two faces share an edge,
  // so the coordinate along that edge is preserved exactly.
  const T = 1;                                  // unit tiles: indices only
  const w = tileWorld(face, i, j, N, T);
  const f = FACES[dst];
  const a = dot(w, f.u) / T + N / 2 - 0.5;
  const b = dot(w, f.v) / T + N / 2 - 0.5;
  const ri = Math.max(0, Math.min(N - 1, Math.round(a)));
  const rj = Math.max(0, Math.min(N - 1, Math.round(b)));
  return { face: dst, i: ri, j: rj, d: nd, wrapped: true };
}

/** Every face's outward normal, for gravity: standing on f, "up" is n. */
export function faceUp(face) { return FACES[face].n; }

/**
 * Which face a world point belongs to — the one whose normal it is furthest
 * along. Used when the player walks past an edge and has to be re-seated.
 */
export function faceOfPoint(p) {
  let best = 0, bestD = -Infinity;
  for (let k = 0; k < 6; k++) {
    const d = dot(p, FACES[k].n);
    if (d > bestD) { bestD = d; best = k; }
  }
  return best;
}
