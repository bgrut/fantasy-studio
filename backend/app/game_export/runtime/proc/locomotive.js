// proc:locomotive (2026-10-22). A train hero is cast as this module so the
// planner never sends a locomotive to image-to-3D. The runtime builds the
// engine itself (buildLoco in main.js.tpl) on its line; this module exists so
// the export can verify the asset and so anything importing it gets a group.
import * as THREE from 'three';

export default function createLocomotive() {
  const g = new THREE.Group();
  g.name = 'locomotive-placeholder';
  return g;
}
