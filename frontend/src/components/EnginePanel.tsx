import React from 'react'

/**
 * ENGINES (2026-08-06)
 *
 * The facade and vehicle systems are the two places where the most engine
 * work is invisible from the outside: a player sees "a street", not that
 * every masonry wall is a generated grid of piers and spandrels with real
 * openings, or that six silhouettes come out of one parameterised shell.
 *
 * This panel is a SHOWCASE, not a control surface — it says what the
 * generator does so the studio stops looking like it only picks assets.
 * The numbers mirror _FACADE / CAR_TYPES in
 * backend/app/game_export/runtime/main.js.tpl; that file is the source of
 * truth, and if the two ever disagree, it wins.
 */

const FACADES: Array<[string, string, string]> = [
  ['Brick walk-up', '3.3m storey · 2.9m bay', 'punched openings, sill + lintel courses'],
  ['Cut ashlar', '3.6m storey · 3.4m bay', 'drawn coursing, joints carry their own relief'],
  ['Loft brick', '4.0m storey · 3.5m bay', 'tall industrial bays, deep reveals'],
  ['Panel concrete', '3.1m storey · 3.2m bay', 'formed panels, tie holes, wide glazing'],
  ['Stucco', '3.2m storey · 3.0m bay', 'rendered finish with rain staining'],
  ['Grand limestone', '4.2m storey · 3.8m bay', 'two-storey order, heaviest piers'],
  ['Glass curtain wall', 'photo + mullion fins', 'the one family that keeps a photo skin'],
]

const CARS: Array<[string, string]> = [
  ['Sedan', '4.55m · the baseline profile'],
  ['Coupe', '4.30m · lower roof, shorter cabin'],
  ['SUV', '4.85m · raised body, 0.41m wheels'],
  ['Pickup', '5.40m · forward cabin + bed sidewall'],
  ['Van', '5.25m · tall slab body, short nose'],
  ['Taxi', '4.60m · roof light, livery yellow'],
]

function Section({ title, blurb, children }: {
  title: string; blurb: string; children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <div>
        <h4 className="text-[11px] font-semibold text-[#d6c9ff]">{title}</h4>
        <p className="text-[10px] text-[#4a4764] leading-snug">{blurb}</p>
      </div>
      {children}
    </div>
  )
}

export default function EnginePanel() {
  return (
    <div className="space-y-3 max-h-[260px] overflow-y-auto pr-1">
      <Section
        title="Facade engine"
        blurb="Masonry buildings are not textured boxes. The wall is a grid of solid
               piers and spandrels standing 0.42m proud of a backing wall, so every
               window is a real opening with real jambs, head and sill. Heights snap
               to whole storeys, so a roofline never slices a window in half."
      >
        <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
          {FACADES.map(([name, dims, note]) => (
            <div key={name}
                 className="rounded-lg border border-[#a78bfa]/15 bg-black/25 px-2 py-1.5">
              <div className="text-[10.5px] text-[#c9c2e4]">{name}</div>
              <div className="text-[9.5px] font-mono text-[#6f6a8c]">{dims}</div>
              <div className="text-[9.5px] text-[#4a4764] leading-snug">{note}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Vehicle engine"
        blurb="One shell, six silhouettes. The side profile is a curve rather than a
               polyline, and the extrusion is drawn in at nose and tail with
               tumblehome above the beltline — which is what stops a car reading as
               a brick. Paint is low-metalness under clearcoat so colour survives
               at night."
      >
        <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
          {CARS.map(([name, note]) => (
            <div key={name}
                 className="rounded-lg border border-[#a78bfa]/15 bg-black/25 px-2 py-1.5">
              <div className="text-[10.5px] text-[#c9c2e4]">{name}</div>
              <div className="text-[9.5px] font-mono text-[#6f6a8c]">{note}</div>
            </div>
          ))}
        </div>
      </Section>

      <p className="text-[9.5px] text-[#4a4764] leading-snug">
        Both systems are seeded per building and per vehicle, so a rebuild with the
        same prompt gives the same street — and every game generated from here on
        inherits them without asking.
      </p>
    </div>
  )
}
