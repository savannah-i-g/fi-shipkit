# Frame Family — deep design (2026-07-10, approved direction: "frame mode is perfect")

## Thesis

ISS-lineage ships are a **grammar, not a shape**: a spine reads as a sequence
of functional sections, each visually distinct, each honest about its job.
The generator therefore becomes a **slot sequencer** over a section library.
References: Savannah's KSP-style cruiser (stacked monocoque + livery), the
orbital station (wheel + clustered wings + amber panels), the Copernicus-class
nuclear tug (cage truss with tanks inside, shadow shield, fin radiators).

## Spine grammar

```
[BOW: node + dish(es) + capsule dome + optional docked craft]
[SLOT 1..6: each one of]
    0 skip          (nothing, spine shortens)
    1 stack module  (pressurised cylinder; livery band, windows, gold wrap,
                     end domes, RCS quads — all seeded/toggleable)
    2 truss         (open box truss, diagonals)
    3 tank bay      (truss cage with gold propellant spheres VISIBLE inside)
    4 node section  (docking node + radial stub modules + cupola)
    5 container rack(truss cage with cargo boxes inside — the frame hauler)
    6 reactor       (shadow-shield disc + dark reactor drum + radial fin
                     radiators + gold cap — the Copernicus signature)
[STERN (gated by Engines bool, off = station): shield disc + engine cluster
    (bell / aerospike / ion via Type) + flanking tanks]
```

Slot types come from **Auto Slots** (seeded, uniform 1..6) or six explicit
`Slot N Type` inputs for hand composition. Section lengths derive from a
`unit = Length/16`, so `Length` scales the whole sentence; module radius
derives from `Depth`. Cumulative x-positions are a chain of adds — the ship's
true length emerges from its sentence.

## Ship-level features (independent of slots)

- **Ring Style**: 0 = continuous torus hab (`FI_RingHab`), 1 = **spoke wheel**
  (`FI_SpokeWheel` — N hab capsules on radial arms, Hermes-style), placed at
  `Ring Position` (fraction along spine), gated by `Ring`.
- **Wings**: `Wing Pairs` at `Wing Position`, alternating cross config,
  seeded amber/blue; radiator pair always near the stern.
- **Dish Count** 1..3 at the bow, seeded aim variation.
- **Nav lights**: port red (+Y) / starboard green (−Y) emissive tips.
- **Gold Fraction**: per-stack-segment probability of MLI gold wrap.
- **Windows**: emissive warm window rows on stack segments (night-side read).
- **Docked Craft**: small crew capsule docked at a bow radial port.
- **Bow Style** (size classes, per Savannah "even small ships"): 0 = node +
  dish(es) (cruisers/stations), 1 = **cockpit capsule** — pressurised dome
  with a glass visor band, the small-craft read. With Length ~16–25 m and
  1–2 slots the same grammar yields work skiffs, shuttles and light tugs;
  nothing else changes (unit scaling carries it).

## New / upgraded groups

| group | job |
|---|---|
| `FI_TankBay` | truss cage + jittered gold spheres inside |
| `FI_ContainerRack` | truss cage + 2×3 cargo boxes, one seeded accent box |
| `FI_NodeSection` | node + up to 4 radial stub modules + cupola + docked craft |
| `FI_ReactorSection` | shadow shield, reactor drum, 8 radial fins, gold cap |
| `FI_SpokeWheel` | hub + arms + tangent hab capsules |
| `FI_EngineSection` | taper struts + shield disc + cluster + tanks |
| `FI_StackSegment` v2 | + End Caps, Windows, Gold, RCS, Seed (ADDITIVE) |
| `FI_FrameShip` v2 | the sequencer; existing 9 sockets frozen, ~14 appended |

New materials: `FI_Window` (warm emissive), `FI_NavRed`, `FI_NavGreen`.

## Contract & dispatch

All socket changes ADDITIVE (appended after existing creation order).
`FI_ShipGen` forwards `Ring Style` only; deep frame control is intended
through a direct `FI_FrameShip` modifier (the playground frame fleet binds
it directly). Blender 4.0 gotchas honoured throughout: geometry Switch bool
= `inputs[1]`, typed socket lookup, Points output named "Geometry".

## Verification

- Selftest: budgets for all six new groups; sequencer legs (slot type flips
  change checksum, Engines off shrinks, Ring Style torus≠spokes, Windows/
  Gold/Docked toggles live); renders per role.
- Playground v3 frame fleet: explorer (ring torus), tug (tanks+reactor),
  container hauler, science (dishes+booms), station (Engines off, wings
  maxed), spoke-wheel cruiser — plus the monohull corvette and Caldari slab
  for contrast.
- Engine landing: export explorer + tug + hauler as `.glb` via
  ship_export.py and confirm them in the target engine/renderer.

## Future (noted, not this wave)

Cross-truss station arms (±Y spine branches), counter-rotating ring pairs,
checker/flag livery via the bake stage, truss-mounted manipulator arm,
per-module UV + decal pass when textures land.
