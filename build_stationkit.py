#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# build_stationkit.py -- FI_StationKit.blend: the FI STATION generator —
# orbital habitats and industry in the EVE register (her 5 references:
# gantry yards, stacked-city spire citadels, radial saucer hubs, armored
# monolith bastions).
#
#   blender -b --python build_stationkit.py -- [--out FI_StationKit.blend]
#
# HOUSE LANGUAGE:
#   - the core is the fleet slab loft STOOD ON END: cube-grid lofted
#     along Z, corner-cut octagon footprints, radial-by-instancing (no
#     mirror pass — stations have no port/starboard)
#   - unit-space fi_u captured FIRST; all region selections test it;
#     tv = fi_u.z + 0.5 is the station's vertical coordinate
#   - every feature is a boss() on the closed grid — towers grow UP AND
#     DOWN from the caps, ledges/trenches ring the flanks; no booleans
#   - the dressing chain (divider -> patchwork -> relief -> weld ->
#     fi_light) is FACTORED into FI_StationDress so arms/maw slabs get
#     the same inhabited skin as the core
#   - fleet faction palettes NAV/OXR/NYX plus FPT "Freeport": grimy
#     gunmetal, sodium-amber lights — the unaligned industrial register

import bpy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fi_gn_lib import (G, TAU, boss, gcall, group_in, in_sock,  # noqa
                       out_sock, mat, _prim, _shader_wear, _base_flat,
                       _base_patchwork, fi_deps)
import build_fleetkit as fleet  # __main__-guarded; fixture builders reused

HERE = os.path.dirname(os.path.abspath(__file__))

DEP_WANT = ["Mesh Face Divider"]


def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = os.path.join(HERE, "FI_StationKit.blend")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    return out


# ---------------------------------------------------------- materials ------
# NAV/OXR/NYX palettes are verbatim fleet (stations are their home ports and
# must colour-match the ships); FPT is the 4th, unaligned freeport faction.

FACS = {
    "NAV": dict(base=(0.35, 0.42, 0.43), accent=(0.85, 0.42, 0.08),
                accent2=(0.82, 0.78, 0.68), deck=(0.10, 0.11, 0.12),
                decal=(0.92, 0.92, 0.90), light=(1.0, 0.85, 0.55),
                glow=(0.55, 0.75, 1.00), wear=0.15, grime=0.10),
    "OXR": dict(base=(0.55, 0.25, 0.12), accent=(0.72, 0.42, 0.10),
                accent2=(0.85, 0.77, 0.60), deck=(0.16, 0.09, 0.06),
                decal=(0.90, 0.86, 0.78), light=(1.0, 0.75, 0.45),
                glow=(1.00, 0.85, 0.60), wear=0.30, grime=0.25),
    "NYX": dict(base=(0.16, 0.16, 0.18), accent=(0.60, 0.08, 0.06),
                accent2=(0.80, 0.80, 0.78), deck=(0.06, 0.06, 0.07),
                decal=(0.85, 0.85, 0.85), light=(1.0, 0.45, 0.30),
                glow=(1.00, 0.30, 0.15), wear=0.20, grime=0.15),
    "FPT": dict(base=(0.13, 0.12, 0.11), accent=(0.62, 0.51, 0.13),
                accent2=(0.45, 0.44, 0.42), deck=(0.05, 0.05, 0.05),
                decal=(0.75, 0.72, 0.65), light=(1.0, 0.62, 0.20),
                glow=(1.00, 0.55, 0.15), wear=0.45, grime=0.40),
}


def build_station_materials():
    m = {}
    # generic roles — the fleet fixture builders index these exact keys
    m["dark"] = mat("FI_Station_Dark", (0.08, 0.08, 0.09), 0.7, 0.4)
    m["cavity"] = mat("FI_Station_Cavity", (0.03, 0.03, 0.04), 0.9, 0.1)
    m["metal"] = mat("FI_Station_Metal", (0.32, 0.33, 0.35), 0.5, 0.8)
    m["slat"] = mat("FI_Station_Slat", (0.78, 0.75, 0.66), 0.6, 0.2)
    m["radome"] = mat("FI_Station_Radome", (0.85, 0.85, 0.83), 0.5, 0.1)
    m["decalw"] = mat("FI_Station_DecalW", (0.92, 0.92, 0.90), 0.5, 0.0)
    m["tiplight"] = mat("FI_Station_TipLight", (0.10, 0.09, 0.06), 0.4, 0.0,
                        emissive=(1.0, 0.85, 0.55), estrength=5.0)
    m["glow_generic"] = mat("FI_Station_GlowG", (0.05, 0.05, 0.06), 0.5, 0.0,
                            emissive=(0.75, 0.85, 1.0), estrength=5.0)
    # station-only roles
    m["truss"] = mat("FI_Station_Truss", (0.14, 0.14, 0.16), 0.6, 0.6)
    m["pad"] = mat("FI_Station_Pad", (0.05, 0.05, 0.05), 0.9, 0.05)
    m["padlight"] = mat("FI_Station_PadLight", (0.06, 0.10, 0.07), 0.4, 0.0,
                        emissive=(0.55, 1.0, 0.7), estrength=8.0)
    m["beacon"] = mat("FI_Station_Beacon", (0.10, 0.02, 0.02), 0.4, 0.0,
                      emissive=(1.0, 0.12, 0.08), estrength=15.0)
    for key, f in FACS.items():
        hull = mat(f"FI_Station_{key}_Hull", f["base"], 0.5, 0.2)
        _shader_wear(hull, lambda nt, k=key: _base_patchwork(nt, FACS[k]),
                     wear=f["wear"], grime=f["grime"], rough=0.5,
                     metal=0.2, bump_str=0.02, seam=0.12,
                     emit=(f["light"], 5.0))
        m[f"hull_{key}"] = hull
        acc = mat(f"FI_Station_{key}_Accent", f["accent"], 0.5, 0.1)
        _shader_wear(acc, lambda nt, k=key: _base_flat(
                         nt, FACS[k]["accent"]),
                     wear=f["wear"] * 0.8, grime=f["grime"] * 0.6,
                     wear_col=(0.35, 0.34, 0.33), rough=0.5, metal=0.1,
                     bump_str=0.02)
        m[f"accent_{key}"] = acc
        m[f"deck_{key}"] = mat(f"FI_Station_{key}_Deck", f["deck"],
                               0.85, 0.05)
        m[f"decal_{key}"] = mat(f"FI_Station_{key}_Decal", f["decal"],
                                0.5, 0.0)
        m[f"light_{key}"] = mat(f"FI_Station_{key}_Light",
                                tuple(c * 0.1 for c in f["light"]), 0.4, 0.0,
                                emissive=f["light"], estrength=4.0)
        # dedicated solid glazing bands (atrium walls, control glazing) —
        # denser than the shader's seeded window grid can reach
        m[f"window_{key}"] = mat(f"FI_Station_{key}_Window",
                                 tuple(c * 0.08 for c in f["light"]),
                                 0.3, 0.0, emissive=f["light"],
                                 estrength=7.0)
        # dock-maw floodlight floors / reactor throats (the fleet Drive
        # role, renamed for what it lights here)
        m[f"glow_{key}"] = mat(f"FI_Station_{key}_Glow",
                               (0.05, 0.05, 0.06), 0.5, 0.0,
                               emissive=f["glow"], estrength=7.0)
    return m


# ------------------------------------------------------ station profile ----

def build_station_profile():
    """v (0 keel .. 1 crown) -> W, Dp footprint multipliers. The vertical
    silhouette: 5 styles, seeded tier steps, independent W/Dp step trains
    so stacked styles read as a broken city block, not a lathe."""
    g = G("FI_StationProfile")
    g.sock_in("v", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Style", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Tiers", "NodeSocketInt", 4, 2, 7)
    g.sock_in("Tier Jitter", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Taper Top", "NodeSocketFloat", 0.25, 0.0, 1.0)
    g.sock_in("Taper Bottom", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Bulge", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Bulge Position", "NodeSocketFloat", 0.55, 0.2, 0.8)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Skyline", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_out("W", "NodeSocketFloat")
    g.sock_out("Dp", "NodeSocketFloat")
    v = group_in(g, "v")
    seed = group_in(g, "Seed")
    style = group_in(g, "Style")
    tiers = group_in(g, "Tiers")
    jit = group_in(g, "Tier Jitter")

    def clamp01(x):
        return g.math("MINIMUM", g.math("MAXIMUM", x, 0.0), 1.0)

    def ieq(k):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(style, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = k
        return out_sock(n, "Result")

    def igt(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="GREATER_THAN")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    def fsw_p(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, in_sock(n, "Switch"))
        for nm, val in (("False", off), ("True", on)):
            s = in_sock(n, nm, "VALUE")
            if hasattr(val, "is_linked"):
                g.l(val, s)
            else:
                s.default_value = val
        return out_sock(n, "Output", "VALUE")

    # tier amplitudes bias up with Class (big stations jog harder)
    amp_bias = g.math("ADD", 1.0,
                      g.math("MULTIPLY", group_in(g, "Class"), 0.35))

    # ---- style 0: stacked-city — seeded step train, Tiers gates count
    w0 = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", v, 0.10))
    for i in range(5):
        pos = g.rand_float(0.12, 0.88, None,
                           g.math("ADD", seed, 11.0 + i * 7.0))
        amp = g.math("MULTIPLY",
                     g.math("SUBTRACT",
                            g.rand_float(0.0, 1.0, None,
                                         g.math("ADD", seed,
                                                12.0 + i * 7.0)), 0.5),
                     g.math("MULTIPLY",
                            g.math("MULTIPLY", 0.34, jit), amp_bias))
        w0 = g.math("ADD", w0,
                    g.math("MULTIPLY",
                           g.math("MULTIPLY", amp,
                                  g.math("GREATER_THAN", v, pos)),
                           igt(tiers, i + 1)))

    # ---- style 1: spindle — tent bulge at Bulge Position
    bp = group_in(g, "Bulge Position")
    tw = g.math("MAXIMUM", 0.0,
                g.math("SUBTRACT", 1.0,
                       g.math("ABSOLUTE",
                              g.math("DIVIDE",
                                     g.math("SUBTRACT", v, bp), 0.45))))
    w1 = g.math("ADD", 0.55,
                g.math("MULTIPLY",
                       g.math("MULTIPLY", group_in(g, "Bulge"), 0.60), tw))

    # ---- style 2: pagoda — sawtooth flare-and-choke per tier
    fr = g.math("FRACT", g.math("MULTIPLY", v, tiers))
    w2 = g.math("MULTIPLY",
                g.math("SUBTRACT", 1.0, g.math("MULTIPLY", fr, 0.32)),
                g.math("SUBTRACT", 1.0, g.math("MULTIPLY", v, 0.12)))

    # ---- style 3: monolith — near-constant batter
    w3 = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", v, 0.06))

    # ---- style 4: drum-stack — hard per-tier seeded radius plateaus
    tier_i = g.math("FLOOR", g.math("MULTIPLY", v, tiers))
    w4 = g.rand_float(0.55, 1.05, None,
                      g.math("ADD", seed,
                             g.math("ADD", 31.0,
                                    g.math("MULTIPLY", tier_i, 17.0))))

    w = fsw_p(ieq(1), w0, w1)
    w = fsw_p(ieq(2), w, w2)
    w = fsw_p(ieq(3), w, w3)
    w = fsw_p(ieq(4), w, w4)

    # ---- common modifiers: waist tent, end tapers ----------------------
    wd = g.math("DIVIDE", g.math("SUBTRACT", v, 0.5), 0.30)
    tent = g.math("MAXIMUM", 0.0,
                  g.math("SUBTRACT", 1.0, g.math("ABSOLUTE", wd)))
    w = g.math("MULTIPLY", w,
               g.math("SUBTRACT", 1.0,
                      g.math("MULTIPLY",
                             g.math("MULTIPLY", group_in(g, "Waist"),
                                    0.35), tent)))
    ramp_b = clamp01(g.math("DIVIDE", v, 0.22))
    w = g.math("MULTIPLY", w,
               g.math("SUBTRACT", 1.0,
                      g.math("MULTIPLY",
                             g.math("MULTIPLY",
                                    group_in(g, "Taper Bottom"), 0.5),
                             g.math("SUBTRACT", 1.0, ramp_b))))
    ramp_t = clamp01(g.math("DIVIDE", g.math("SUBTRACT", 1.0, v), 0.22))
    w = g.math("MULTIPLY", w,
               g.math("SUBTRACT", 1.0,
                      g.math("MULTIPLY",
                             g.math("MULTIPLY",
                                    group_in(g, "Taper Top"), 0.5),
                             g.math("SUBTRACT", 1.0, ramp_t))))

    # ---- Dp: independent step train on the blocky styles (0 and 4) so
    # footprints read stacked-city, not lathed
    blocky = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(ieq(0), blocky.inputs[0])
    g.l(ieq(4), blocky.inputs[1])
    dp_dev = None
    for i in range(3):
        pos = g.rand_float(0.15, 0.85, None,
                           g.math("ADD", seed, 51.0 + i * 9.0))
        amp = g.math("MULTIPLY",
                     g.math("SUBTRACT",
                            g.rand_float(0.0, 1.0, None,
                                         g.math("ADD", seed,
                                                52.0 + i * 9.0)), 0.5),
                     g.math("MULTIPLY", 0.22, jit))
        stp = g.math("MULTIPLY", amp, g.math("GREATER_THAN", v, pos))
        dp_dev = stp if dp_dev is None else g.math("ADD", dp_dev, stp)
    dp = g.math("MULTIPLY", w,
                g.math("ADD", 1.0,
                       g.math("MULTIPLY", dp_dev, blocky.outputs[0])))

    # ---- Skyline: extra W-only step train — breaks the skyline without
    # losing Dp coherence
    for i in range(3):
        pos = g.rand_float(0.20, 0.90, None,
                           g.math("ADD", seed, 71.0 + i * 9.0))
        amp = g.math("MULTIPLY",
                     g.math("SUBTRACT",
                            g.rand_float(0.0, 1.0, None,
                                         g.math("ADD", seed,
                                                72.0 + i * 9.0)), 0.5),
                     g.math("MULTIPLY", 0.30, group_in(g, "Skyline")))
        w = g.math("ADD", w,
                   g.math("MULTIPLY", amp, g.math("GREATER_THAN", v, pos)))

    w = g.math("MINIMUM", g.math("MAXIMUM", w, 0.08), 1.20)
    dp = g.math("MINIMUM", g.math("MAXIMUM", dp, 0.08), 1.20)

    g.gout = g.n("NodeGroupOutput")
    g.l(w, g.gout.inputs[0])
    g.l(dp, g.gout.inputs[1])
    g.ng.asset_mark()
    return g.ng


# --------------------------------------------------------- station core ----

def build_station_core(profile):
    """Vertical cube-grid loft. fi_u unit-space capture FIRST; corner-cut
    chamfer in the XY plane; profile loft along Z; zone attrs; base flare /
    ledge rings / top plateaus / towers UP AND DOWN — all boss() regions."""
    g = G("FI_StationCore")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Width", "NodeSocketFloat", 140.0, 10.0, 2000.0)
    g.sock_in("Depth", "NodeSocketFloat", 140.0, 10.0, 2000.0)
    g.sock_in("Height", "NodeSocketFloat", 380.0, 10.0, 4000.0)
    g.sock_in("Levels", "NodeSocketInt", 16, 4, 64)
    g.sock_in("Cols", "NodeSocketInt", 9, 4, 21)
    g.sock_in("Rows", "NodeSocketInt", 9, 4, 21)
    g.sock_in("Corner Cut", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Corner Cut Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Style", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Tiers", "NodeSocketInt", 4, 2, 7)
    g.sock_in("Tier Jitter", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Taper Top", "NodeSocketFloat", 0.25, 0.0, 1.0)
    g.sock_in("Taper Bottom", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Bulge", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Bulge Position", "NodeSocketFloat", 0.55, 0.2, 0.8)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Skyline", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Base Flare", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Ledges", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Ledge Depth", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Top Plateaus", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Towers Up", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Towers Down", "NodeSocketInt", 1, 0, 3)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.2, 0.0, 1.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    W = group_in(g, "Width")
    Dp = group_in(g, "Depth")
    H = group_in(g, "Height")
    seed = group_in(g, "Seed")

    cube = g.n("GeometryNodeMeshCube")
    in_sock(cube, "Size").default_value = (1.0, 1.0, 1.0)
    g.l(group_in(g, "Cols"), in_sock(cube, "Vertices X"))
    g.l(group_in(g, "Rows"), in_sock(cube, "Vertices Y"))
    g.l(group_in(g, "Levels"), in_sock(cube, "Vertices Z"))

    # fi_u: unit-space position, captured BEFORE any deformation — every
    # downstream region selection tests this, never live positions
    st_u = g.n("GeometryNodeStoreNamedAttribute", data_type="FLOAT_VECTOR",
               domain="POINT")
    g.l(out_sock(cube, "Mesh"), st_u.inputs[0])
    in_sock(st_u, "Name").default_value = "fi_u"
    pos0 = g.n("GeometryNodeInputPosition")
    g.l(out_sock(pos0, "Position"), in_sock(st_u, "Value", "VECTOR"))

    # corner-cut chamfer projection (the fleet chine math turned into the
    # XY plane: square -> octagon footprint) + loft in one Set Position
    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    x, y, z = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    xn = g.math("MULTIPLY", x, 2.0)
    yn = g.math("MULTIPLY", y, 2.0)
    ax = g.math("ABSOLUTE", xn)
    ay = g.math("ABSOLUTE", yn)
    m = g.math("MAXIMUM", g.math("MAXIMUM", ax, ay), 0.001)
    s = g.math("MAXIMUM",
               g.math("MULTIPLY", g.math("DIVIDE", W, Dp),
                      group_in(g, "Corner Cut Slope")), 0.2)
    cprime = g.math("DIVIDE",
                    g.math("SUBTRACT", 1.0,
                           g.math("MULTIPLY",
                                  group_in(g, "Corner Cut"), 0.8)), s)
    k = g.math("MAXIMUM", m,
               g.math("DIVIDE",
                      g.math("ADD", ax, g.math("DIVIDE", ay, s)),
                      g.math("ADD", 1.0, cprime)))
    f = g.math("DIVIDE", m, k)
    xnp = g.math("MULTIPLY", xn, f)
    ynp = g.math("MULTIPLY", yn, f)

    v = g.math("ADD", z, 0.5)
    tp = gcall(g, profile, wires={
        "v": v, "Seed": seed,
        "Style": group_in(g, "Style"),
        "Tiers": group_in(g, "Tiers"),
        "Tier Jitter": group_in(g, "Tier Jitter"),
        "Taper Top": group_in(g, "Taper Top"),
        "Taper Bottom": group_in(g, "Taper Bottom"),
        "Bulge": group_in(g, "Bulge"),
        "Bulge Position": group_in(g, "Bulge Position"),
        "Waist": group_in(g, "Waist"),
        "Skyline": group_in(g, "Skyline"),
        "Class": group_in(g, "Class")})
    X = g.math("MULTIPLY", xnp,
               g.math("MULTIPLY", g.math("DIVIDE", W, 2.0),
                      out_sock(tp, "W", "VALUE")))
    Y = g.math("MULTIPLY", ynp,
               g.math("MULTIPLY", g.math("DIVIDE", Dp, 2.0),
                      out_sock(tp, "Dp", "VALUE")))
    Z = g.math("MULTIPLY", z, H)
    cmb = g.n("ShaderNodeCombineXYZ")
    g.l(X, cmb.inputs[0])
    g.l(Y, cmb.inputs[1])
    g.l(Z, cmb.inputs[2])
    sp = g.n("GeometryNodeSetPosition")
    g.l(out_sock(st_u, "Geometry"), sp.inputs[0])
    g.l(cmb.outputs[0], in_sock(sp, "Position"))
    geo = out_sock(sp, "Geometry")

    # zone attrs, stored ONCE (boss walls inherit them later). Station
    # semantics: deck/cap_fore = crown grid, belly/cap_aft = keel grid,
    # flank = the four vertical walls.
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    zones = (("fi_deck", g.math("GREATER_THAN", ns.outputs[2], 0.8)),
             ("fi_belly", g.math("LESS_THAN", ns.outputs[2], -0.8)),
             ("fi_flank", g.math("LESS_THAN",
                                 g.math("ABSOLUTE", ns.outputs[2]), 0.5)),
             ("fi_cap_aft", g.math("LESS_THAN", ns.outputs[2], -0.8)),
             ("fi_cap_fore", g.math("GREATER_THAN", ns.outputs[2], 0.8)))
    for name, val in zones:
        st = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                 domain="FACE")
        g.l(geo, st.inputs[0])
        in_sock(st, "Name").default_value = name
        g.l(val, in_sock(st, "Value"))
        geo = out_sock(st, "Geometry")

    # unit-space + zone readers (fields, evaluated where used)
    def named_vec(name):
        n = g.n("GeometryNodeInputNamedAttribute",
                data_type="FLOAT_VECTOR")
        in_sock(n, "Name").default_value = name
        sp2 = g.n("ShaderNodeSeparateXYZ")
        g.l(out_sock(n, "Attribute"), sp2.inputs[0])
        return sp2.outputs[0], sp2.outputs[1], sp2.outputs[2]

    def named_bool(name):
        n = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
        in_sock(n, "Name").default_value = name
        return out_sock(n, "Attribute")

    def store_bool(geo, name, val):
        st = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                 domain="FACE")
        g.l(geo, st.inputs[0])
        in_sock(st, "Name").default_value = name
        g.l(val, in_sock(st, "Value"))
        return out_sock(st, "Geometry")

    def int_gt(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="GREATER_THAN")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    def band(vv, lo, hi):
        return g.math("MULTIPLY",
                      g.math("GREATER_THAN", vv, lo),
                      g.math("LESS_THAN", vv, hi))

    ux, uy, uz = named_vec("fi_u")
    tv = g.math("ADD", uz, 0.5)              # 0 keel .. 1 crown
    ux2 = g.math("MULTIPLY", ux, 2.0)        # -1 .. 1 footprint coords
    uy2 = g.math("MULTIPLY", uy, 2.0)

    # base flare: one positive skirt ring at the keel line
    fl_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY", named_bool("fi_flank"),
                           g.math("LESS_THAN", tv, 0.08)),
                    g.math("GREATER_THAN",
                           group_in(g, "Base Flare"), 0.02))
    geo, _, _ = boss(g, geo, fl_sel,
                     g.math("MULTIPLY", group_in(g, "Base Flare"),
                            g.math("MULTIPLY", W, 0.06)), 0.90)
    geo = store_bool(geo, "fi_keel",
                     g.math("MULTIPLY", named_bool("fi_flank"),
                            g.math("LESS_THAN", tv, 0.08)))

    # ledge rings: walkway shelves at seeded heights
    ld = g.math("MULTIPLY", group_in(g, "Ledge Depth"),
                g.math("MULTIPLY", W, 0.045))
    for i in range(3):
        tc = g.rand_float(0.22, 0.86, None,
                          g.math("ADD", seed, 21.0 + i * 7.0))
        l_sel = g.math("MULTIPLY",
                       g.math("MULTIPLY", named_bool("fi_flank"),
                              g.math("LESS_THAN",
                                     g.math("ABSOLUTE",
                                            g.math("SUBTRACT", tv, tc)),
                                     0.030)),
                       int_gt(group_in(g, "Ledges"), i))
        geo, _, _ = boss(g, geo, l_sel, ld, 0.92)

    # top plateaus: the fleet plateau logic on the crown grid
    ph = g.math("MULTIPLY", group_in(g, "Plateau Height"),
                g.math("MULTIPLY", H, 0.05))
    p1_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY", named_bool("fi_cap_fore"),
                           g.math("MULTIPLY",
                                  g.math("LESS_THAN",
                                         g.math("ABSOLUTE", ux2), 0.60),
                                  g.math("LESS_THAN",
                                         g.math("ABSOLUTE", uy2), 0.60))),
                    int_gt(group_in(g, "Top Plateaus"), 0))
    geo, p1_top, _ = boss(g, geo, p1_sel, ph, 0.90)
    geo = store_bool(geo, "fi_plat1", p1_top)
    nz2 = g.n("GeometryNodeInputNormal")
    ns2 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nz2, "Normal"), ns2.inputs[0])
    up2 = g.math("GREATER_THAN", ns2.outputs[2], 0.8)
    p2_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY", named_bool("fi_plat1"),
                           g.math("MULTIPLY",
                                  g.math("LESS_THAN",
                                         g.math("ABSOLUTE", ux2), 0.35),
                                  g.math("LESS_THAN",
                                         g.math("ABSOLUTE", uy2), 0.35))),
                    g.math("MULTIPLY", up2,
                           int_gt(group_in(g, "Top Plateaus"), 1)))
    geo, p2_top, _ = boss(g, geo, p2_sel,
                          g.math("MULTIPLY", ph, 0.60), 0.88)
    geo = store_bool(geo, "fi_plat2", p2_top)

    # ---- towers UP and DOWN: the citadel's asymmetric vertical city.
    # The fleet integrated-tower stack run on BOTH caps with independent
    # seeded footprints. Tower footprints select stale fi_u (raised tops
    # inherit their source coords), so each level nests by construction.
    tw_h = group_in(g, "Tower Height")
    tw_r = group_in(g, "Tower Rake")
    lvl_w = (0.24, 0.17, 0.11)     # ux2 half-widths per level
    lvl_hz = (0.10, 0.08, 0.07)    # H fractions per level
    tower_mask = None              # OR of every tower top+side (fi_tower)
    # each tower owns a DISJOINT footprint cell (fleet lesson, radialized:
    # overlapping seeded windows double-stack into 190 m needles — the
    # intersection region re-extrudes through every later tower's levels)
    cells = ((-0.30, -0.30), (0.30, 0.30), (0.30, -0.30))
    for down, count_k, seed0, shear_sgn in (
            (False, "Towers Up", 41.0, 1.0),
            (True, "Towers Down", 61.0, -1.0)):
        cnt = group_in(g, count_k)
        capn = "fi_cap_aft" if down else "fi_cap_fore"
        for ti in range(3):
            cx = g.math("ADD", cells[ti][0],
                        g.rand_float(-0.04, 0.04, None,
                                     g.math("ADD", seed,
                                            seed0 + ti * 13.0)))
            cy = g.math("ADD", cells[ti][1],
                        g.rand_float(-0.04, 0.04, None,
                                     g.math("ADD", seed,
                                            seed0 + 1.0 + ti * 13.0)))
            tgate = int_gt(cnt, ti)
            for lv in range(3):
                nrm_t = g.n("GeometryNodeInputNormal")
                nst = g.n("ShaderNodeSeparateXYZ")
                g.l(out_sock(nrm_t, "Normal"), nst.inputs[0])
                facing = (g.math("LESS_THAN", nst.outputs[2], -0.8)
                          if down else
                          g.math("GREATER_THAN", nst.outputs[2], 0.8))
                sel_t = g.math("MULTIPLY",
                               g.math("MULTIPLY",
                                      g.math("LESS_THAN",
                                             g.math("ABSOLUTE",
                                                    g.math("SUBTRACT",
                                                           ux2, cx)),
                                             lvl_w[lv]),
                                      g.math("LESS_THAN",
                                             g.math("ABSOLUTE",
                                                    g.math("SUBTRACT",
                                                           uy2, cy)),
                                             lvl_w[lv])),
                               g.math("MULTIPLY",
                                      g.math("MULTIPLY", facing,
                                             named_bool(capn)),
                                      tgate))
                geo, t_top, t_side = boss(g, geo, sel_t,
                                          g.math("MULTIPLY",
                                                 g.math("MULTIPLY", H,
                                                        lvl_hz[lv]),
                                                 tw_h), 0.86)
                # rake = geometric shear of the level top; borders stay
                # put so it is watertight (the fleet tower lesson)
                shx = g.n("ShaderNodeCombineXYZ")
                g.l(g.math("MULTIPLY",
                           g.math("MULTIPLY", tw_r, shear_sgn),
                           g.math("MULTIPLY", W, 0.05)), shx.inputs[0])
                spt = g.n("GeometryNodeSetPosition")
                g.l(geo, spt.inputs[0])
                g.l(t_top, in_sock(spt, "Selection"))
                g.l(shx.outputs[0], in_sock(spt, "Offset"))
                geo = out_sock(spt, "Geometry")
                lv_or = g.n("FunctionNodeBooleanMath", operation="OR")
                g.l(t_top, lv_or.inputs[0])
                g.l(t_side, lv_or.inputs[1])
                if tower_mask is None:
                    tower_mask = lv_or.outputs[0]
                else:
                    acc = g.n("FunctionNodeBooleanMath", operation="OR")
                    g.l(tower_mask, acc.inputs[0])
                    g.l(lv_or.outputs[0], acc.inputs[1])
                    tower_mask = acc.outputs[0]

    # fi_tower: tower skin — grown from plateau tops it INHERITS fi_plat*,
    # so the dress stage needs this mask to keep towers out of fi_deckwell
    # (dark-deck towers bug) and to give tower walls window eligibility
    geo = store_bool(geo, "fi_tower", tower_mask)

    return g.finish(geo)


# -------------------------------------------------------- station dress ----

def build_station_dress(mats, hg, parts):
    """The factored dressing chain — divider -> patchwork attrs -> relief
    -> blisters -> faction materials -> trench/hangar cuts -> weld ->
    fi_light. Reusable on ANY closed mesh that carries fi_u + zone attrs
    (the core, arm modules, maw slabs). The element-order contract from
    the fleet applies verbatim: apertures are attr-selected PRE-divider,
    the divider receives originals first, fi_light is stored after the
    weld so merged verts average their stale fi_u into soft band ends."""
    g = G("FI_StationDress")
    g.sock_in("Mesh", "NodeSocketGeometry")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Footprint", "NodeSocketFloat", 140.0, 1.0, 2000.0)
    g.sock_in("Height", "NodeSocketFloat", 380.0, 1.0, 4000.0)
    g.sock_in("Panel Density", "NodeSocketInt", 3, 1, 4)
    g.sock_in("Patchwork", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Accent Fields", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Accent Bands", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Meridian Stripe", "NodeSocketBool", False)
    g.sock_in("Hue Jitter", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 4, 0, 6)
    g.sock_in("Deck Markings", "NodeSocketBool", True)
    g.sock_in("Blisters", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Trenches", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Trench Depth", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Hangars", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hangar Size", "NodeSocketFloat", 1.0, 0.5, 1.5)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # Relief + Relief Floor Mult: created AFTER the output so every
    # pre-existing socket — including the Geometry output — keeps its
    # identifier (strictly additive contract). Defaults (True, 1.0)
    # preserve station behavior and goldens exactly. The BuildingKit's
    # LOD map turns Relief off for light/shell levels — gating the
    # SELECTION (not the offset) is what removes the x5 face cost,
    # since boss() extrudes regardless. Relief Floor Mult scales the
    # relief area floor: at building scale (30x120 m vs 140x380) the
    # W*H floor passes nearly every panel and relief explodes; ~10
    # keeps relief on only the largest panels.
    g.sock_in("Relief", "NodeSocketBool", True)
    g.sock_in("Relief Floor Mult", "NodeSocketFloat", 1.0, 0.1, 50.0)
    seed = group_in(g, "Seed")
    W = group_in(g, "Footprint")
    H = group_in(g, "Height")
    geo = group_in(g, "Mesh")

    def int_eq(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    def int_gt(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="GREATER_THAN")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    def named_bool(name):
        n = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
        in_sock(n, "Name").default_value = name
        return out_sock(n, "Attribute")

    def named_float(name):
        n = g.n("GeometryNodeInputNamedAttribute", data_type="FLOAT")
        in_sock(n, "Name").default_value = name
        return out_sock(n, "Attribute")

    def named_vec(name):
        n = g.n("GeometryNodeInputNamedAttribute",
                data_type="FLOAT_VECTOR")
        in_sock(n, "Name").default_value = name
        sp2 = g.n("ShaderNodeSeparateXYZ")
        g.l(out_sock(n, "Attribute"), sp2.inputs[0])
        return sp2.outputs[0], sp2.outputs[1], sp2.outputs[2]

    def bnot(v):
        n = g.n("FunctionNodeBooleanMath", operation="NOT")
        g.l(v, n.inputs[0])
        return n.outputs[0]

    def band(vv, lo, hi):
        return g.math("MULTIPLY",
                      g.math("GREATER_THAN", vv, lo),
                      g.math("LESS_THAN", vv, hi))

    def store_bool(geo, name, val):
        st = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                 domain="FACE")
        g.l(geo, st.inputs[0])
        in_sock(st, "Name").default_value = name
        g.l(val, in_sock(st, "Value"))
        return out_sock(st, "Geometry")

    # ---- aperture zones, stored BEFORE the divider (deep region cuts
    # must never land on divider-detached faces — the drive-slot rule)
    zux, zuy, zuz = named_vec("fi_u")
    ztv = g.math("ADD", zuz, 0.5)
    zux2 = g.math("MULTIPLY", zux, 2.0)
    zuy2 = g.math("MULTIPLY", zuy, 2.0)
    znrm = g.n("GeometryNodeInputNormal")
    zns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(znrm, "Normal"), zns.inputs[0])
    # hangar doors: paired recesses on the +-X walls at seeded heights
    hz_sum = None
    for i in range(2):
        hc = g.rand_float(0.30, 0.72, None,
                          g.math("ADD", seed, 83.0 + i * 7.0))
        hw2 = g.math("MULTIPLY", 0.05, group_in(g, "Hangar Size"))
        hzone = g.math("MULTIPLY",
                       g.math("MULTIPLY",
                              g.math("GREATER_THAN",
                                     g.math("ABSOLUTE", zns.outputs[0]),
                                     0.9),
                              band(ztv, g.math("SUBTRACT", hc, hw2),
                                   g.math("ADD", hc, hw2))),
                       g.math("MULTIPLY",
                              g.math("LESS_THAN",
                                     g.math("ABSOLUTE", zuy2), 0.45),
                              int_gt(group_in(g, "Hangars"), i)))
        hz_sum = hzone if hz_sum is None else g.math("ADD", hz_sum, hzone)
    geo = store_bool(geo, "fi_hangar",
                     g.math("GREATER_THAN", hz_sum, 0.5))
    # armor trenches: horizontal wrap bands on the flanks (the bastion)
    tz_sum = None
    for i in range(4):
        tc = g.rand_float(0.15, 0.85, None,
                          g.math("ADD", seed, 101.0 + i * 9.0))
        tzone = g.math("MULTIPLY",
                       g.math("MULTIPLY", named_bool("fi_flank"),
                              band(ztv, g.math("SUBTRACT", tc, 0.022),
                                   g.math("ADD", tc, 0.022))),
                       int_gt(group_in(g, "Trenches"), i))
        tz_sum = tzone if tz_sum is None else g.math("ADD", tz_sum, tzone)
    geo = store_bool(geo, "fi_trench",
                     g.math("GREATER_THAN", tz_sum, 0.5))
    # deck wells: plateau tops become dark landing platforms — towers
    # inherit fi_plat* from the tops they grow from, so mask them out
    dwell = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(named_bool("fi_plat1"), dwell.inputs[0])
    g.l(named_bool("fi_plat2"), dwell.inputs[1])
    dwell2 = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(dwell.outputs[0], dwell2.inputs[0])
    g.l(bnot(named_bool("fi_tower")), dwell2.inputs[1])
    geo = store_bool(geo, "fi_deckwell", dwell2.outputs[0])

    # ---- paneling: divider -> patchwork attrs -> per-panel relief -----
    hgr0 = named_bool("fi_hangar")
    trr0 = named_bool("fi_trench")
    keep = g.math("MULTIPLY",
                  g.math("SUBTRACT", 1.0, hgr0),
                  g.math("SUBTRACT", 1.0, trr0))
    panels = gcall(g, hg["Mesh Face Divider"], wires={
        "Mesh": geo, "Seed": seed,
        "Selection": keep,
        "Iterations": group_in(g, "Panel Density"),
        "Limit Distance": g.math("MULTIPLY", W, 0.03)},
        values={"U/V Ratio": 2.0, "Divide Probability": 0.72,
                "Even Probability": 0.5, "Distortion": 0.0})
    geo = out_sock(panels, "Mesh")
    fidt = g.n("GeometryNodeInputIndex")
    st_t = g.n("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
               domain="FACE")
    g.l(geo, st_t.inputs[0])
    in_sock(st_t, "Name").default_value = "fi_tint"
    g.l(g.rand_float(0.0, 1.0, out_sock(fidt, "Index"),
                     g.math("ADD", seed, 17.0)),
        in_sock(st_t, "Value", "VALUE"))
    geo = out_sock(st_t, "Geometry")
    st_h = g.n("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
               domain="FACE")
    g.l(geo, st_h.inputs[0])
    in_sock(st_h, "Name").default_value = "fi_hue"
    g.l(g.math("MULTIPLY",
               g.rand_float(0.0, 1.0, out_sock(fidt, "Index"),
                            g.math("ADD", seed, 19.0)),
               group_in(g, "Hue Jitter")),
        in_sock(st_h, "Value", "VALUE"))
    geo = out_sock(st_h, "Geometry")

    # accent fields (seeded rectangles in tv x footprint space), accent
    # BANDS as full horizontal rings, meridian stripe down the +-Y walls
    pux, puy, puz = named_vec("fi_u")
    ptv = g.math("ADD", puz, 0.5)
    pux2 = g.math("MULTIPLY", pux, 2.0)
    acc_sum = None
    for i in range(3):
        za = g.rand_float(0.12, 0.70, None,
                          g.math("ADD", seed, 31.0 + i * 9.0))
        zl = g.rand_float(0.08, 0.22, None,
                          g.math("ADD", seed, 32.0 + i * 9.0))
        zw = g.rand_float(0.25, 0.85, None,
                          g.math("ADD", seed, 33.0 + i * 9.0))
        zone = g.math("MULTIPLY",
                      g.math("MULTIPLY",
                             band(ptv, za, g.math("ADD", za, zl)),
                             g.math("LESS_THAN",
                                    g.math("ABSOLUTE", pux2), zw)),
                      int_gt(group_in(g, "Accent Fields"), i))
        acc_sum = zone if acc_sum is None else g.math("ADD", acc_sum, zone)
    for i in range(2):
        bc = g.rand_float(0.20, 0.78, None,
                          g.math("ADD", seed, 41.0 + i * 9.0))
        bwd = g.rand_float(0.020, 0.045, None,
                           g.math("ADD", seed, 42.0 + i * 9.0))
        bandz = g.math("MULTIPLY",
                       band(ptv, g.math("SUBTRACT", bc, bwd),
                            g.math("ADD", bc, bwd)),
                       int_gt(group_in(g, "Accent Bands"), i))
        acc_sum = g.math("ADD", acc_sum, bandz)
    # 0.15 half-width, sized to the grid: face centres sit at multiples
    # of 0.125 (Cols 9) — a 0.10 window falls BETWEEN them and the
    # stripe selects nothing (knob-dead in the first selftest run)
    stripe = g.math("MULTIPLY",
                    g.math("MULTIPLY",
                           g.math("LESS_THAN",
                                  g.math("ABSOLUTE", pux2), 0.15),
                           named_bool("fi_flank")),
                    group_in(g, "Meridian Stripe"))
    acc_sum = g.math("ADD", acc_sum, stripe)
    accf = g.math("MULTIPLY",
                  g.math("MULTIPLY",
                         g.math("GREATER_THAN", acc_sum, 0.5),
                         bnot(named_bool("fi_deckwell"))),
                  g.math("MULTIPLY",
                         bnot(named_bool("fi_hangar")),
                         bnot(named_bool("fi_trench"))))
    geo = store_bool(geo, "fi_accent", accf)
    # painted pad dashes (knob -> attr; shaders can't read knobs)
    dm_and = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(named_bool("fi_deckwell"), dm_and.inputs[0])
    g.l(group_in(g, "Deck Markings"), dm_and.inputs[1])
    geo = store_bool(geo, "fi_deckmark", dm_and.outputs[0])
    # lit-window panels: seeded flank faces in the habitable band —
    # the night-city mechanism
    fidw = g.n("GeometryNodeInputIndex")
    winel = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(g.math("MULTIPLY", named_bool("fi_flank"),
               band(ptv, 0.10, 0.92)), winel.inputs[0])
    g.l(named_bool("fi_tower"), winel.inputs[1])
    glow_sel = g.math("MULTIPLY",
                      g.math("MULTIPLY", winel.outputs[0], 1.0),
                      g.math("MULTIPLY",
                             g.math("LESS_THAN",
                                    g.rand_float(0.0, 1.0,
                                                 out_sock(fidw, "Index"),
                                                 g.math("ADD", seed,
                                                        63.0)),
                                    g.math("MULTIPLY",
                                           group_in(g, "Window Glow"),
                                           0.5)),
                             bnot(accf)))
    geo = store_bool(geo, "fi_glowpanel", glow_sel)

    # weld EARLY — before relief, unlike the fleet. Fusing divider
    # islands first means the individual relief extrudes run on a
    # CONNECTED manifold, so every shared edge gets side walls from both
    # panels. Welding after relief let two adjacent panels that sank to
    # near-identical depths merge their sunk chords, dedup their
    # coincident walls, and leave a lone open edge with sink-deep
    # "daylight" (found on stacked/seed 1). Distance scales with the
    # body (the cruiser-weld lesson; fixed 2 mm stops welding at km
    # scale). The stale-fi_u averaging that shapes the fi_light bands
    # still happens here, before fi_light is stored.
    weld = g.n("GeometryNodeMergeByDistance")
    g.l(geo, weld.inputs[0])
    g.l(g.math("MAXIMUM", g.math("MULTIPLY", W, 0.0002), 0.002),
        in_sock(weld, "Distance"))
    geo = out_sock(weld, "Geometry")

    # per-panel relief: panels sink by their tint, accents ride proud
    acc_r = named_bool("fi_accent")
    tint_r = named_float("fi_tint")
    d_sink = g.math("MULTIPLY", W,
                    g.math("MULTIPLY", -1.0,
                           g.math("ADD", 0.004,
                                  g.math("MULTIPLY", 0.006,
                                         g.math("MULTIPLY", tint_r,
                                                group_in(g,
                                                         "Patchwork"))))))
    d_relief = g.math("ADD",
                      g.math("MULTIPLY", d_sink,
                             g.math("SUBTRACT", 1.0, acc_r)),
                      g.math("MULTIPLY", g.math("MULTIPLY", W, 0.003),
                             acc_r))
    areap = g.n("GeometryNodeInputMeshFaceArea")
    bigp = g.math("GREATER_THAN", out_sock(areap, "Area"),
                  g.math("MULTIPLY",
                         g.math("MULTIPLY", g.math("MULTIPLY", W, H),
                                0.0008),
                         group_in(g, "Relief Floor Mult")))
    pr_sel = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(bnot(named_bool("fi_deckwell")), pr_sel.inputs[0])
    g.l(bnot(named_bool("fi_hangar")), pr_sel.inputs[1])
    pr_selb = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pr_sel.outputs[0], pr_selb.inputs[0])
    g.l(bnot(named_bool("fi_trench")), pr_selb.inputs[1])
    pr_sel2 = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pr_selb.outputs[0], pr_sel2.inputs[0])
    g.l(bigp, pr_sel2.inputs[1])
    pr_sel3 = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pr_sel2.outputs[0], pr_sel3.inputs[0])
    g.l(group_in(g, "Relief"), pr_sel3.inputs[1])
    geo, _, _ = boss(g, geo, pr_sel3.outputs[0], d_relief, 0.90,
                     individual=True)

    # blisters: two-step chamfered module housings on seeded roof panels
    nrmb = g.n("GeometryNodeInputNormal")
    nsb = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrmb, "Normal"), nsb.inputs[0])
    upb = g.math("GREATER_THAN", nsb.outputs[2], 0.8)
    areab = g.n("GeometryNodeInputMeshFaceArea")
    bigb = g.math("GREATER_THAN", out_sock(areab, "Area"),
                  g.math("MULTIPLY",
                         g.math("MULTIPLY", g.math("MULTIPLY", W, H),
                                0.0012),
                         group_in(g, "Relief Floor Mult")))
    fidb = g.n("GeometryNodeInputIndex")
    b_pick = g.math("LESS_THAN",
                    g.rand_float(0.0, 1.0, out_sock(fidb, "Index"),
                                 g.math("ADD", seed, 91.0)),
                    g.math("MULTIPLY", group_in(g, "Blisters"), 0.35))
    deckish = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(named_bool("fi_deck"), deckish.inputs[0])
    g.l(named_bool("fi_plat1"), deckish.inputs[1])
    b_sel = g.math("MULTIPLY",
                   g.math("MULTIPLY",
                          g.math("MULTIPLY", deckish.outputs[0], upb),
                          g.math("MULTIPLY", bigb, b_pick)),
                   bnot(named_bool("fi_deckwell")))
    geo, b1t, b1s = boss(g, geo, b_sel,
                         g.math("MULTIPLY", W, 0.020), 0.82,
                         individual=True)
    geo, b2t, b2s = boss(g, geo, b1t,
                         g.math("MULTIPLY", W, 0.008), 0.85,
                         individual=True)
    bl_or1 = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(b1t, bl_or1.inputs[0])
    g.l(b1s, bl_or1.inputs[1])
    bl_or2 = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(b2t, bl_or2.inputs[0])
    g.l(b2s, bl_or2.inputs[1])
    bl_all = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(bl_or1.outputs[0], bl_all.inputs[0])
    g.l(bl_or2.outputs[0], bl_all.inputs[1])
    st_b = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
               domain="FACE")
    g.l(geo, st_b.inputs[0])
    in_sock(st_b, "Name").default_value = "fi_accent"
    g.l(bl_all.outputs[0], in_sock(st_b, "Selection"))
    st_bv = g.n("FunctionNodeInputBool")
    st_bv.boolean = True
    g.l(st_bv.outputs[0], in_sock(st_b, "Value"))
    geo = out_sock(st_b, "Geometry")

    # ---- faction material switch (mat4: the fleet mat3 + FPT) ---------
    is_oxr = int_eq(group_in(g, "Faction"), 1)
    is_nyx = int_eq(group_in(g, "Faction"), 2)
    is_fpt = int_eq(group_in(g, "Faction"), 3)

    def mat4(role):
        m1 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
        g.l(is_oxr, in_sock(m1, "Switch"))
        in_sock(m1, "False", "MATERIAL").default_value = \
            mats[f"{role}_NAV"]
        in_sock(m1, "True", "MATERIAL").default_value = \
            mats[f"{role}_OXR"]
        m2 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
        g.l(is_nyx, in_sock(m2, "Switch"))
        g.l(out_sock(m1, "Output", "MATERIAL"),
            in_sock(m2, "False", "MATERIAL"))
        in_sock(m2, "True", "MATERIAL").default_value = \
            mats[f"{role}_NYX"]
        m3 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
        g.l(is_fpt, in_sock(m3, "Switch"))
        g.l(out_sock(m2, "Output", "MATERIAL"),
            in_sock(m3, "False", "MATERIAL"))
        in_sock(m3, "True", "MATERIAL").default_value = \
            mats[f"{role}_FPT"]
        return out_sock(m3, "Output", "MATERIAL")

    def set_mat(geo, sel, matsock_or_key):
        sm = g.n("GeometryNodeSetMaterial")
        g.l(geo, sm.inputs[0])
        if sel is not None:
            g.l(sel, in_sock(sm, "Selection"))
        if isinstance(matsock_or_key, str):
            in_sock(sm, "Material").default_value = mats[matsock_or_key]
        else:
            g.l(matsock_or_key, in_sock(sm, "Material"))
        return out_sock(sm, "Geometry")

    # base materials FIRST (overrides come after — the war-kit order rule)
    geo = set_mat(geo, None, mat4("hull"))
    geo = set_mat(geo, named_bool("fi_deckwell"), mat4("deck"))

    # ---- aperture cuts on the attr-selected pre-divider regions -------
    hg_sel = named_bool("fi_hangar")
    geo, hg_top, hg_side = boss(g, geo, hg_sel,
                                g.math("MULTIPLY", W, -0.08), 0.85)
    tr_sel = named_bool("fi_trench")
    geo, tr_top, tr_side = boss(g, geo, tr_sel,
                                g.math("MULTIPLY",
                                       g.math("MULTIPLY", W, -0.05),
                                       group_in(g, "Trench Depth")), 0.92)

    def or2(a, b):
        n = g.n("FunctionNodeBooleanMath", operation="OR")
        g.l(a, n.inputs[0])
        g.l(b, n.inputs[1])
        return n.outputs[0]

    geo = set_mat(geo, or2(hg_side, tr_side), "dark")
    geo = set_mat(geo, tr_top, "cavity")
    geo = set_mat(geo, hg_top, mat4("glow"))
    welded = geo

    # ---- running lights: per-POINT tier-line bands stored AFTER the
    # weld (merged verts average their stale fi_u — that averaging is
    # what creates the soft band ends; the fleet mechanism verbatim)
    lux, luy, luz = named_vec("fi_u")
    l_tv = g.math("ADD", luz, 0.5)
    in_v = g.math("MULTIPLY",
                  g.math("GREATER_THAN", l_tv, 0.06),
                  g.math("LESS_THAN", l_tv, 0.94))
    lr = group_in(g, "Light Rows")
    lmask = None
    for i, gate_at in enumerate((0, 2, 4)):
        tc = g.rand_float(0.20, 0.88, None,
                          g.math("ADD", seed, 111.0 + i * 9.0))
        bnd = g.math("MULTIPLY",
                     g.math("LESS_THAN",
                            g.math("ABSOLUTE",
                                   g.math("SUBTRACT", l_tv, tc)), 0.015),
                     int_gt(lr, gate_at))
        lmask = bnd if lmask is None else g.math("ADD", lmask, bnd)
    lmask = g.math("MULTIPLY", g.math("MINIMUM", lmask, 1.0), in_v)
    st_l = g.n("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
               domain="POINT")
    g.l(welded, st_l.inputs[0])
    in_sock(st_l, "Name").default_value = "fi_light"
    g.l(lmask, in_sock(st_l, "Value", "VALUE"))
    welded = out_sock(st_l, "Geometry")
    return g.finish(welded)


# ------------------------------------------------- dressed core (composite)

def build_station_core_dressed(parts):
    """FI_StationCore + FI_StationDress in one callable — what the form
    composers instance. Pure pass-through wiring."""
    g = G("FI_StationCoreDressed")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Width", "NodeSocketFloat", 140.0, 10.0, 2000.0)
    g.sock_in("Depth", "NodeSocketFloat", 140.0, 10.0, 2000.0)
    g.sock_in("Height", "NodeSocketFloat", 380.0, 10.0, 4000.0)
    g.sock_in("Levels", "NodeSocketInt", 16, 4, 64)
    g.sock_in("Cols", "NodeSocketInt", 9, 4, 21)
    g.sock_in("Rows", "NodeSocketInt", 9, 4, 21)
    g.sock_in("Corner Cut", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Corner Cut Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Style", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Tiers", "NodeSocketInt", 4, 2, 7)
    g.sock_in("Tier Jitter", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Taper Top", "NodeSocketFloat", 0.25, 0.0, 1.0)
    g.sock_in("Taper Bottom", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Bulge", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Bulge Position", "NodeSocketFloat", 0.55, 0.2, 0.8)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Skyline", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Base Flare", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Ledges", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Ledge Depth", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Top Plateaus", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Towers Up", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Towers Down", "NodeSocketInt", 1, 0, 3)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.2, 0.0, 1.0)
    g.sock_in("Panel Density", "NodeSocketInt", 3, 1, 4)
    g.sock_in("Patchwork", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Accent Fields", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Accent Bands", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Meridian Stripe", "NodeSocketBool", False)
    g.sock_in("Hue Jitter", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 4, 0, 6)
    g.sock_in("Deck Markings", "NodeSocketBool", True)
    g.sock_in("Blisters", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Trenches", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Trench Depth", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Hangars", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hangar Size", "NodeSocketFloat", 1.0, 0.5, 1.5)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # appended after the output: strictly additive (see FI_StationDress)
    g.sock_in("Relief", "NodeSocketBool", True)
    g.sock_in("Relief Floor Mult", "NodeSocketFloat", 1.0, 0.1, 50.0)

    core = gcall(g, parts["core"], wires={
        k: group_in(g, k) for k in (
            "Seed", "Width", "Depth", "Height", "Levels", "Cols", "Rows",
            "Corner Cut", "Corner Cut Slope", "Style", "Tiers",
            "Tier Jitter", "Taper Top", "Taper Bottom", "Bulge",
            "Bulge Position", "Waist", "Skyline", "Class", "Base Flare",
            "Ledges", "Ledge Depth", "Top Plateaus", "Plateau Height",
            "Towers Up", "Towers Down", "Tower Height", "Tower Rake")})
    dwires = {k: group_in(g, k) for k in (
        "Seed", "Faction", "Panel Density", "Patchwork", "Accent Fields",
        "Accent Bands", "Meridian Stripe", "Hue Jitter", "Window Glow",
        "Light Rows", "Deck Markings", "Blisters", "Trenches",
        "Trench Depth", "Hangars", "Hangar Size", "Relief",
        "Relief Floor Mult")}
    dwires["Mesh"] = out_sock(core, "Geometry")
    dwires["Footprint"] = group_in(g, "Width")
    dwires["Height"] = group_in(g, "Height")
    dressed = gcall(g, parts["dress"], wires=dwires)
    return g.finish(out_sock(dressed, "Geometry"))


# ---------------------------------------------------- station components ---

def build_station_truss(mats):
    """Open lattice girder along +X: 4 chords + 4 posts + alternating
    diagonals per bay, all closed interpenetrating boxes (no welds — a
    weld would corrupt element order and buys nothing on struts)."""
    g = G("FI_StationTruss")
    g.sock_in("Length", "NodeSocketFloat", 100.0, 2.0, 4000.0)
    g.sock_in("Width", "NodeSocketFloat", 12.0, 0.5, 400.0)
    g.sock_in("Height", "NodeSocketFloat", 12.0, 0.5, 400.0)
    g.sock_in("Bays", "NodeSocketInt", 6, 2, 24)
    g.sock_in("Strut", "NodeSocketFloat", 0.10, 0.02, 0.30)
    g.sock_out("Geometry", "NodeSocketGeometry")
    L = group_in(g, "Length")
    Wd = group_in(g, "Width")
    Ht = group_in(g, "Height")
    bays = group_in(g, "Bays")
    Lb = g.math("DIVIDE", L, bays)
    th = g.math("MULTIPLY", g.math("MINIMUM", Wd, Ht),
                group_in(g, "Strut"))
    yh = g.math("MULTIPLY", Wd, 0.5)
    zh = g.math("MULTIPLY", Ht, 0.5)
    bay = g.n("GeometryNodeJoinGeometry")
    # 4 chords along the bay
    for sy, sz in ((1.0, 1.0), (1.0, -1.0), (-1.0, 1.0), (-1.0, -1.0)):
        g.l(_prim(g, "cube", (Lb, th, th), None,
                  (g.math("MULTIPLY", Lb, 0.5),
                   g.math("MULTIPLY", yh, sy),
                   g.math("MULTIPLY", zh, sz)), mats["truss"]),
            bay.inputs[0])
    # 4 posts at the bay end
    for sy in (1.0, -1.0):
        g.l(_prim(g, "cube", (th, th, Ht), None,
                  (Lb, g.math("MULTIPLY", yh, sy), 0.0), mats["truss"]),
            bay.inputs[0])
        g.l(_prim(g, "cube", (th, Wd, th), None,
                  (Lb, 0.0, g.math("MULTIPLY", zh, sy)), mats["truss"]),
            bay.inputs[0])
    # 2 face diagonals (top/bottom X-brace read); length spans the bay
    dlen = g.math("SQRT",
                  g.math("ADD", g.math("MULTIPLY", Lb, Lb),
                         g.math("MULTIPLY", Ht, Ht)))
    dang = g.math("ARCTAN2", Ht, Lb)
    for sy in (1.0, -1.0):
        dg = _prim(g, "cube", (dlen, th, th), None, None, mats["truss"])
        rot = g.n("GeometryNodeTransform")
        g.l(dg, rot.inputs[0])
        rv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", dang, -sy), rv.inputs[1])
        g.l(rv.outputs[0], in_sock(rot, "Rotation"))
        mv = g.n("GeometryNodeTransform")
        g.l(out_sock(rot, "Geometry"), mv.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", Lb, 0.5), tv.inputs[0])
        g.l(g.math("MULTIPLY", yh, sy), tv.inputs[1])
        g.l(tv.outputs[0], in_sock(mv, "Translation"))
        g.l(out_sock(mv, "Geometry"), bay.inputs[0])
    # instance the bay along X; odd bays flip about X so braces alternate
    line = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(bays, in_sock(line, "Count"))
    ov = g.n("ShaderNodeCombineXYZ")
    g.l(Lb, ov.inputs[0])
    g.l(ov.outputs[0], in_sock(line, "Offset"))
    idx = g.n("GeometryNodeInputIndex")
    parity = g.math("FLOORED_MODULO", out_sock(idx, "Index"), 2.0)
    rquat = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", parity, 3.14159265), rquat.inputs[0])
    iop = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(line, "Mesh"), iop.inputs[0])
    g.l(out_sock(bay, "Geometry"), in_sock(iop, "Instance"))
    g.l(rquat.outputs[0], in_sock(iop, "Rotation"))
    rl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(iop, "Instances"), rl.inputs[0])
    j = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(rl, "Geometry"), j.inputs[0])
    # end frame at x=0 (the line covers bay ends 1..Bays)
    for sy in (1.0, -1.0):
        g.l(_prim(g, "cube", (th, th, Ht), None,
                  (0.0, g.math("MULTIPLY", yh, sy), 0.0), mats["truss"]),
            j.inputs[0])
        g.l(_prim(g, "cube", (th, Wd, th), None,
                  (0.0, 0.0, g.math("MULTIPLY", zh, sy)), mats["truss"]),
            j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_station_tank(mats):
    """External tank cluster: capsules (cyl + squashed sphere caps) on a
    ring, per-tank length jitter, dark saddle frames."""
    g = G("FI_StationTank")
    g.sock_in("Count", "NodeSocketInt", 4, 1, 7)
    g.sock_in("Radius", "NodeSocketFloat", 8.0, 0.5, 200.0)
    g.sock_in("Length", "NodeSocketFloat", 40.0, 2.0, 800.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # Verts: created after the output (strictly additive); default 10 =
    # the old hardcoded count, so station behavior/goldens are
    # unchanged. Building LODs feed 8/6.
    g.sock_in("Verts", "NodeSocketInt", 10, 6, 16)
    cnt = group_in(g, "Count")
    R = group_in(g, "Radius")
    L = group_in(g, "Length")
    seed = group_in(g, "Seed")
    tverts = group_in(g, "Verts")
    cap = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (R, L), None, None, mats["metal"], verts=tverts),
        cap.inputs[0])
    for sz in (1.0, -1.0):
        sph = _prim(g, "sphere", (R,), None, None, mats["metal"],
                    verts=tverts)
        sq = g.n("GeometryNodeTransform")
        g.l(sph, sq.inputs[0])
        in_sock(sq, "Scale").default_value = (1.0, 1.0, 0.55)
        mv = g.n("GeometryNodeTransform")
        g.l(out_sock(sq, "Geometry"), mv.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", L, 0.5 * sz), tv.inputs[2])
        g.l(tv.outputs[0], in_sock(mv, "Translation"))
        g.l(out_sock(mv, "Geometry"), cap.inputs[0])
    pts = g.n("GeometryNodePoints")
    g.l(cnt, in_sock(pts, "Count"))
    idx = g.n("GeometryNodeInputIndex")
    ang = g.math("MULTIPLY",
                 g.math("DIVIDE", out_sock(idx, "Index"),
                        g.math("MAXIMUM", cnt, 1.0)), TAU)
    rr = g.math("MULTIPLY", R, 2.25)
    # Count 1 parks the single tank at the centre
    solo = g.math("LESS_THAN", cnt, 1.5)
    rr = g.math("MULTIPLY", rr, g.math("SUBTRACT", 1.0, solo))
    pv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", g.math("COSINE", ang), rr), pv.inputs[0])
    g.l(g.math("MULTIPLY", g.math("SINE", ang), rr), pv.inputs[1])
    g.l(pv.outputs[0], in_sock(pts, "Position"))
    iop = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(pts, "Points"), iop.inputs[0])
    g.l(out_sock(cap, "Geometry"), in_sock(iop, "Instance"))
    jit = g.rand_float(0.78, 1.0, out_sock(idx, "Index"),
                       g.math("ADD", seed, 7.0))
    sv = g.n("ShaderNodeCombineXYZ")
    sv.inputs[0].default_value = 1.0
    sv.inputs[1].default_value = 1.0
    g.l(jit, sv.inputs[2])
    g.l(sv.outputs[0], in_sock(iop, "Scale"))
    rl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(iop, "Instances"), rl.inputs[0])
    j = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(rl, "Geometry"), j.inputs[0])
    # saddle frames across the cluster
    fw = g.math("MULTIPLY", R, 5.6)
    for sz in (0.30, -0.30):
        g.l(_prim(g, "cube", (fw, fw, g.math("MULTIPLY", R, 0.5)), None,
                  (0.0, 0.0, g.math("MULTIPLY", L, sz)), mats["dark"]),
            j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_dock_pad(mats):
    """Radial landing pier along +X: pylon + crisp polygonal pad + rim
    boss + emissive edge ring + kiosk."""
    g = G("FI_DockPad")
    g.sock_in("Reach", "NodeSocketFloat", 60.0, 5.0, 1200.0)
    g.sock_in("Root", "NodeSocketFloat", 20.0, 0.0, 2000.0)
    g.sock_in("Size", "NodeSocketFloat", 24.0, 2.0, 500.0)
    g.sock_in("Verts", "NodeSocketInt", 8, 6, 16)
    g.sock_in("Lights", "NodeSocketBool", True)
    g.sock_out("Geometry", "NodeSocketGeometry")
    reach = group_in(g, "Reach")
    root = group_in(g, "Root")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    # pylon spans x -Root .. +0.95*Reach; the caller sizes Root to bury
    # it in the parent hull (the saucer runs pylons to the hub — lens
    # profiles and octagon chamfers narrow the rim unpredictably)
    plen = g.math("ADD", root, g.math("MULTIPLY", reach, 0.95))
    g.l(_prim(g, "cube", (plen, g.math("MULTIPLY", S, 0.45),
                          g.math("MULTIPLY", S, 0.30)), None,
              (g.math("SUBTRACT", g.math("MULTIPLY", plen, 0.5), root),
               0.0, 0.0),
              mats["metal"]), j.inputs[0])
    pad = _prim(g, "cyl", (S, g.math("MULTIPLY", S, 0.14)), None, None,
                mats["pad"], verts=group_in(g, "Verts"), smooth=False)
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    topf = g.math("GREATER_THAN", ns.outputs[2], 0.5)
    pad2, ptop, _ = boss(g, pad, topf, g.math("MULTIPLY", S, -0.02), 0.90)
    mvp = g.n("GeometryNodeTransform")
    g.l(pad2, mvp.inputs[0])
    tv = g.n("ShaderNodeCombineXYZ")
    g.l(reach, tv.inputs[0])
    g.l(tv.outputs[0], in_sock(mvp, "Translation"))
    g.l(out_sock(mvp, "Geometry"), j.inputs[0])
    # emissive rim ring, slightly proud below the deck line
    ring = _prim(g, "cyl", (g.math("MULTIPLY", S, 1.03),
                            g.math("MULTIPLY", S, 0.04)), None,
                 (reach, 0.0, g.math("MULTIPLY", S, 0.02)),
                 mats["padlight"], verts=group_in(g, "Verts"),
                 smooth=False)
    lsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Lights"), in_sock(lsw, "Switch"))
    g.l(ring, in_sock(lsw, "True", "GEOMETRY"))
    g.l(out_sock(lsw, "Output", "GEOMETRY"), j.inputs[0])
    # kiosk off-centre
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.22),
                          g.math("MULTIPLY", S, 0.16),
                          g.math("MULTIPLY", S, 0.18)), None,
              (g.math("MULTIPLY", reach, 0.72),
               g.math("MULTIPLY", S, 0.55),
               g.math("MULTIPLY", S, 0.14)), mats["dark"]), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_station_ring(mats):
    """Polygonal box-section halo + radial spoke boxes to the core."""
    g = G("FI_StationRing")
    g.sock_in("Radius", "NodeSocketFloat", 120.0, 10.0, 2000.0)
    g.sock_in("Section", "NodeSocketFloat", 8.0, 0.5, 200.0)
    g.sock_in("Segments", "NodeSocketInt", 12, 8, 24)
    g.sock_in("Spokes", "NodeSocketInt", 4, 0, 8)
    g.sock_out("Geometry", "NodeSocketGeometry")
    R = group_in(g, "Radius")
    S = group_in(g, "Section")
    j = g.n("GeometryNodeJoinGeometry")
    cc = g.n("GeometryNodeCurvePrimitiveCircle")
    g.l(group_in(g, "Segments"), in_sock(cc, "Resolution"))
    g.l(R, in_sock(cc, "Radius"))
    prof = g.n("GeometryNodeCurvePrimitiveQuadrilateral")
    g.l(S, in_sock(prof, "Width"))
    g.l(g.math("MULTIPLY", S, 0.6), in_sock(prof, "Height"))
    ctm = g.n("GeometryNodeCurveToMesh")
    g.l(out_sock(cc, "Curve"), in_sock(ctm, "Curve"))
    g.l(out_sock(prof, "Curve"), in_sock(ctm, "Profile Curve"))
    in_sock(ctm, "Fill Caps").default_value = True
    sm = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(ctm, "Mesh"), sm.inputs[0])
    in_sock(sm, "Material").default_value = mats["truss"]
    g.l(out_sock(sm, "Geometry"), j.inputs[0])
    # spokes: radial boxes from the core out to the ring
    pts = g.n("GeometryNodePoints")
    g.l(group_in(g, "Spokes"), in_sock(pts, "Count"))
    idx = g.n("GeometryNodeInputIndex")
    ang = g.math("MULTIPLY",
                 g.math("DIVIDE", out_sock(idx, "Index"),
                        g.math("MAXIMUM", group_in(g, "Spokes"), 1.0)),
                 TAU)
    spoke = _prim(g, "cube", (R, g.math("MULTIPLY", S, 0.5),
                              g.math("MULTIPLY", S, 0.35)), None,
                  (g.math("MULTIPLY", R, 0.52), 0.0, 0.0), mats["truss"])
    rv = g.n("ShaderNodeCombineXYZ")
    g.l(ang, rv.inputs[2])
    iop = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(pts, "Points"), iop.inputs[0])
    g.l(spoke, in_sock(iop, "Instance"))
    g.l(rv.outputs[0], in_sock(iop, "Rotation"))
    rl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(iop, "Instances"), rl.inputs[0])
    g.l(out_sock(rl, "Geometry"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_station_turret(mats):
    """Bastion hardpoint: base drum + housing + twin barrels + muzzles."""
    g = G("FI_StationTurret")
    g.sock_in("Size", "NodeSocketFloat", 14.0, 1.0, 200.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.36),
                         g.math("MULTIPLY", S, 0.26)), None,
              (0.0, 0.0, g.math("MULTIPLY", S, 0.13)), mats["metal"],
              verts=10), j.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.52),
                          g.math("MULTIPLY", S, 0.40),
                          g.math("MULTIPLY", S, 0.30)), None,
              (0.0, 0.0, g.math("MULTIPLY", S, 0.40)), mats["dark"]),
        j.inputs[0])
    for sy in (1.0, -1.0):
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.045),
                             g.math("MULTIPLY", S, 0.75)),
                  (0.0, 1.5707963, 0.0),
                  (g.math("MULTIPLY", S, 0.55),
                   g.math("MULTIPLY", S, 0.10 * sy),
                   g.math("MULTIPLY", S, 0.42)), mats["metal"], verts=8),
            j.inputs[0])
        g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.06),
                              g.math("MULTIPLY", S, 0.08),
                              g.math("MULTIPLY", S, 0.08)), None,
                  (g.math("MULTIPLY", S, 0.92),
                   g.math("MULTIPLY", S, 0.10 * sy),
                   g.math("MULTIPLY", S, 0.42)), mats["glow_generic"]),
            j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_dock_maw(mats, parts):
    """Docking cradle: U-channel of three DRESSED slabs (the core-dressed
    group at slab proportions — inhabited walls, not greebled boxes) +
    glow throat + rim approach lights. Open on +X; NOT a boolean void."""
    g = G("FI_DockMaw")
    g.sock_in("Width", "NodeSocketFloat", 120.0, 10.0, 1500.0)
    g.sock_in("Height", "NodeSocketFloat", 80.0, 5.0, 1000.0)
    g.sock_in("Depth", "NodeSocketFloat", 140.0, 10.0, 1500.0)
    g.sock_in("Glow", "NodeSocketFloat", 0.7, 0.0, 1.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Panel Density", "NodeSocketInt", 2, 1, 4)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 2, 0, 6)
    g.sock_out("Geometry", "NodeSocketGeometry")
    MW = group_in(g, "Width")
    MH = group_in(g, "Height")
    MD = group_in(g, "Depth")
    seed = group_in(g, "Seed")
    j = g.n("GeometryNodeJoinGeometry")

    def slab(w, dp, h, tx, ty, tz, seed_off):
        s = gcall(g, parts["core_dressed"], wires={
            "Seed": g.math("ADD", seed, seed_off),
            "Faction": group_in(g, "Faction"),
            "Width": w, "Depth": dp, "Height": h,
            "Panel Density": group_in(g, "Panel Density"),
            "Window Glow": group_in(g, "Window Glow"),
            "Light Rows": group_in(g, "Light Rows")},
            values={"Levels": 8, "Cols": 7, "Rows": 7,
                    "Corner Cut": 0.15, "Style": 3, "Tiers": 2,
                    "Tier Jitter": 0.15, "Taper Top": 0.0,
                    "Taper Bottom": 0.0, "Skyline": 0.1,
                    "Base Flare": 0.0, "Ledges": 1, "Ledge Depth": 0.4,
                    "Top Plateaus": 0, "Towers Up": 0, "Towers Down": 0,
                    "Accent Fields": 1, "Accent Bands": 1,
                    "Blisters": 0.2, "Trenches": 0,
                    "Hangars": 0, "Deck Markings": False})
        mv = g.n("GeometryNodeTransform")
        g.l(out_sock(s, "Geometry"), mv.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        for i, t in enumerate((tx, ty, tz)):
            if hasattr(t, "is_linked"):
                g.l(t, tv.inputs[i])
            else:
                tv.inputs[i].default_value = t
        g.l(tv.outputs[0], in_sock(mv, "Translation"))
        g.l(out_sock(mv, "Geometry"), j.inputs[0])

    # floor slab + two wall slabs (slab axis stays vertical — the core
    # loft is Z-lofted, so a squat call reads as a deck, a tall one as a
    # wall)
    slab(MD, MW, g.math("MULTIPLY", MH, 0.18),
         0.0, 0.0, g.math("MULTIPLY", MH, -0.41), 3.0)
    for sy in (1.0, -1.0):
        slab(MD, g.math("MULTIPLY", MW, 0.14),
             g.math("MULTIPLY", MH, 0.90),
             0.0, g.math("MULTIPLY", g.math("MULTIPLY", MW, 0.5), sy),
             g.math("MULTIPLY", MH, 0.05), 5.0 + sy)
    # glow throat: emissive back plate inside the channel
    thr = _prim(g, "cube", (g.math("MULTIPLY", MD, 0.10),
                            g.math("MULTIPLY", MW, 0.86),
                            g.math("MULTIPLY", MH, 0.80)), None,
                (g.math("MULTIPLY", MD, -0.42), 0.0, 0.0), None)
    smt = g.n("GeometryNodeSetMaterial")
    g.l(thr, smt.inputs[0])
    # faction glow via 3-switch chain
    is_oxr = g.n("FunctionNodeCompare", data_type="INT",
                 operation="EQUAL")
    g.l(group_in(g, "Faction"), in_sock(is_oxr, "A", "INT"))
    in_sock(is_oxr, "B", "INT").default_value = 1
    is_nyx = g.n("FunctionNodeCompare", data_type="INT",
                 operation="EQUAL")
    g.l(group_in(g, "Faction"), in_sock(is_nyx, "A", "INT"))
    in_sock(is_nyx, "B", "INT").default_value = 2
    is_fpt = g.n("FunctionNodeCompare", data_type="INT",
                 operation="EQUAL")
    g.l(group_in(g, "Faction"), in_sock(is_fpt, "A", "INT"))
    in_sock(is_fpt, "B", "INT").default_value = 3
    m1 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(out_sock(is_oxr, "Result"), in_sock(m1, "Switch"))
    in_sock(m1, "False", "MATERIAL").default_value = mats["glow_NAV"]
    in_sock(m1, "True", "MATERIAL").default_value = mats["glow_OXR"]
    m2 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(out_sock(is_nyx, "Result"), in_sock(m2, "Switch"))
    g.l(out_sock(m1, "Output", "MATERIAL"), in_sock(m2, "False", "MATERIAL"))
    in_sock(m2, "True", "MATERIAL").default_value = mats["glow_NYX"]
    m3 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(out_sock(is_fpt, "Result"), in_sock(m3, "Switch"))
    g.l(out_sock(m2, "Output", "MATERIAL"), in_sock(m3, "False", "MATERIAL"))
    in_sock(m3, "True", "MATERIAL").default_value = mats["glow_FPT"]
    g.l(out_sock(m3, "Output", "MATERIAL"), in_sock(smt, "Material"))
    gsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(g.math("GREATER_THAN", group_in(g, "Glow"), 0.02),
        in_sock(gsw, "Switch"))
    g.l(out_sock(smt, "Geometry"), in_sock(gsw, "True", "GEOMETRY"))
    g.l(out_sock(gsw, "Output", "GEOMETRY"), j.inputs[0])
    # rim approach lights along the two channel lips
    for sy in (1.0, -1.0):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", MD, 0.9),
                              g.math("MULTIPLY", MW, 0.02),
                              g.math("MULTIPLY", MW, 0.02)), None,
                  (0.0, g.math("MULTIPLY", g.math("MULTIPLY", MW, 0.44),
                               sy),
                   g.math("MULTIPLY", MH, -0.30)), mats["padlight"]),
            j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_station_arm(mats, parts):
    """Cross-arm along +X: pylon (solid or truss) + DRESSED hab module —
    a small core-dressed call, so arms read inhabited, not greebled.
    Module Style 0 = city block, 1 = drum stack, 2 = tank rack."""
    g = G("FI_StationArm")
    g.sock_in("Length", "NodeSocketFloat", 90.0, 5.0, 1200.0)
    g.sock_in("Width", "NodeSocketFloat", 10.0, 0.5, 200.0)
    g.sock_in("Module Scale", "NodeSocketFloat", 1.0, 0.4, 2.0)
    g.sock_in("Module Style", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Truss", "NodeSocketBool", False)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Panel Density", "NodeSocketInt", 2, 1, 4)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Hue Jitter", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 2, 0, 6)
    g.sock_out("Geometry", "NodeSocketGeometry")
    L = group_in(g, "Length")
    Wd = group_in(g, "Width")
    seed = group_in(g, "Seed")
    j = g.n("GeometryNodeJoinGeometry")
    # pylon: root at -0.08 L for embed; solid box or truss
    plen = g.math("MULTIPLY", L, 1.08)
    solid = _prim(g, "cube", (plen, Wd, g.math("MULTIPLY", Wd, 0.7)),
                  None, (g.math("MULTIPLY", L, 0.46), 0.0, 0.0),
                  mats["metal"])
    truss = gcall(g, parts["truss"], wires={
        "Length": plen, "Width": Wd,
        "Height": g.math("MULTIPLY", Wd, 0.7)}, values={"Bays": 6})
    tmv = g.n("GeometryNodeTransform")
    g.l(out_sock(truss, "Geometry"), tmv.inputs[0])
    ttv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", L, -0.08), ttv.inputs[0])
    g.l(ttv.outputs[0], in_sock(tmv, "Translation"))
    psw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Truss"), in_sock(psw, "Switch"))
    g.l(solid, in_sock(psw, "False", "GEOMETRY"))
    g.l(out_sock(tmv, "Geometry"), in_sock(psw, "True", "GEOMETRY"))
    g.l(out_sock(psw, "Output", "GEOMETRY"), j.inputs[0])
    # module at the pylon tip
    mw = g.math("MULTIPLY", g.math("MULTIPLY", L, 0.30),
                group_in(g, "Module Scale"))
    mh = g.math("MULTIPLY", mw, 1.7)
    mstyle = g.n("GeometryNodeSwitch", input_type="INT")
    ms1 = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
    g.l(group_in(g, "Module Style"), in_sock(ms1, "A", "INT"))
    in_sock(ms1, "B", "INT").default_value = 1
    g.l(out_sock(ms1, "Result"), in_sock(mstyle, "Switch"))
    in_sock(mstyle, "False", "INT").default_value = 0
    in_sock(mstyle, "True", "INT").default_value = 4
    # module panel density one below the station's, capped at 2 (arms
    # are numerous — 6 arms x 3 levels at full density blew the budget)
    pdm1 = g.math("MINIMUM",
                  g.math("MAXIMUM",
                         g.math("SUBTRACT",
                                group_in(g, "Panel Density"), 1.0),
                         1.0), 2.0)
    mod = gcall(g, parts["core_dressed"], wires={
        "Seed": g.math("ADD", seed, 11.0),
        "Faction": group_in(g, "Faction"),
        "Width": mw, "Depth": mw, "Height": mh,
        "Style": out_sock(mstyle, "Output", "INT"),
        "Panel Density": pdm1,
        "Window Glow": group_in(g, "Window Glow"),
        "Hue Jitter": group_in(g, "Hue Jitter"),
        "Light Rows": group_in(g, "Light Rows")},
        values={"Levels": 6, "Cols": 5, "Rows": 5, "Corner Cut": 0.35,
                "Tiers": 3, "Tier Jitter": 0.45, "Taper Top": 0.15,
                "Taper Bottom": 0.15, "Skyline": 0.25, "Base Flare": 0.0,
                "Ledges": 1, "Ledge Depth": 0.5, "Top Plateaus": 1,
                "Plateau Height": 0.4, "Towers Up": 1, "Towers Down": 0,
                "Tower Height": 0.7, "Accent Fields": 1,
                "Accent Bands": 1, "Blisters": 0.3,
                "Trenches": 0, "Hangars": 0})
    mmv = g.n("GeometryNodeTransform")
    g.l(out_sock(mod, "Geometry"), mmv.inputs[0])
    mtv = g.n("ShaderNodeCombineXYZ")
    g.l(L, mtv.inputs[0])
    g.l(mtv.outputs[0], in_sock(mmv, "Translation"))
    # tank-rack style swaps the hab module for a tank cluster
    rack = gcall(g, parts["tank"], wires={
        "Radius": g.math("MULTIPLY", mw, 0.22),
        "Length": g.math("MULTIPLY", mh, 0.8),
        "Seed": seed}, values={"Count": 5})
    rmv = g.n("GeometryNodeTransform")
    g.l(out_sock(rack, "Geometry"), rmv.inputs[0])
    g.l(mtv.outputs[0], in_sock(rmv, "Translation"))
    ms2 = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
    g.l(group_in(g, "Module Style"), in_sock(ms2, "A", "INT"))
    in_sock(ms2, "B", "INT").default_value = 2
    msw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(out_sock(ms2, "Result"), in_sock(msw, "Switch"))
    g.l(out_sock(mmv, "Geometry"), in_sock(msw, "False", "GEOMETRY"))
    g.l(out_sock(rmv, "Geometry"), in_sock(msw, "True", "GEOMETRY"))
    g.l(out_sock(msw, "Output", "GEOMETRY"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


# ------------------------------------------------------------ FI_Station ---

def build_station(mats, hg, parts):
    """Top-level station. Form picks the archetype (0 spire citadel /
    1 gantry yard / 2 saucer hub / 3 monolith bastion); the four
    assemblies are built INLINE behind an Index Switch (the fleet
    Hull-Form precedent — switches are lazy, only the picked branch
    evaluates). Shared fixtures raycast onto whichever form won."""
    g = G("FI_Station")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Form", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Detail", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Scale", "NodeSocketFloat", 1.0, 0.1, 10.0)
    g.sock_in("Height Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Footprint Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Silhouette Style", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Tiers", "NodeSocketInt", 4, 2, 7)
    g.sock_in("Tier Jitter", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Taper Top", "NodeSocketFloat", 0.25, 0.0, 1.0)
    g.sock_in("Taper Bottom", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Bulge", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Bulge Position", "NodeSocketFloat", 0.55, 0.2, 0.8)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Skyline", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Corner Cut", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Corner Cut Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Footprint Aspect", "NodeSocketFloat", 1.0, 0.5, 1.0)
    g.sock_in("Base Flare", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Ledges", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Ledge Depth", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Top Plateaus", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Towers Up", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Towers Down", "NodeSocketInt", 1, 0, 3)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.2, 0.0, 1.0)
    g.sock_in("Arms", "NodeSocketInt", 4, 0, 6)
    g.sock_in("Arm Length", "NodeSocketFloat", 0.6, 0.3, 1.2)
    g.sock_in("Arm Levels", "NodeSocketInt", 2, 1, 3)
    g.sock_in("Arm Stagger", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Arm Phase", "NodeSocketFloat", 0.0, 0.0, 6.2831853)
    g.sock_in("Arm Module Scale", "NodeSocketFloat", 1.0, 0.4, 2.0)
    g.sock_in("Arm Truss", "NodeSocketBool", False)
    g.sock_in("Pads", "NodeSocketInt", 6, 0, 12)
    g.sock_in("Pad Radius", "NodeSocketFloat", 0.85, 0.6, 1.1)
    g.sock_in("Pad Size", "NodeSocketFloat", 1.0, 0.5, 1.6)
    g.sock_in("Pad Tier", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Maw", "NodeSocketFloat", 0.8, 0.0, 1.0)
    g.sock_in("Maw Aspect", "NodeSocketFloat", 1.0, 0.6, 1.6)
    g.sock_in("Maw Depth", "NodeSocketFloat", 1.0, 0.5, 1.5)
    g.sock_in("Spine Stretch", "NodeSocketFloat", 1.6, 1.0, 3.0)
    g.sock_in("Gantries", "NodeSocketInt", 3, 0, 6)
    g.sock_in("Gantry Spacing", "NodeSocketFloat", 0.9, 0.5, 1.6)
    g.sock_in("Cranes", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Tank Clusters", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Tanks Per Cluster", "NodeSocketInt", 4, 1, 7)
    g.sock_in("Tank Scale", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Ring", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Ring Radius", "NodeSocketFloat", 0.95, 0.7, 1.4)
    g.sock_in("Spires", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Spire Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Turrets", "NodeSocketInt", 0, 0, 8)
    g.sock_in("Turret Scale", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Vents", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Radomes", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Antennas", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Decals", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Beacons", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Panel Density", "NodeSocketInt", 3, 1, 4)
    g.sock_in("Patchwork", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Accent Fields", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Accent Bands", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Meridian Stripe", "NodeSocketBool", False)
    g.sock_in("Hue Jitter", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 4, 0, 6)
    g.sock_in("Deck Markings", "NodeSocketBool", True)
    g.sock_in("Blisters", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Trenches", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Trench Depth", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Hangars", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hangar Size", "NodeSocketFloat", 1.0, 0.5, 1.5)
    g.sock_out("Geometry", "NodeSocketGeometry")
    seed = group_in(g, "Seed")

    def fsw(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, in_sock(n, "Switch"))
        for nm, v in (("False", off), ("True", on)):
            sck = in_sock(n, nm, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, sck)
            else:
                sck.default_value = v
        return out_sock(n, "Output", "VALUE")

    def int_eq(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    def int_gt(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="GREATER_THAN")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    # ---- dims + Detail resolution (Detail gates tessellation ONLY) ----
    is_cl = int_eq(group_in(g, "Class"), 1)
    W = g.math("MULTIPLY", fsw(is_cl, 140.0, 320.0),
               g.math("MULTIPLY", group_in(g, "Scale"),
                      group_in(g, "Footprint Mult")))
    Dp = g.math("MULTIPLY", W, group_in(g, "Footprint Aspect"))
    H = g.math("MULTIPLY", fsw(is_cl, 380.0, 900.0),
               g.math("MULTIPLY", group_in(g, "Scale"),
                      group_in(g, "Height Mult")))
    det = group_in(g, "Detail")
    levels = g.math("ADD", 16.0, g.math("MULTIPLY", det, 8.0))
    colsrows = g.math("ADD", 9.0, g.math("MULTIPLY", det, 2.0))
    pad_verts = g.math("ADD", 8.0, g.math("MULTIPLY", det, 2.0))
    bays = g.math("ADD", 4.0, g.math("MULTIPLY", det, 2.0))

    PAINT = ("Panel Density", "Patchwork", "Accent Fields", "Accent Bands",
             "Meridian Stripe", "Hue Jitter", "Window Glow", "Light Rows",
             "Deck Markings", "Blisters", "Trenches", "Trench Depth",
             "Hangars", "Hangar Size")
    SILH = (("Style", "Silhouette Style"), ("Tiers", "Tiers"),
            ("Tier Jitter", "Tier Jitter"), ("Taper Top", "Taper Top"),
            ("Taper Bottom", "Taper Bottom"), ("Bulge", "Bulge"),
            ("Bulge Position", "Bulge Position"), ("Waist", "Waist"),
            ("Skyline", "Skyline"),
            ("Corner Cut Slope", "Corner Cut Slope"))
    COREK = ("Base Flare", "Ledges", "Ledge Depth", "Top Plateaus",
             "Plateau Height", "Towers Up", "Towers Down", "Tower Height",
             "Tower Rake")

    def core_call(w, dp, h, seed_off=0.0, wires_over=None, values_over=None):
        wires = {"Seed": g.math("ADD", seed, seed_off),
                 "Faction": group_in(g, "Faction"),
                 "Class": group_in(g, "Class"),
                 "Width": w, "Depth": dp, "Height": h,
                 "Levels": levels, "Cols": colsrows, "Rows": colsrows,
                 "Corner Cut": group_in(g, "Corner Cut")}
        for dst, src in SILH:
            wires[dst] = group_in(g, src)
        for k in COREK:
            wires[k] = group_in(g, k)
        for k in PAINT:
            wires[k] = group_in(g, k)
        wires.update(wires_over or {})
        values = dict(values_over or {})
        for k in list(values):
            wires.pop(k, None)
        return gcall(g, parts["core_dressed"], wires=wires, values=values)

    def move(geo, tx, ty, tz, rot=None):
        mv = g.n("GeometryNodeTransform")
        g.l(geo, mv.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        for i, t in enumerate((tx, ty, tz)):
            if hasattr(t, "is_linked"):
                g.l(t, tv.inputs[i])
            else:
                tv.inputs[i].default_value = t
        g.l(tv.outputs[0], in_sock(mv, "Translation"))
        if rot is not None:
            in_sock(mv, "Rotation").default_value = rot
        return out_sock(mv, "Geometry")

    def gated(geo, gate, join):
        sw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(gate, in_sock(sw, "Switch"))
        g.l(geo, in_sock(sw, "True", "GEOMETRY"))
        g.l(out_sock(sw, "Output", "GEOMETRY"), join.inputs[0])

    def ring_pts(count, radius, z, phase):
        pts = g.n("GeometryNodePoints")
        g.l(count, in_sock(pts, "Count"))
        idx = g.n("GeometryNodeInputIndex")
        ang = g.math("ADD",
                     g.math("MULTIPLY",
                            g.math("DIVIDE", out_sock(idx, "Index"),
                                   g.math("MAXIMUM", count, 1.0)), TAU),
                     phase)
        pv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", g.math("COSINE", ang), radius),
            pv.inputs[0])
        g.l(g.math("MULTIPLY", g.math("SINE", ang), radius),
            pv.inputs[1])
        if hasattr(z, "is_linked"):
            g.l(z, pv.inputs[2])
        else:
            pv.inputs[2].default_value = z
        g.l(pv.outputs[0], in_sock(pts, "Position"))
        return out_sock(pts, "Points"), ang, out_sock(idx, "Index")

    def ring_realize(points, ang, inst, pick_idx=None):
        iop = g.n("GeometryNodeInstanceOnPoints")
        g.l(points, iop.inputs[0])
        g.l(inst, in_sock(iop, "Instance"))
        if pick_idx is not None:
            in_sock(iop, "Pick Instance").default_value = True
            g.l(pick_idx, in_sock(iop, "Instance Index"))
        rv = g.n("ShaderNodeCombineXYZ")
        g.l(ang, rv.inputs[2])
        g.l(rv.outputs[0], in_sock(iop, "Rotation"))
        rl = g.n("GeometryNodeRealizeInstances")
        g.l(out_sock(iop, "Instances"), rl.inputs[0])
        return out_sock(rl, "Geometry")

    # =========================== FORM 0: SPIRE CITADEL =================
    spire = g.n("GeometryNodeJoinGeometry")
    sp_core = core_call(W, Dp, H)
    g.l(out_sock(sp_core, "Geometry"), spire.inputs[0])
    # radial arm rings: seeded phase + z-stagger per level, two arm
    # variants alternating by parity (no non-uniform instance scaling)
    arm_len = g.math("MULTIPLY", group_in(g, "Arm Length"), W)
    arm_wires = {"Length": arm_len,
                 "Width": g.math("MULTIPLY", W, 0.075),
                 "Module Scale": group_in(g, "Arm Module Scale"),
                 "Truss": group_in(g, "Arm Truss"),
                 "Faction": group_in(g, "Faction"),
                 "Panel Density": group_in(g, "Panel Density"),
                 "Window Glow": group_in(g, "Window Glow"),
                 "Hue Jitter": group_in(g, "Hue Jitter"),
                 "Light Rows": group_in(g, "Light Rows")}
    armA = gcall(g, parts["arm"], wires=dict(arm_wires, Seed=seed),
                 values={"Module Style": 0})
    armB = gcall(g, parts["arm"],
                 wires=dict(arm_wires,
                            Seed=g.math("ADD", seed, 23.0)),
                 values={"Module Style": 1})
    g2i = g.n("GeometryNodeGeometryToInstance")
    g.l(out_sock(armA, "Geometry"), g2i.inputs[0])
    g.l(out_sock(armB, "Geometry"), g2i.inputs[0])
    for li in range(3):
        zjit = g.math("MULTIPLY",
                      g.math("SUBTRACT",
                             g.rand_float(0.0, 1.0, None,
                                          g.math("ADD", seed,
                                                 131.0 + li * 9.0)), 0.5),
                      g.math("MULTIPLY", group_in(g, "Arm Stagger"),
                             g.math("MULTIPLY", H, 0.12)))
        z_li = g.math("ADD",
                      g.math("MULTIPLY", H, -0.10 + 0.18 * li), zjit)
        phase = g.math("ADD", group_in(g, "Arm Phase"), 0.7 * li)
        pts, ang, idx = ring_pts(group_in(g, "Arms"),
                                 g.math("MULTIPLY", W, 0.22), z_li, phase)
        pick = g.n("ShaderNodeMath")
        pick.operation = "FLOORED_MODULO"
        g.l(idx, pick.inputs[0])
        pick.inputs[1].default_value = 2.0
        armring = ring_realize(pts, ang, out_sock(g2i, "Instances"),
                               pick_idx=pick.outputs[0])
        gated(armring, int_gt(group_in(g, "Arm Levels"), li), spire)
    # halo rings
    for ri, rz in enumerate((-0.10, 0.12)):
        ringc = gcall(g, parts["ring"], wires={
            "Radius": g.math("MULTIPLY", group_in(g, "Ring Radius"), W),
            "Section": g.math("MULTIPLY", W, 0.045)},
            values={"Segments": 12, "Spokes": 4})
        gated(move(out_sock(ringc, "Geometry"), 0.0, 0.0,
                   g.math("MULTIPLY", H, rz)),
              int_gt(group_in(g, "Ring"), ri), spire)

    # =========================== FORM 1: GANTRY YARD ===================
    yard = g.n("GeometryNodeJoinGeometry")
    spineL = g.math("MULTIPLY", H, group_in(g, "Spine Stretch"))
    yd_core = core_call(g.math("MULTIPLY", W, 0.55),
                        g.math("MULTIPLY", Dp, 0.55), spineL,
                        seed_off=41.0,
                        values_over={"Towers Up": 0, "Towers Down": 0,
                                     "Base Flare": 0.0, "Taper Top": 0.1,
                                     "Taper Bottom": 0.1,
                                     # crown plateaus would jut into the
                                     # maw berth (rotated crown = +X end)
                                     "Top Plateaus": 0})
    yd_spine = g.n("GeometryNodeTransform")
    g.l(out_sock(yd_core, "Geometry"), yd_spine.inputs[0])
    in_sock(yd_spine, "Rotation").default_value = (0.0, 1.5707963, 0.0)
    g.l(out_sock(yd_spine, "Geometry"), yard.inputs[0])
    # gantry portal frames straddling the spine
    fw = g.math("MULTIPLY", W, 0.72)
    fbeam = g.math("MULTIPLY", fw, 2.0)
    fsec_w = g.math("MULTIPLY", W, 0.055)
    frame = g.n("GeometryNodeJoinGeometry")
    for sz in (1.0, -1.0):
        beam = gcall(g, parts["truss"], wires={
            "Length": fbeam, "Width": fsec_w, "Height": fsec_w,
            "Bays": bays})
        rb = g.n("GeometryNodeTransform")
        g.l(out_sock(beam, "Geometry"), rb.inputs[0])
        in_sock(rb, "Rotation").default_value = (0.0, 0.0, 1.5707963)
        g.l(move(out_sock(rb, "Geometry"), 0.0,
                 g.math("MULTIPLY", fw, -1.0),
                 g.math("MULTIPLY", fw, sz)), frame.inputs[0])
        post = gcall(g, parts["truss"], wires={
            "Length": fbeam, "Width": fsec_w, "Height": fsec_w,
            "Bays": bays})
        rp = g.n("GeometryNodeTransform")
        g.l(out_sock(post, "Geometry"), rp.inputs[0])
        in_sock(rp, "Rotation").default_value = (0.0, -1.5707963, 0.0)
        g.l(move(out_sock(rp, "Geometry"), 0.0,
                 g.math("MULTIPLY", fw, sz),
                 g.math("MULTIPLY", fw, -1.0)), frame.inputs[0])
    # tie beam THROUGH the spine — without it every portal frame is a
    # floating shell ring (the island-overlap test caught 1000+ of them)
    g.l(_prim(g, "cube", (fsec_w, fbeam, fsec_w), None, None,
              mats["truss"]), frame.inputs[0])
    f2i = g.n("GeometryNodeGeometryToInstance")
    g.l(out_sock(frame, "Geometry"), f2i.inputs[0])
    # clamp the row to the spine: unclamped spacing hangs the end frames
    # off the hull and they float (the island-overlap test caught it)
    gspace = g.math("MINIMUM",
                    g.math("MULTIPLY", group_in(g, "Gantry Spacing"), W),
                    g.math("DIVIDE",
                           g.math("MULTIPLY", spineL, 0.85),
                           g.math("MAXIMUM",
                                  g.math("SUBTRACT",
                                         group_in(g, "Gantries"), 1.0),
                                  1.0)))
    gline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Gantries"), in_sock(gline, "Count"))
    gx0 = g.math("MULTIPLY",
                 g.math("MULTIPLY",
                        g.math("SUBTRACT", group_in(g, "Gantries"), 1.0),
                        gspace), -0.5)
    sv0 = g.n("ShaderNodeCombineXYZ")
    g.l(gx0, sv0.inputs[0])
    g.l(sv0.outputs[0], in_sock(gline, "Start Location"))
    ovg = g.n("ShaderNodeCombineXYZ")
    g.l(gspace, ovg.inputs[0])
    g.l(ovg.outputs[0], in_sock(gline, "Offset"))
    giop = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(gline, "Mesh"), giop.inputs[0])
    g.l(out_sock(f2i, "Instances"), in_sock(giop, "Instance"))
    grl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(giop, "Instances"), grl.inputs[0])
    gated(out_sock(grl, "Geometry"), int_gt(group_in(g, "Gantries"), 0),
          yard)
    # dock maw cradle at the +X end
    mawW = g.math("MULTIPLY",
                  g.math("MULTIPLY", W, group_in(g, "Maw Aspect")),
                  g.math("ADD", 0.55,
                         g.math("MULTIPLY", group_in(g, "Maw"), 0.55)))
    mawD = g.math("MULTIPLY",
                  g.math("MULTIPLY", W, 1.1), group_in(g, "Maw Depth"))
    mawc = gcall(g, parts["maw"], wires={
        "Width": mawW, "Height": g.math("MULTIPLY", W, 0.62),
        "Depth": mawD, "Glow": group_in(g, "Maw"),
        "Seed": seed, "Faction": group_in(g, "Faction"),
        "Panel Density": group_in(g, "Panel Density"),
        "Window Glow": group_in(g, "Window Glow"),
        "Light Rows": group_in(g, "Light Rows")})
    maw_x = g.math("ADD", g.math("MULTIPLY", spineL, 0.5),
                   g.math("MULTIPLY", mawD, 0.22))
    gated(move(out_sock(mawc, "Geometry"), maw_x, 0.0, 0.0),
          g.math("GREATER_THAN", group_in(g, "Maw"), 0.02), yard)
    # tank clusters alternating down the spine flanks
    for i in range(4):
        tx = g.rand_float(-0.32, 0.32, None,
                          g.math("ADD", seed, 151.0 + i * 9.0))
        tank = gcall(g, parts["tank"], wires={
            "Count": group_in(g, "Tanks Per Cluster"),
            "Radius": g.math("MULTIPLY",
                             g.math("MULTIPLY", W, 0.055),
                             group_in(g, "Tank Scale")),
            "Length": g.math("MULTIPLY",
                             g.math("MULTIPLY", W, 0.34),
                             group_in(g, "Tank Scale")),
            "Seed": g.math("ADD", seed, 7.0 * i)})
        side = 1.0 if i % 2 == 0 else -1.0
        # cluster + a mount strut reaching the spine centreline (thin
        # spine profiles otherwise leave the cluster floating)
        tgrp = g.n("GeometryNodeJoinGeometry")
        g.l(out_sock(tank, "Geometry"), tgrp.inputs[0])
        g.l(_prim(g, "cube", (g.math("MULTIPLY", W, 0.05),
                              g.math("MULTIPLY", W, 0.42),
                              g.math("MULTIPLY", W, 0.05)), None,
                  (0.0, g.math("MULTIPLY", W, -0.21 * side), 0.0),
                  mats["dark"]), tgrp.inputs[0])
        gated(move(out_sock(tgrp, "Geometry"),
                   g.math("MULTIPLY", spineL, tx),
                   g.math("MULTIPLY", W, 0.42 * side), 0.0),
              int_gt(group_in(g, "Tank Clusters"), i), yard)
    # cranes: sensor booms atop the gantry line, tilted down
    boomy = gcall(g, parts["boom"], wires={
        "Size": g.math("MULTIPLY", W, 0.55)})
    for i in range(4):
        cx = g.math("ADD", gx0, g.math("MULTIPLY", gspace, float(i)))
        side = 1.0 if i % 2 == 0 else -1.0
        cr = g.n("GeometryNodeTransform")
        g.l(out_sock(boomy, "Geometry"), cr.inputs[0])
        in_sock(cr, "Rotation").default_value = \
            (0.0, 0.35, 1.5707963 * side)
        gated(move(out_sock(cr, "Geometry"), cx,
                   g.math("MULTIPLY", W, -0.1 * side),
                   g.math("MULTIPLY", fw, 1.0)),
              int_gt(group_in(g, "Cranes"), i), yard)

    # =========================== FORM 2: SAUCER HUB ====================
    saucer = g.n("GeometryNodeJoinGeometry")
    sc_core = core_call(g.math("MULTIPLY", W, 1.9),
                        g.math("MULTIPLY", Dp, 1.9),
                        g.math("MULTIPLY", H, 0.32),
                        seed_off=71.0,
                        wires_over={"Style": group_in(
                            g, "Silhouette Style")},
                        values_over={"Towers Down": 0,
                                     "Base Flare": 0.0})
    g.l(out_sock(sc_core, "Geometry"), saucer.inputs[0])
    # ventral spike stack + dorsal dome
    sc_spike = core_call(g.math("MULTIPLY", W, 0.30),
                         g.math("MULTIPLY", Dp, 0.30),
                         g.math("MULTIPLY", H, 0.55),
                         seed_off=73.0,
                         values_over={"Style": 3, "Towers Up": 0,
                                      "Towers Down": 1, "Ledges": 2,
                                      "Top Plateaus": 0,
                                      "Base Flare": 0.0, "Trenches": 0,
                                      "Hangars": 0})
    g.l(move(out_sock(sc_spike, "Geometry"), 0.0, 0.0,
             g.math("MULTIPLY", H, -0.30)), saucer.inputs[0])
    dome = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", W, 0.55)}, values={"Variant": 0})
    g.l(move(out_sock(dome, "Geometry"), 0.0, 0.0,
             g.math("MULTIPLY", H, 0.13)), saucer.inputs[0])
    # radial landing piers around the rim
    padc = gcall(g, parts["pad"], wires={
        "Reach": g.math("MULTIPLY", W, 0.28),
        "Root": g.math("MULTIPLY", group_in(g, "Pad Radius"), W),
        "Size": g.math("MULTIPLY",
                       g.math("MULTIPLY", W, 0.11),
                       group_in(g, "Pad Size")),
        "Verts": pad_verts},
        values={"Lights": True})
    p_pts, p_ang, _ = ring_pts(
        group_in(g, "Pads"),
        g.math("MULTIPLY", group_in(g, "Pad Radius"), W),
        g.math("MULTIPLY",
               g.math("SUBTRACT", group_in(g, "Pad Tier"), 0.5),
               g.math("MULTIPLY", H, 0.18)), 0.0)
    p2i = g.n("GeometryNodeGeometryToInstance")
    g.l(out_sock(padc, "Geometry"), p2i.inputs[0])
    g.l(ring_realize(p_pts, p_ang, out_sock(p2i, "Instances")),
        saucer.inputs[0])

    # =========================== FORM 3: MONOLITH BASTION ==============
    bastion = g.n("GeometryNodeJoinGeometry")
    bs_core = core_call(g.math("MULTIPLY", W, 1.35),
                        g.math("MULTIPLY", Dp, 1.35),
                        g.math("MULTIPLY", H, 0.75),
                        seed_off=91.0,
                        wires_over={"Corner Cut": g.math(
                            "MULTIPLY", group_in(g, "Corner Cut"), 0.5)})
    g.l(out_sock(bs_core, "Geometry"), bastion.inputs[0])
    # flank tank farms (refinery bastion)
    for i in range(2):
        btank = gcall(g, parts["tank"], wires={
            "Count": group_in(g, "Tanks Per Cluster"),
            "Radius": g.math("MULTIPLY",
                             g.math("MULTIPLY", W, 0.07),
                             group_in(g, "Tank Scale")),
            "Length": g.math("MULTIPLY",
                             g.math("MULTIPLY", W, 0.42),
                             group_in(g, "Tank Scale")),
            "Seed": g.math("ADD", seed, 13.0 * i)})
        side = 1.0 if i == 0 else -1.0
        gated(move(out_sock(btank, "Geometry"),
                   g.math("MULTIPLY", W, 0.62 * side),
                   g.math("MULTIPLY", Dp, 0.3 * side),
                   g.math("MULTIPLY", H, -0.08)),
              int_gt(group_in(g, "Tank Clusters"), i), bastion)

    # ---- pick the form ------------------------------------------------
    fsel = g.n("GeometryNodeIndexSwitch", data_type="GEOMETRY")
    while len(fsel.index_switch_items) < 4:
        fsel.index_switch_items.new()
    g.l(group_in(g, "Form"), in_sock(fsel, "Index"))
    for i, br in enumerate((spire, yard, saucer, bastion)):
        g.l(out_sock(br, "Geometry"), in_sock(fsel, str(i)))
    formed = out_sock(fsel, "Output")

    out = g.n("GeometryNodeJoinGeometry")
    g.l(formed, out.inputs[0])

    # ---- shared fixtures: raycast onto whichever form won -------------
    def place_ray(px, py, part_geo, gate, down=True, upright=False,
                  sink=None, rot=None):
        rc = g.n("GeometryNodeRaycast")
        g.l(formed, in_sock(rc, "Target Geometry"))
        srcv = g.n("ShaderNodeCombineXYZ")
        for i, t in enumerate((px, py)):
            if hasattr(t, "is_linked"):
                g.l(t, srcv.inputs[i])
            else:
                srcv.inputs[i].default_value = t
        g.l(g.math("MULTIPLY", H, 3.0 if down else -3.0), srcv.inputs[2])
        g.l(srcv.outputs[0], in_sock(rc, "Source Position"))
        in_sock(rc, "Ray Direction").default_value = \
            (0.0, 0.0, -1.0 if down else 1.0)
        g.l(g.math("MULTIPLY", H, 6.0), in_sock(rc, "Ray Length"))
        pt = g.n("GeometryNodePoints")
        in_sock(pt, "Count").default_value = 1
        land = out_sock(rc, "Hit Position")
        if sink is not None:
            sv2 = g.n("ShaderNodeCombineXYZ")
            g.l(g.math("MULTIPLY", sink, -1.0 if down else 1.0),
                sv2.inputs[2])
            va = g.n("ShaderNodeVectorMath", operation="ADD")
            g.l(land, va.inputs[0])
            g.l(sv2.outputs[0], va.inputs[1])
            land = va.outputs[0]
        g.l(land, in_sock(pt, "Position"))
        if rot is not None:
            pre = g.n("GeometryNodeTransform")
            g.l(part_geo, pre.inputs[0])
            in_sock(pre, "Rotation").default_value = rot
            part_geo = out_sock(pre, "Geometry")
        iop2 = g.n("GeometryNodeInstanceOnPoints")
        g.l(out_sock(pt, "Points"), iop2.inputs[0])
        g.l(part_geo, in_sock(iop2, "Instance"))
        if not upright:
            al = g.n("FunctionNodeAlignEulerToVector", axis="Z")
            g.l(out_sock(rc, "Hit Normal"), in_sock(al, "Vector"))
            g.l(out_sock(al, "Rotation"), in_sock(iop2, "Rotation"))
        rl2 = g.n("GeometryNodeRealizeInstances")
        g.l(out_sock(iop2, "Instances"), rl2.inputs[0])
        gsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(gate, in_sock(gsw, "Switch"))
        g.l(out_sock(rl2, "Geometry"), in_sock(gsw, "True", "GEOMETRY"))
        g.l(out_sock(gsw, "Output", "GEOMETRY"), out.inputs[0])

    grate = gcall(g, parts["grate"], wires={
        "Length": g.math("MULTIPLY", W, 0.16),
        "Width": g.math("MULTIPLY", W, 0.10)}, values={"Slats": 10})
    for i, (xf, yf) in enumerate(((-0.10, 0.22), (0.14, -0.20),
                                  (-0.24, -0.16), (0.20, 0.24))):
        place_ray(g.math("MULTIPLY", W, xf), g.math("MULTIPLY", Dp, yf),
                  out_sock(grate, "Geometry"),
                  int_gt(group_in(g, "Vents"), i))
    rad0 = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", W, 0.14)}, values={"Variant": 0})
    rad1 = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", W, 0.11)}, values={"Variant": 1})
    # dish mount bracket: the dish cone only GRAZES its housing box in
    # AABB terms — tilted onto a sloped crown the boxes separate and the
    # dish reads as a floating shell. A bracket that truly intersects
    # both volumes survives any align-to-normal rotation.
    s_r1 = g.math("MULTIPLY", W, 0.11)
    rad1j = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(rad1, "Geometry"), rad1j.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", s_r1, 0.14),
                          g.math("MULTIPLY", s_r1, 0.10),
                          g.math("MULTIPLY", s_r1, 0.20)), None,
              (g.math("MULTIPLY", s_r1, 0.10), 0.0,
               g.math("MULTIPLY", s_r1, 0.66)), mats["dark"]),
        rad1j.inputs[0])
    place_ray(g.math("MULTIPLY", W, -0.05),
              g.math("MULTIPLY", Dp, -0.12),
              out_sock(rad0, "Geometry"),
              int_gt(group_in(g, "Radomes"), 0))
    place_ray(g.math("MULTIPLY", W, 0.18),
              g.math("MULTIPLY", Dp, 0.06),
              out_sock(rad1j, "Geometry"),
              int_gt(group_in(g, "Radomes"), 1))
    mast = gcall(g, parts["mast"], wires={
        "Size": g.math("MULTIPLY", W, 0.16)})
    for i, (xf, yf) in enumerate(((-0.28, 0.08), (0.10, 0.26),
                                  (0.26, -0.12))):
        place_ray(g.math("MULTIPLY", W, xf), g.math("MULTIPLY", Dp, yf),
                  out_sock(mast, "Geometry"),
                  int_gt(group_in(g, "Antennas"), i), upright=True)
    # comm spires: the antenna mast in its tower register (x3-6 scale)
    spire_m = gcall(g, parts["mast"], wires={
        "Size": g.math("MULTIPLY",
                       g.math("MULTIPLY", H, 0.11),
                       group_in(g, "Spire Height"))})
    for i, (xf, yf) in enumerate(((0.0, 0.0), (0.24, -0.20),
                                  (-0.22, 0.18))):
        place_ray(g.math("MULTIPLY", W, xf), g.math("MULTIPLY", Dp, yf),
                  out_sock(spire_m, "Geometry"),
                  int_gt(group_in(g, "Spires"), i), upright=True,
                  sink=g.math("MULTIPLY", H, 0.01))
    chev = gcall(g, parts["chevron"], wires={
        "Size": g.math("MULTIPLY", W, 0.30)})
    place_ray(g.math("MULTIPLY", W, 0.26), 0.0,
              out_sock(chev, "Geometry"),
              int_gt(group_in(g, "Decals"), 0))
    hnum = gcall(g, parts["number"], wires={
        "Size": g.math("MULTIPLY", W, 0.18),
        "Value": g.rand_float(0.0, 99.9, None,
                              g.math("ADD", seed, 77.0))})
    place_ray(g.math("MULTIPLY", W, 0.12), 0.0,
              out_sock(hnum, "Geometry"),
              int_gt(group_in(g, "Decals"), 1))
    # turrets: crown hardpoint ring (the bastion signature; the knob is
    # live on every form)
    tur = gcall(g, parts["turret"], wires={
        "Size": g.math("MULTIPLY",
                       g.math("MULTIPLY", W, 0.10),
                       group_in(g, "Turret Scale"))})
    import math as _m
    for i in range(8):
        a = i * TAU / 8.0
        place_ray(g.math("MULTIPLY", W, 0.34 * _m.cos(a)),
                  g.math("MULTIPLY", Dp, 0.34 * _m.sin(a)),
                  out_sock(tur, "Geometry"),
                  int_gt(group_in(g, "Turrets"), i),
                  sink=g.math("MULTIPLY", W, 0.005))
    # nav beacons: crown / keel / two crown flanks, half-embedded
    beac = _prim(g, "cube", (g.math("MULTIPLY", W, 0.02),
                             g.math("MULTIPLY", W, 0.02),
                             g.math("MULTIPLY", W, 0.02)), None, None,
                 mats["beacon"])
    for i, (xf, yf, down) in enumerate(((0.0, 0.0, True),
                                        (0.0, 0.0, False),
                                        (0.30, 0.0, True),
                                        (-0.30, 0.0, True))):
        place_ray(g.math("MULTIPLY", W, xf), g.math("MULTIPLY", Dp, yf),
                  beac, int_gt(group_in(g, "Beacons"), i), down=down,
                  sink=g.math("MULTIPLY", W, -0.008))

    final = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(out, "Geometry"), final.inputs[0])
    return g.finish(out_sock(final, "Geometry"))


# ---------------------------------------------------------------- main -----

def main():
    outp = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    hg = fi_deps(DEP_WANT)
    mats = build_station_materials()
    parts = {"profile": build_station_profile()}
    parts["core"] = build_station_core(parts["profile"])
    parts["dress"] = build_station_dress(mats, hg, parts)
    parts["core_dressed"] = build_station_core_dressed(parts)
    # fleet fixtures rebuilt against the STATION mats dict (same role
    # keys), renamed so both kits can coexist in one asset browser
    for key, builder, name in (
            ("grate", fleet.build_vent_grate, "FI_StationVentGrate"),
            ("radome", fleet.build_radome, "FI_StationRadome"),
            ("mast", fleet.build_antenna_mast, "FI_StationAntennaMast"),
            ("boom", fleet.build_sensor_boom, "FI_StationSensorBoom"),
            ("chevron", fleet.build_chevron, "FI_StationChevron"),
            ("number", fleet.build_hull_number, "FI_StationHullNumber")):
        grp = builder(mats)
        grp.name = name
        parts[key] = grp
    parts["truss"] = build_station_truss(mats)
    parts["tank"] = build_station_tank(mats)
    parts["pad"] = build_dock_pad(mats)
    parts["ring"] = build_station_ring(mats)
    parts["turret"] = build_station_turret(mats)
    parts["maw"] = build_dock_maw(mats, parts)
    parts["arm"] = build_station_arm(mats, parts)
    parts["station"] = build_station(mats, hg, parts)
    contract = {}
    for ng in parts.values():
        contract[ng.name] = [
            {"name": it.name, "in_out": it.in_out,
             "type": getattr(it, "socket_type", "?"),
             "identifier": it.identifier}
            for it in ng.interface.items_tree
            if it.item_type == "SOCKET"]
    with open(os.path.join(os.path.dirname(outp), "station_contract.json"),
              "w") as f:
        json.dump(contract, f, indent=1, sort_keys=True)
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    print(f"build_stationkit: OK -> {outp} ({len(parts)} groups + "
          f"{len(hg)} native deps)")


if __name__ == "__main__":
    main()
