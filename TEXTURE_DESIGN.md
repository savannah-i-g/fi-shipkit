# Frame textures + detail — design (2026-07-10)

## Basis: Savannah's Hull_Generator_HD method (from her hand-built corvette)

Her working recipe, kept as the foundation:
- **Brick Texture as panel grid** (per-panel colour cells), mixed with
  **Musgrave** for organic breakup — drives base colour AND metallic.
- **Tiling micro image texture** (+Brightness/Contrast) for surface detail.
- **Dual Bevel-node normals → Separate Blue → ColorRamp**: an edge-detection
  mask. Present in her graph but not yet driving a wear layer — "we just
  need edge wear etc".

## FI shader v2 grammar (applies her method across the frame palette)

| material | treatment |
|---|---|
| FI_ThermalWhite | brick panel-cell tint + musgrave breakup, micro noise bump, **edge wear** (bevel-normal mask, noise-broken, reveals dark bare metal), AO grime in cavities |
| FI_TrussMetal | stronger edge wear, oil-streak grime (stretched noise) |
| FI_MLIGold | high-frequency noise crinkle bump (foil), rough variation |
| FI_AccentRed/Blue | **worn paint**: edge mask reveals FI_ThermalWhite beneath |
| FI_SolarPanel/Amber | brick cell grid (solar cells), slight facet rough variation |

Edge mask recipe (hers, cleaned): `dot(Bevel(N, r), Normal)` → ramp → multiply
by noise breakup. Bevel + AO are Cycles-only: viewport shows base colours,
bakes are fully detailed — correct split, since the engine consumes BAKES.

## Detail setting (her ask: low poly as a LEVEL, not a ceiling)

`FI_FrameShip.Detail` (int 0/1/2, default 0) → int-switched segment counts
plumbed into every curved component (stack cylinders 14/20/28, domes/tanks
10/14/20, bells 12/18/24, ring/wheel/cockpit likewise). Additive "Segments"
sockets on components; low poly remains default.

## Reliable UVs + bake pipeline (bake_ship.py)

GN emits no UVs; unwrap happens deterministically at bake time:
realize → join per material → **Smart UV Project** (island margin 0.02)
→ Cycles bake per part set: albedo (diffuse colour), ORM (AO/rough/metal
packed engine-style), emissive, normal (from procedural bumps) → 8-bit PNGs
→ assign to plain Principled export materials → textured `.glb`.
Default 1024², 16 samples (procedural = converges fast);
`--res 2048` for hero bakes.

## Removal (same wave)

Monohull + Slab families deleted (FI_MonohullShip, FI_SlabShip, FI_ShipGen,
FI_TaperProfile, FI_HullLoft, FI_EngineBlock, FI_PipeRun). FI_FrameShip is
THE generator. KEPT despite the purge: FI_Panelize / FI_GreebleScatter /
RCS / mast / radiator groups — downstream dress-pass files link them
(the hand-corvette dress pass predates the generator and stays
supported). BREAKING for shipgen_playground.blend only (regenerated).
