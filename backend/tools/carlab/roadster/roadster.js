// classic white roadster — img2threejs sculpt (blockout + form + material in
// one module; the passes share every helper). Spec: object-sculpt-spec.json.
// +Z nose, Y up, metres. Every node the actionReadiness contract promises
// exists by name: wheel-FL-steer / wheel-FR-steer (yaw), wheel-XX-spin (all
// four), so an engine can drive steering and rolling without guessing.
import * as THREE from 'three';

const L = 3.95, W = 1.62;
const WHEEL_R = 0.315, TIRE_T = 0.115, AXLE_F = 1.18, AXLE_R = -1.17;
const TRACK = 0.72;                        // hub |x|
const HUB_Y = WHEEL_R;                     // axle height

// Side profile in (z, y): the identity curve — low nose, falling bonnet,
// cowl rise, long haunch crest behind the door, tucked tail.
const TOP = [
  [1.975, 0.40], [1.80, 0.50], [1.35, 0.585], [0.85, 0.635],
  [0.50, 0.72], [0.30, 0.86],                       // cowl rise
  [-0.40, 0.90], [-0.95, 0.845],                    // haunch
  [-1.55, 0.72], [-1.85, 0.56], [-1.975, 0.44],
];
const SILL_Y = 0.155;

function bodyShape() {
  // outline runs nose-top -> tail-top -> tail-bottom -> arches -> nose-bottom
  const s = new THREE.Shape();
  s.moveTo(TOP[0][0], TOP[0][1]);
  for (let i = 1; i < TOP.length; i++) s.lineTo(TOP[i][0], TOP[i][1]);
  s.lineTo(-1.975, SILL_Y);
  s.lineTo(1.975, SILL_Y);                 // sill line, arches cut as holes
  s.closePath();
  for (const cx of [AXLE_R, AXLE_F]) {
    const h = new THREE.Path();
    const r = WHEEL_R + 0.13;
    h.moveTo(cx + r, SILL_Y - 0.001);
    // half-disc arch opening upward from the sill
    for (let i = 0; i <= 16; i++) {
      const a = Math.PI * (i / 16);
      h.lineTo(cx + Math.cos(a) * r, SILL_Y - 0.001 + Math.sin(a) * r);
    }
    h.closePath();
    s.holes.push(h);
  }
  return s;
}

// plan taper + tumblehome, the engine's own proven anti-box deformation:
// width pulls in toward nose and tail, glasshouse leans inboard above the
// beltline, roofline crowns slightly.
function carveShell(geo) {
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const z = p.getY(i) === undefined ? 0 : 0;      // placate linters
  }
  for (let i = 0; i < p.count; i++) {
    const zz = p.getX(i);                  // extrude axis BEFORE rotation: x=profile z
    const yy = p.getY(i);
    const xx = p.getZ(i);                  // width axis
    const t = (1.975 - zz) / L;            // 0 nose .. 1 tail
    const nose = Math.min(1, t / 0.20), tail = Math.min(1, (1 - t) / 0.16);
    const plan = 1 - 0.16 * (1 - nose) - 0.12 * (1 - tail);
    const above = Math.max(0, (yy - 0.62) / 0.30);
    const lean = 1 - 0.22 * above * above;
    p.setZ(i, xx * plan * lean);
  }
  geo.computeVertexNormals();
  return geo;
}

function extrudeBody(mat) {
  const geo = new THREE.ExtrudeGeometry(bodyShape(), {
    depth: W, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.045,
    bevelSegments: 3, curveSegments: 24,
  });
  // shape was authored in (z, y); extrusion ran along +Z(shape) = car width.
  geo.translate(0, 0, -W / 2);
  carveShell(geo);
  geo.rotateY(Math.PI / 2);                // profile z -> world z, width -> x
  const m = new THREE.Mesh(geo, mat);
  m.castShadow = m.receiveShadow = true;
  return m;
}

function softTop(M) {
  // truncated wedge dome: screen header back to deck, bow seams as ridges
  const s = new THREE.Shape();
  s.moveTo(0.28, 0.86);
  s.lineTo(0.16, 1.06);
  s.quadraticCurveTo(-0.25, 1.135, -0.62, 1.08);
  s.lineTo(-0.95, 0.845);
  s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, {
    depth: W * 0.76, bevelEnabled: true, bevelThickness: 0.03,
    bevelSize: 0.035, bevelSegments: 2, curveSegments: 12,
  });
  geo.translate(0, 0, -W * 0.76 / 2);
  const p = geo.attributes.position;      // soft tumblehome on the canopy too
  for (let i = 0; i < p.count; i++) {
    const above = Math.max(0, (p.getY(i) - 0.86) / 0.28);
    p.setZ(i, p.getZ(i) * (1 - 0.30 * above * above));
  }
  geo.computeVertexNormals();
  geo.rotateY(Math.PI / 2);
  const top = new THREE.Mesh(geo, M.canvas);
  top.castShadow = true;
  // three bow seams: thin torus segments draped across the canopy
  const g = new THREE.Group();
  g.add(top);
  for (const z of [-0.05, -0.35, -0.62]) {
    const seam = new THREE.Mesh(
      new THREE.TorusGeometry(0.62, 0.008, 6, 24, Math.PI * 0.78), M.canvas);
    seam.rotation.set(0, Math.PI / 2, Math.PI * 0.11);
    seam.position.set(0, 0.52, z);
    g.add(seam);
  }
  return g;
}

function windscreen(M) {
  const g = new THREE.Group();
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(1.18, 0.30), M.glass);
  glass.rotation.x = -0.42;
  glass.position.set(0, 0.985, 0.235);
  g.add(glass);
  const frame = new THREE.Mesh(
    new THREE.TorusGeometry(0.60, 0.016, 8, 20, Math.PI), M.chrome);
  frame.rotation.set(-0.42 + Math.PI / 2, 0, 0);
  frame.position.set(0, 0.985, 0.235);
  frame.scale.set(1, 0.52, 1);
  g.add(frame);
  return g;
}

function bumper(M, zFace, sign) {
  const g = new THREE.Group();
  const blade = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.085, 0.075), M.chrome);
  blade.position.set(0, 0.315, zFace);
  // wrap: bend the blade tips back with two short angled end caps
  for (const sx of [-1, 1]) {
    const cap = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.085, 0.07), M.chrome);
    cap.position.set(sx * 0.82, 0.315, zFace - sign * 0.055);
    cap.rotation.y = sx * sign * 0.55;
    g.add(cap);
  }
  const insert = new THREE.Mesh(new THREE.BoxGeometry(1.46, 0.03, 0.078), M.insert);
  insert.position.set(0, 0.315, zFace + sign * 0.002);
  const bkt = new THREE.BoxGeometry(0.05, 0.05, 0.10);
  for (const sx of [-0.5, 0.5]) {
    const b = new THREE.Mesh(bkt, M.black);
    b.position.set(sx, 0.315, zFace - sign * 0.08);
    g.add(b);
  }
  g.add(blade); g.add(insert);
  g.traverse(o => { if (o.isMesh) o.castShadow = true; });
  return g;
}

function headlampPair(M) {
  const g = new THREE.Group();
  for (const sx of [-0.52, 0.52]) {
    const bezel = new THREE.Mesh(
      new THREE.CylinderGeometry(0.115, 0.125, 0.10, 24), M.chrome);
    bezel.rotation.x = Math.PI / 2 - 0.06;
    bezel.position.set(sx, 0.50, 1.875);
    const lens = new THREE.Mesh(
      new THREE.SphereGeometry(0.095, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2),
      new THREE.MeshPhysicalMaterial({ color: 0xd8e2ec, metalness: 0.1,
        roughness: 0.12, clearcoat: 1 }));
    lens.rotation.x = Math.PI / 2 - 0.06;
    lens.position.set(sx, 0.50, 1.915);
    g.add(bezel, lens);
    const ind = new THREE.Mesh(new THREE.SphereGeometry(0.037, 12, 8), M.amber);
    ind.position.set(sx * 1.26, 0.365, 1.90);
    g.add(ind);
  }
  g.traverse(o => { if (o.isMesh) o.castShadow = true; });
  return g;
}

function wheel(M, pos) {
  // hierarchy: [steer?] -> spin -> (tire, barrel, 12 spokes, cap)
  const spin = new THREE.Group();
  spin.name = `wheel-${pos}-spin`;
  const tire = new THREE.Mesh(
    new THREE.TorusGeometry(WHEEL_R - TIRE_T / 2, TIRE_T, 14, 28), M.rubber);
  tire.rotation.y = Math.PI / 2;
  const barrel = new THREE.Mesh(
    new THREE.CylinderGeometry(WHEEL_R - TIRE_T, WHEEL_R - TIRE_T, 0.09, 24),
    M.black);
  barrel.rotation.z = Math.PI / 2;
  spin.add(tire, barrel);
  const spokeG = new THREE.BoxGeometry(0.055, WHEEL_R - TIRE_T - 0.02, 0.028);
  // two fans, one per wheel face — rotation about X keeps every spoke in the
  // wheel plane (axis = x); the earlier extra yaw threw the fan out of plane
  // and hid all twelve behind the barrel
  for (const fx of [-0.055, 0.055]) {
    for (let i = 0; i < 12; i++) {
      const holder = new THREE.Group();
      const sp = new THREE.Mesh(spokeG, M.rim);
      sp.position.y = (WHEEL_R - TIRE_T) / 2;
      holder.add(sp);
      holder.position.x = fx;
      holder.rotation.x = (i / 12) * Math.PI * 2;
      spin.add(holder);
    }
  }
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.06, 14, 10), M.chrome);
  cap.scale.set(1.6, 1, 1);
  spin.add(cap);
  spin.traverse(o => { if (o.isMesh) o.castShadow = true; });
  return spin;
}

function interior(M) {
  const g = new THREE.Group();
  for (const sx of [-0.33, 0.33]) {
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.30, 0.42), M.cabin);
    seat.position.set(sx, 0.62, -0.42);
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.42, 0.10), M.cabin);
    back.position.set(sx, 0.86, -0.62);
    back.rotation.x = 0.18;
    g.add(seat, back);
  }
  const dash = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.14, 0.22), M.black);
  dash.position.set(0, 0.80, 0.12);
  g.add(dash);
  const rimW = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.014, 8, 20), M.black);
  rimW.rotation.x = -0.9;
  rimW.position.set(-0.33, 0.84, -0.10);
  g.add(rimW);
  return g;
}

export function createRoadster() {
  const M = {
    paint: new THREE.MeshPhysicalMaterial({ color: 0xf2efe8, metalness: 0.1,
      roughness: 0.25, clearcoat: 1.0, clearcoatRoughness: 0.06 }),
    black: new THREE.MeshStandardMaterial({ color: 0x141416, roughness: 0.7 }),
    canvas: new THREE.MeshPhysicalMaterial({ color: 0xd4222c, metalness: 0,
      roughness: 0.85, sheen: 0.45, sheenColor: 0xd24a52, sheenRoughness: 0.6 }),
    chrome: new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 1.0,
      roughness: 0.08 }),
    rubber: new THREE.MeshStandardMaterial({ color: 0x17181a, roughness: 0.92 }),
    rim: new THREE.MeshStandardMaterial({ color: 0xb81f26, metalness: 0.3,
      roughness: 0.45 }),
    glass: new THREE.MeshPhysicalMaterial({ color: 0x9fb4c4, metalness: 0,
      roughness: 0.05, transparent: true, opacity: 0.35 }),
    amber: new THREE.MeshStandardMaterial({ color: 0xe07818, roughness: 0.3,
      emissive: 0x301000 }),
    cabin: new THREE.MeshStandardMaterial({ color: 0xa82830, roughness: 0.6 }),
    insert: new THREE.MeshStandardMaterial({ color: 0xc02026, roughness: 0.5 }),
  };

  const root = new THREE.Group();
  root.name = 'roadster-root';
  root.add(extrudeBody(M.paint));

  // satin black sill band under the doors
  const sill = new THREE.Mesh(new THREE.BoxGeometry(1.28, 0.075, 2.3), M.black);
  sill.position.set(0, SILL_Y - 0.02, 0);
  root.add(sill);

  root.add(softTop(M));
  root.add(windscreen(M));
  root.add(bumper(M, 1.99, 1));
  const rear = bumper(M, -1.99, -1);
  root.add(rear);
  root.add(headlampPair(M));

  // door handles at the beltline
  for (const sx of [-1, 1]) {
    const h = new THREE.Mesh(new THREE.BoxGeometry(0.022, 0.022, 0.14), M.chrome);
    h.position.set(sx * 0.74, 0.60, -0.12);
    root.add(h);
  }
  // nose crest: tiny extruded shield
  const crest = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.02, 0.012, 6),
    M.insert);
  crest.rotation.x = Math.PI / 2 + 0.35;
  crest.position.set(0, 0.52, 1.965);
  root.add(crest);

  root.add(interior(M));

  // tail lamps (inferred, round, red)
  for (const sx of [-0.55, 0.55]) {
    const t = new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 8),
      new THREE.MeshStandardMaterial({ color: 0xa01820, roughness: 0.3,
        emissive: 0x300000 }));
    t.position.set(sx, 0.42, -1.965);
    root.add(t);
  }

  const wheels = { spins: [], steers: [] };
  for (const [pos, x, z, front] of [
    ['FL', -TRACK, AXLE_F, true], ['FR', TRACK, AXLE_F, true],
    ['RL', -TRACK, AXLE_R, false], ['RR', TRACK, AXLE_R, false]]) {
    const spin = wheel(M, pos);
    wheels.spins.push(spin);
    if (front) {
      const steer = new THREE.Group();
      steer.name = `wheel-${pos}-steer`;
      steer.add(spin);
      steer.position.set(x, HUB_Y, z);
      wheels.steers.push(steer);
      root.add(steer);
    } else {
      spin.position.set(x, HUB_Y, z);
      root.add(spin);
    }
  }

  // action API the engine contract promised
  root.userData.drive = {
    setSteer(rad) { for (const s of wheels.steers) s.rotation.y = rad; },
    spin(dRad) { for (const s of wheels.spins) s.rotation.x += dRad; },
  };
  return root;
}
