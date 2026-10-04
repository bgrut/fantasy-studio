// ── GROUND THAT IS DRAWN, NOT PHOTOGRAPHED (2026-10-03) ─────────────────────
// snow.jpg is a close-up of wind ripples. Tiled every four and a half metres
// under a mountaineer it became a regular field of blue waves, the scene
// survey's alpine blizzard standing on what read as rippled sand. Fresh snow
// is mostly flat white: soft drifts a few metres across, a fine grain, and
// the odd sparkle where a crystal catches the light. Drawn here, tileable,
// once per game.
import * as THREE from 'three';

function tileNoise(seed, P) {
  // value noise on a lattice that wraps every P cells, so the texture tiles
  const h = new Float32Array(P * P);
  let s = seed >>> 0;
  for (let i = 0; i < P * P; i++) { s = (s * 1664525 + 1013904223) >>> 0; h[i] = s / 4294967296; }
  return (x, y) => {
    const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const at = (a, b) => h[(((b % P) + P) % P) * P + (((a % P) + P) % P)];
    return at(xi, yi) * (1 - u) * (1 - v) + at(xi + 1, yi) * u * (1 - v)
         + at(xi, yi + 1) * (1 - u) * v + at(xi + 1, yi + 1) * u * v;
  };
}

/** albedo and normal map for fresh snow, repeating `rep` times across the ground */
export function snowTextures(rep, aniso = 8, N = 512) {
  const n4 = tileNoise(71, 4), n8 = tileNoise(73, 8), n16 = tileNoise(79, 16), n64 = tileNoise(83, 64), n128 = tileNoise(89, 128);
  const H = new Float32Array(N * N);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const u = x / N, v = y / N;
    // drifts (large, soft), then a little unevenness, then the grain
    H[y * N + x] = n4(u * 4, v * 4) * 0.55 + n8(u * 8, v * 8) * 0.3 + n16(u * 16, v * 16) * 0.12
                 + n64(u * 64, v * 64) * 0.025 + n128(u * 128, v * 128) * 0.015;
  }
  const ca = document.createElement('canvas'), cn = document.createElement('canvas');
  ca.width = ca.height = cn.width = cn.height = N;
  const ga = ca.getContext('2d'), gn = cn.getContext('2d');
  const ia = ga.createImageData(N, N), inn = gn.createImageData(N, N);
  let s = 977;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const i = y * N + x, k = i * 4;
    const hx = H[y * N + ((x + 1) % N)] - H[y * N + ((x + N - 1) % N)];
    const hy = H[((y + 1) % N) * N + x] - H[((y + N - 1) % N) * N + x];
    // normal: gentle; the drifts are read from the light, not drawn as lines
    const sc = 9.0;
    let nx = -hx * sc, ny = -hy * sc, nz = 1;
    const nl = Math.hypot(nx, ny, nz); nx /= nl; ny /= nl; nz /= nl;
    inn.data[k] = (nx * 0.5 + 0.5) * 255; inn.data[k + 1] = (ny * 0.5 + 0.5) * 255; inn.data[k + 2] = (nz * 0.5 + 0.5) * 255; inn.data[k + 3] = 255;
    // albedo: near white, the hollows a touch cooler, a sparkle now and then
    const hv = H[i];
    let r = 0.94 + (hv - 0.5) * 0.05, g = 0.955 + (hv - 0.5) * 0.04, b = 0.975 + (hv - 0.5) * 0.02;
    if (rnd() < 0.0035) { r = g = b = 1.0; }
    ia.data[k] = Math.min(255, r * 255); ia.data[k + 1] = Math.min(255, g * 255); ia.data[k + 2] = Math.min(255, b * 255); ia.data[k + 3] = 255;
  }
  ga.putImageData(ia, 0, 0); gn.putImageData(inn, 0, 0);
  const mk = (c, srgb) => {
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(rep, rep);
    t.anisotropy = aniso;
    if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    return t;
  };
  return { map: mk(ca, true), normalMap: mk(cn, false) };
}
