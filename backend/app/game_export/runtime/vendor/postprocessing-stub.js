// Stub for the "postprocessing" (pmndrs) package: n8ao imports it only for
// its optional N8AOPostPass variant, which this runtime never uses (we use
// N8AOPass with the three/examples EffectComposer). A minimal Pass shape
// satisfies the import without shipping the real 300KB library.
export class Pass {
  constructor() { this.enabled = true; this.needsSwap = true; }
  render() {}
  setSize() {}
  dispose() {}
}
