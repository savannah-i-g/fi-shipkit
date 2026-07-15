#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# build_warkit.py -- FI_WarKit.blend: the FI NAVAL military generator.
#
#   blender -b --python build_warkit.py -- [--out FI_WarKit.blend]
#
# HOUSE LANGUAGE (revision 2 — "make this unique, far sleeker"):
#   - blade-lofted monocoque hulls: long chined blades, wedge prow,
#     boat-tail stern — sleek by construction, not box-grown
#   - growth zone adds only FAIRED pods (strongly tapered blisters)
#   - UNIQUE DRIVES (no bell cones): 0 = recessed linear slat array in a
#     sculpted cowl with vector vanes, 1 = halo ring drive, 2 = tri-prong
#   - chine LIGHT-LINES (faction-tinted emissive strips) — the signature
#   - flush low-profile turrets in recessed seats; speed-line recesses
#   - recursive panel hierarchy kept but shallow (sleek, not crusty)
#   - factions: MCR-dark / UNN-grey / BEL-rust palettes + line colours

import bpy
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fi_gn_lib import (TAU, G, gcall, group_in, in_sock, out_sock,  # noqa
                       _prim, _shader_wear, _base_panels, mat, fi_deps)

HERE = os.path.dirname(os.path.abspath(__file__))
DEP_WANT = ["Mesh Face Divider", "Mirror", "Checker Selection",
            "Bend", "Mesh Relax", "Taper"]

# fixed house taper (shared by loft + external samplers)
NOSE_FRAC, NOSE_W, NOSE_H = 0.38, 0.10, 0.22
TAIL_FRAC, TAIL_W, TAIL_H = 0.22, 0.42, 0.55


def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = os.path.join(HERE, "FI_WarKit.blend")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    return out


# ---------------------------------------------------------- materials ------

def build_war_materials():
    m = {}
    m["dark"] = mat("FI_War_Dark", (0.09, 0.09, 0.10), 0.75, 0.4)
    m["metal"] = mat("FI_War_Metal", (0.30, 0.31, 0.33), 0.5, 0.8)
    m["cavity"] = mat("FI_War_Cavity", (0.03, 0.03, 0.04), 0.9, 0.1)
    m["glass"] = mat("FI_War_Glass", (0.04, 0.08, 0.12), 0.08, 0.0,
                     emissive=(0.10, 0.20, 0.30), estrength=0.8)
    facs = {
        "MCR": dict(tone=(0.15, 0.14, 0.15), accent=(0.48, 0.06, 0.05),
                    line=(1.0, 0.22, 0.12), wear=0.5, grime=0.45),
        "UNN": dict(tone=(0.52, 0.55, 0.60), accent=(0.10, 0.22, 0.48),
                    line=(0.45, 0.75, 1.0), wear=0.4, grime=0.3),
        "BEL": dict(tone=(0.40, 0.29, 0.21), accent=(0.55, 0.38, 0.10),
                    line=(1.0, 0.62, 0.20), wear=0.85, grime=0.7),
    }
    for key, f in facs.items():
        hull = mat(f"FI_War_{key}_Hull", f["tone"], 0.5, 0.55)
        _shader_wear(hull, lambda nt, k=key: _base_panels(
                         nt, "hull-texture2", facs[k]["tone"], 0.28),
                     wear=f["wear"], grime=f["grime"], rough=0.5, metal=0.55)
        acc = mat(f"FI_War_{key}_Accent", f["accent"], 0.5, 0.2)
        _shader_wear(acc, lambda nt, k=key: _base_panels(
                         nt, "hull-texture2", facs[k]["accent"], 0.28),
                     wear=f["wear"] * 0.9, grime=f["grime"] * 0.6,
                     wear_col=(0.35, 0.34, 0.33), rough=0.5, metal=0.1)
        m[f"hull_{key}"] = hull
        m[f"accent_{key}"] = acc
        m[f"line_{key}"] = mat(f"FI_War_{key}_Line",
                               tuple(c * 0.1 for c in f["line"]), 0.4, 0.0,
                               emissive=f["line"], estrength=4.0)
        m[f"drive_{key}"] = mat(f"FI_War_{key}_Drive",
                                (0.05, 0.05, 0.06), 0.5, 0.0,
                                emissive=f["line"], estrength=7.0)
    return m


# --------------------------------------------------------- war profile -----

def build_war_profile():
    """t (0 tail..1 nose) -> W,H. ANGULAR edition: linear wedge ramps plus
    two seeded hard STEPS per axis; Silhouette picks the archetype
    (0 wedge / 1 dagger / 2 hammer). No smooth curves anywhere."""
    g = G("FI_WarProfile")
    g.sock_in("t", "NodeSocketFloat", 0.5)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Silhouette", "NodeSocketInt", 0, 0, 2)
    g.sock_out("W", "NodeSocketFloat")
    g.sock_out("H", "NodeSocketFloat")
    g.sock_in("Step Strength", "NodeSocketFloat", 1.0, 0.0, 2.0)
    g.sock_in("Step Count", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Nose Frac", "NodeSocketFloat", 0.35, 0.05, 0.9)
    g.sock_in("Tail Frac", "NodeSocketFloat", 0.45, 0.05, 0.9)
    g.sock_in("Side Profile", "NodeSocketInt", 0, 0, 2)
    t = group_in(g, "t")
    seed = group_in(g, "Seed")
    sil = group_in(g, "Silhouette")

    def lramp(v, fmin, fmax, tmin, tmax):
        n = g.n("ShaderNodeMapRange", interpolation_type="LINEAR")
        for s, x in (("Value", v), ("From Min", fmin), ("From Max", fmax),
                     ("To Min", tmin), ("To Max", tmax)):
            sock = in_sock(n, s, "VALUE")
            if hasattr(x, "is_linked"):
                g.l(x, sock)
            else:
                sock.default_value = x
        return out_sock(n, "Result", "VALUE")

    def int_eq(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    def fsw(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, in_sock(n, "Switch"))
        for nm, v in (("False", off), ("True", on)):
            s = in_sock(n, nm, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, s)
            else:
                s.default_value = v
        return out_sock(n, "Output", "VALUE")

    is1 = int_eq(sil, 1)
    is2 = int_eq(sil, 2)
    NF, TF = group_in(g, "Nose Frac"), group_in(g, "Tail Frac")
    nose_lo = g.math("SUBTRACT", 1.0, NF)
    # archetype base wedges built on adjustable nose/tail lengths
    w_wedge = g.math("MINIMUM",
                     lramp(t, nose_lo, 0.97, 1.0, 0.10),
                     lramp(t, 0.0, 0.06, 0.70, 1.0))
    w_dag = g.math("MINIMUM", lramp(t, 0.0, TF, 0.55, 1.0),
                   lramp(t, nose_lo, 1.0, 1.0, 0.08))
    w_ham = g.math("MAXIMUM",
                   g.math("MULTIPLY",
                          g.math("GREATER_THAN", t, nose_lo), 1.0),
                   g.math("MINIMUM", lramp(t, 0.0, 0.2, 0.75, 0.55),
                          lramp(t, 0.2, nose_lo, 0.55, 0.42)))
    w = fsw(is1, w_wedge, w_dag)
    w = fsw(is2, w, w_ham)
    # up to four seeded hard steps, gated by Step Count, scaled by Strength
    for k, (mn, mx) in enumerate(((0.30, 0.55), (0.58, 0.85),
                                  (0.15, 0.35), (0.42, 0.70))):
        bx = g.rand_float(mn, mx, None, g.math("ADD", seed, 31.0 + k))
        sh = g.math("MULTIPLY",
                    g.rand_float(-0.18, 0.22, None,
                                 g.math("ADD", seed, 41.0 + k)),
                    group_in(g, "Step Strength"))
        gate = g.n("FunctionNodeCompare", data_type="INT",
                   operation="GREATER_THAN")
        g.l(group_in(g, "Step Count"), in_sock(gate, "A", "INT"))
        in_sock(gate, "B", "INT").default_value = k
        stp = g.math("MULTIPLY",
                     g.math("MULTIPLY",
                            g.math("GREATER_THAN", t, bx), sh),
                     out_sock(gate, "Result"))
        w = g.math("ADD", w, stp)
    w = g.math("MAXIMUM", 0.10, g.math("MINIMUM", w, 1.0))
    # side profile archetypes: 0 level / 1 raked bow-high / 2 humpback
    h0 = g.math("MINIMUM", lramp(t, 0.0, 0.10, 0.72, 1.0),
                lramp(t, 0.55, 1.0, 1.0, 0.16))
    h1 = g.math("MINIMUM", lramp(t, 0.0, 0.85, 0.45, 1.0),
                lramp(t, 0.80, 1.0, 1.0, 0.30))
    h2 = g.math("MINIMUM", lramp(t, 0.0, 0.45, 0.55, 1.05),
                lramp(t, 0.45, 1.0, 1.05, 0.20))
    sp = group_in(g, "Side Profile")
    h = fsw(int_eq(sp, 1), h0, h1)
    h = fsw(int_eq(sp, 2), h, h2)
    bh = g.rand_float(0.35, 0.75, None, g.math("ADD", seed, 51.0))
    sh2 = g.math("MULTIPLY",
                 g.rand_float(-0.15, 0.15, None,
                              g.math("ADD", seed, 52.0)),
                 group_in(g, "Step Strength"))
    h = g.math("ADD", h, g.math("MULTIPLY",
               g.math("GREATER_THAN", t, bh), sh2))
    h = g.math("MAXIMUM", 0.14, g.math("MINIMUM", h, 1.10))
    g.gout = g.n("NodeGroupOutput")
    g.l(w, g.gout.inputs[0])
    g.l(h, g.gout.inputs[1])
    g.ng.asset_mark()
    return g.ng


# ------------------------------------------------------------ war hull -----

def build_war_hull(hg, profile):
    """Sleek blade loft + a few strongly-faired pod blisters, mirrored."""
    g = G("FI_WarHull")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Length", "NodeSocketFloat", 45.0, 5.0, 1200.0)
    g.sock_in("Beam", "NodeSocketFloat", 10.0, 1.0, 400.0)
    g.sock_in("Depth", "NodeSocketFloat", 7.0, 1.0, 400.0)
    g.sock_in("Chines", "NodeSocketInt", 8, 6, 16)
    g.sock_in("Stations", "NodeSocketInt", 28, 8, 96)
    g.sock_in("Pods", "NodeSocketInt", 2, 0, 6)
    g.sock_in("Pod Fairing", "NodeSocketFloat", 0.72, 0.3, 0.95)
    g.sock_in("Silhouette", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Asymmetry", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Section", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Section Exponent", "NodeSocketFloat", 1.0, 0.5, 2.5)
    g.sock_in("Side Profile", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Step Strength", "NodeSocketFloat", 1.0, 0.0, 2.0)
    g.sock_in("Step Count", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Nose Frac", "NodeSocketFloat", 0.35, 0.05, 0.9)
    g.sock_in("Tail Frac", "NodeSocketFloat", 0.45, 0.05, 0.9)
    g.sock_in("Bend", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Blend", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Dorsal Taper", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Hump Position", "NodeSocketFloat", -1.0, -1.0, 0.9)
    g.sock_in("Hump Length", "NodeSocketFloat", -1.0, -1.0, 0.5)
    g.sock_in("Hump Height", "NodeSocketFloat", -1.0, -1.0, 0.6)
    g.sock_in("Detail Extrusions", "NodeSocketInt", 0, 0, 8)
    L, B, D = (group_in(g, "Length"), group_in(g, "Beam"),
               group_in(g, "Depth"))
    seed = group_in(g, "Seed")

    cyl = g.n("GeometryNodeMeshCylinder")
    g.l(group_in(g, "Chines"), in_sock(cyl, "Vertices"))
    g.l(group_in(g, "Stations"), in_sock(cyl, "Side Segments"))
    in_sock(cyl, "Radius").default_value = 1.0
    in_sock(cyl, "Depth").default_value = 1.0
    rot = g.n("GeometryNodeTransform")
    g.l(out_sock(cyl, "Mesh"), rot.inputs[0])
    in_sock(rot, "Rotation").default_value = (0.0, math.pi / 2.0, 0.0)

    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    x_raw, y0, z0 = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    t = g.math("ADD", x_raw, 0.5)
    tp = gcall(g, profile, wires={
        "t": t, "Seed": seed, "Silhouette": group_in(g, "Silhouette"),
        "Step Strength": group_in(g, "Step Strength"),
        "Step Count": group_in(g, "Step Count"),
        "Nose Frac": group_in(g, "Nose Frac"),
        "Tail Frac": group_in(g, "Tail Frac"),
        "Side Profile": group_in(g, "Side Profile")})

    # ---- cross-SECTION identity: reshape the unit ring before scaling ----
    #  0 flattened octagon (house)   1 diamond (chine-heavy, exponent)
    #  2 trapezoid (wide belly)      3 inverted trapezoid (wide dorsal)
    def fsw_h(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, in_sock(n, "Switch"))
        for nm, v in (("False", off), ("True", on)):
            s = in_sock(n, nm, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, s)
            else:
                s.default_value = v
        return out_sock(n, "Output", "VALUE")

    def ieq(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    sec = group_in(g, "Section")
    sexp = group_in(g, "Section Exponent")
    y_dia = g.math("MULTIPLY", g.math("SIGN", y0),
                   g.math("POWER", g.math("ABSOLUTE", y0), sexp))
    z_dia = g.math("MULTIPLY", g.math("SIGN", z0),
                   g.math("POWER", g.math("ABSOLUTE", z0), sexp))
    y_trap = g.math("MULTIPLY", y0,
                    g.math("SUBTRACT", 1.0, g.math("MULTIPLY", z0, 0.42)))
    y_itrap = g.math("MULTIPLY", y0,
                     g.math("ADD", 1.0, g.math("MULTIPLY", z0, 0.42)))
    y_sec = fsw_h(ieq(sec, 1), y0, y_dia)
    y_sec = fsw_h(ieq(sec, 2), y_sec, y_trap)
    y_sec = fsw_h(ieq(sec, 3), y_sec, y_itrap)
    z_sec = fsw_h(ieq(sec, 1), z0, z_dia)
    y0, z0 = y_sec, z_sec

    # blade: flatten verticals, slight dorsal ridge lift
    above = g.math("GREATER_THAN", z0, 0.0)
    tb = g.math("ADD", 0.92, g.math("MULTIPLY", above, -0.22))  # top 0.70
    nx = g.math("MULTIPLY", x_raw, L)
    ny = g.math("MULTIPLY", y0, g.math("MULTIPLY",
                g.math("DIVIDE", B, 2.0), out_sock(tp, "W")))
    nz = g.math("MULTIPLY", z0, g.math("MULTIPLY", tb, g.math(
        "MULTIPLY", g.math("DIVIDE", D, 2.0), out_sock(tp, "H"))))
    # INTEGRATED superstructure: a seeded angular dorsal hump IN the skin —
    # part of the hull, paneled and textured continuously (no boxes)
    def auto_or(user, seeded):
        auto = g.math("LESS_THAN", user, -0.001)
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(auto, in_sock(n, "Switch"))
        g.l(user, in_sock(n, "False", "VALUE"))
        g.l(seeded, in_sock(n, "True", "VALUE"))
        return out_sock(n, "Output", "VALUE")
    h_a = auto_or(group_in(g, "Hump Position"),
                  g.rand_float(0.16, 0.40, None,
                               g.math("ADD", seed, 71.0)))
    h_b = g.math("ADD", h_a,
                 auto_or(group_in(g, "Hump Length"),
                         g.rand_float(0.10, 0.26, None,
                                      g.math("ADD", seed, 72.0))))
    h_amp = auto_or(group_in(g, "Hump Height"),
                    g.rand_float(0.14, 0.34, None,
                                 g.math("ADD", seed, 73.0)))
    in_band = g.math("MULTIPLY", g.math("GREATER_THAN", t, h_a),
                     g.math("GREATER_THAN", h_b, t))
    crest = g.math("MAXIMUM", 0.0, z0)
    hump = g.math("MULTIPLY", g.math("MULTIPLY", in_band, crest),
                  g.math("MULTIPLY", h_amp, D))
    nz = g.math("ADD", nz, hump)
    # hump narrows the crest for a keel-backed superstructure silhouette
    ny = g.math("MULTIPLY", ny,
                g.math("SUBTRACT", 1.0,
                       g.math("MULTIPLY",
                              g.math("MULTIPLY", in_band, crest), 0.35)))
    npv = g.n("ShaderNodeCombineXYZ")
    g.l(nx, npv.inputs[0])
    g.l(ny, npv.inputs[1])
    g.l(nz, npv.inputs[2])
    sp = g.n("GeometryNodeSetPosition")
    g.l(out_sock(rot, "Geometry"), sp.inputs[0])
    g.l(npv.outputs[0], in_sock(sp, "Position"))
    # ANGULAR: flat shading — facets are the language now
    loft = out_sock(sp, "Geometry")

    # faired pod blisters via a short repeat zone on flank/top faces
    ri = g.n("GeometryNodeRepeatInput")
    ro = g.n("GeometryNodeRepeatOutput")
    ri.pair_with_output(ro)
    g.l(group_in(g, "Pods"), in_sock(ri, "Iterations"))
    g.l(loft, in_sock(ri, "Geometry"))
    zg = out_sock(ri, "Geometry")
    it = out_sock(ri, "Iteration")
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    posz = g.n("GeometryNodeInputPosition")
    pzs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(posz, "Position"), pzs.inputs[0])
    mid_band = g.math("LESS_THAN", g.math("ABSOLUTE", pzs.outputs[0]),
                      g.math("MULTIPLY", L, 0.28))
    lateral = g.math("GREATER_THAN",
                     g.math("ABSOLUTE", ns.outputs[1]), 0.55)
    # grow strictly on the kept (+Y) half: a blister on a face straddling
    # the centreline gets CUT OPEN by the delete-half pass and the mirror
    # cannot match its torn rim
    y_safe = g.math("GREATER_THAN", pzs.outputs[1],
                    g.math("MULTIPLY", B, 0.06))
    okf = g.math("MULTIPLY", g.math("MULTIPLY", mid_band, lateral), y_safe)
    fid = g.n("GeometryNodeInputIndex")
    wsel = g.math("MULTIPLY", okf,
                  g.math("ADD", 0.2,
                         g.rand_float(0.0, 1.0, out_sock(fid, "Index"),
                                      g.math("ADD", seed,
                                             g.math("MULTIPLY", it, 7.0)))))
    stat = g.n("GeometryNodeAttributeStatistic", domain="FACE")
    g.l(zg, stat.inputs[0])
    g.l(wsel, in_sock(stat, "Attribute"))
    pick = g.math("GREATER_THAN", wsel,
                  g.math("SUBTRACT", out_sock(stat, "Max", "VALUE"), 1e-4))
    ext = g.n("GeometryNodeExtrudeMesh", mode="FACES")
    g.l(zg, ext.inputs[0])
    g.l(pick, in_sock(ext, "Selection"))
    g.l(g.math("MULTIPLY", B,
               g.math("ADD", 0.05,
                      g.math("MULTIPLY",
                             g.rand_float(0.0, 1.0, None,
                                          g.math("ADD", seed,
                                                 g.math("MULTIPLY", it,
                                                        13.0))), 0.09))),
        in_sock(ext, "Offset Scale"))
    in_sock(ext, "Individual").default_value = True
    shr = g.n("GeometryNodeScaleElements", domain="FACE")
    g.l(out_sock(ext, "Mesh"), shr.inputs[0])
    g.l(out_sock(ext, "Top"), in_sock(shr, "Selection"))
    g.l(group_in(g, "Pod Fairing"), in_sock(shr, "Scale"))
    g.l(out_sock(shr, "Geometry"), in_sock(ro, "Geometry"))
    grown = out_sock(ro, "Geometry")

    # symmetry: +Y half mirrored (pods land on both flanks, matched)
    p2 = g.n("GeometryNodeInputPosition")
    p2s = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(p2, "Position"), p2s.inputs[0])
    below = g.math("LESS_THAN", p2s.outputs[1],
                   g.math("MULTIPLY", B, -0.01))
    dele = g.n("GeometryNodeDeleteGeometry", domain="FACE")
    g.l(grown, dele.inputs[0])
    g.l(below, in_sock(dele, "Selection"))
    mir = gcall(g, hg["Mirror"], wires={
        "Geometry": out_sock(dele, "Geometry")},
        values={"Y": True, "Merge By Distance": True, "Distance": 0.05})
    sym = out_sock(mir, "Geometry")

    # ---- reference-generator grammar at small scale: seeded quantized
    # detail extrusions (surface machinery masses, silhouette preserved) ----
    ri2 = g.n("GeometryNodeRepeatInput")
    ro2 = g.n("GeometryNodeRepeatOutput")
    ri2.pair_with_output(ro2)
    g.l(group_in(g, "Detail Extrusions"), in_sock(ri2, "Iterations"))
    g.l(sym, in_sock(ri2, "Geometry"))
    zg2 = out_sock(ri2, "Geometry")
    it2 = out_sock(ri2, "Iteration")
    fid2 = g.n("GeometryNodeInputIndex")
    w2 = g.rand_float(0.0, 1.0, out_sock(fid2, "Index"),
                      g.math("ADD", seed, g.math("MULTIPLY", it2, 23.0)))
    st2 = g.n("GeometryNodeAttributeStatistic", domain="FACE")
    g.l(zg2, st2.inputs[0])
    g.l(w2, in_sock(st2, "Attribute"))
    pick2 = g.math("GREATER_THAN", w2,
                   g.math("SUBTRACT", out_sock(st2, "Max", "VALUE"), 1e-4))
    ex2 = g.n("GeometryNodeExtrudeMesh", mode="FACES")
    g.l(zg2, ex2.inputs[0])
    g.l(pick2, in_sock(ex2, "Selection"))
    g.l(g.math("SNAP",
               g.math("MULTIPLY", B,
                      g.rand_float(0.02, 0.06, None,
                                   g.math("ADD", seed,
                                          g.math("MULTIPLY", it2, 29.0)))),
               g.math("MULTIPLY", B, 0.01)), in_sock(ex2, "Offset Scale"))
    in_sock(ex2, "Individual").default_value = True
    sh3 = g.n("GeometryNodeScaleElements", domain="FACE")
    g.l(out_sock(ex2, "Mesh"), sh3.inputs[0])
    g.l(out_sock(ex2, "Top"), in_sock(sh3, "Selection"))
    in_sock(sh3, "Scale").default_value = 0.82
    g.l(out_sock(sh3, "Geometry"), in_sock(ro2, "Geometry"))
    sym = out_sock(ro2, "Geometry")

    # ---- dorsal taper (FI_Taper about Z) ----------------------------------
    tap = gcall(g, hg["Taper"], wires={
        "Geometry": sym,
        "Upper Factor": g.math("ADD", 1.0,
                               g.math("MULTIPLY",
                                      group_in(g, "Dorsal Taper"), 0.45)),
        "Lower Factor": g.math("SUBTRACT", 1.0,
                               g.math("MULTIPLY",
                                      group_in(g, "Dorsal Taper"), 0.25))},
        values={"Axis": (0.0, 0.0, 1.0)})
    taper_on = g.math("GREATER_THAN",
                      g.math("ABSOLUTE", group_in(g, "Dorsal Taper")), 0.02)
    tpsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(taper_on, in_sock(tpsw, "Switch"))
    g.l(sym, in_sock(tpsw, "False", "GEOMETRY"))
    g.l(out_sock(tap, "Geometry"), in_sock(tpsw, "True", "GEOMETRY"))
    sym = out_sock(tpsw, "Output", "GEOMETRY")

    # ---- spine bend (subtle raked keel curve) ------------------------------
    bnd = gcall(g, hg["Bend"], wires={
        "Geometry": sym,
        "Angle": g.math("MULTIPLY", group_in(g, "Bend"), 0.35)},
        values={"Axis": (0.0, 1.0, 0.0)})
    bend_on = g.math("GREATER_THAN",
                     g.math("ABSOLUTE", group_in(g, "Bend")), 0.02)
    bsw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(bend_on, in_sock(bsw2, "Switch"))
    g.l(sym, in_sock(bsw2, "False", "GEOMETRY"))
    g.l(out_sock(bnd, "Geometry"), in_sock(bsw2, "True", "GEOMETRY"))
    sym = out_sock(bsw2, "Output", "GEOMETRY")

    # ---- blend: angular <-> softened (FI_MeshRelax) ------------------------
    rlx = gcall(g, hg["Mesh Relax"], wires={
        "Mesh": sym,
        "Weight": g.math("MULTIPLY", group_in(g, "Blend"), 0.8)},
        values={"Iterations": 6, "Pin Boundary": False})
    blend_on = g.math("GREATER_THAN", group_in(g, "Blend"), 0.02)
    rsw3 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(blend_on, in_sock(rsw3, "Switch"))
    g.l(sym, in_sock(rsw3, "False", "GEOMETRY"))
    g.l(out_sock(rlx, "Mesh"), in_sock(rsw3, "True", "GEOMETRY"))
    sym = out_sock(rsw3, "Output", "GEOMETRY")

    # ---- asymmetry: shear the superstructure crest laterally (deform
    # only — geometry stays integrated, mirror subtly broken) --------------
    p4 = g.n("GeometryNodeInputPosition")
    p4s = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(p4, "Position"), p4s.inputs[0])
    top_frac = g.math("MAXIMUM", 0.0,
                      g.math("SUBTRACT",
                             g.math("DIVIDE", p4s.outputs[2],
                                    g.math("MULTIPLY", D, 0.5)), 0.35))
    sgn = g.math("SUBTRACT",
                 g.math("MULTIPLY",
                        g.math("GREATER_THAN",
                               g.rand_float(0.0, 1.0, None,
                                            g.math("ADD", seed, 62.0)),
                               0.5), 2.0), 1.0)
    shear = g.math("MULTIPLY",
                   g.math("MULTIPLY", top_frac, sgn),
                   g.math("MULTIPLY", g.math("MULTIPLY", B, 0.14),
                          group_in(g, "Asymmetry")))
    sv2 = g.n("ShaderNodeCombineXYZ")
    g.l(shear, sv2.inputs[1])
    shr2 = g.n("GeometryNodeSetPosition")
    g.l(sym, shr2.inputs[0])
    g.l(sv2.outputs[0], in_sock(shr2, "Offset"))
    return g.finish(out_sock(shr2, "Geometry"))


# ---------------------------------------------------------- FI drives ------

def build_linear_drive(mats):
    """FI Naval signature drives. Type 0: recessed vertical glow slats in a
    sculpted cowl with vector vanes. Type 1: halo ring. Type 2: tri-prong.
    Thrust +X, emission aft (-X). Faction glow assigned by the composer via
    the Drive Material input."""
    g = G("FI_LinearDrive")
    g.sock_in("Width", "NodeSocketFloat", 8.0, 0.5, 200.0)
    g.sock_in("Height", "NodeSocketFloat", 4.0, 0.5, 200.0)
    g.sock_in("Slats", "NodeSocketInt", 5, 2, 12)
    g.sock_in("Type", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Segments", "NodeSocketInt", 12, 6, 32)
    g.sock_in("Drive Material", "NodeSocketMaterial")
    g.sock_out("Geometry", "NodeSocketGeometry")
    W, H = group_in(g, "Width"), group_in(g, "Height")
    SEG = group_in(g, "Segments")
    dmat = group_in(g, "Drive Material")

    def set_dmat(geo):
        n = g.n("GeometryNodeSetMaterial")
        g.l(geo, n.inputs[0])
        g.l(dmat, in_sock(n, "Material"))
        return out_sock(n, "Geometry")

    depth = g.math("MULTIPLY", W, 0.45)

    # --- type 0: slat cowl ---
    j0 = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (depth, W, H), None,
              (g.math("MULTIPLY", depth, 0.5), 0, 0), mats["metal"]),
        j0.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", depth, 0.30),
                          g.math("MULTIPLY", W, 0.86),
                          g.math("MULTIPLY", H, 0.78)), None,
              (g.math("MULTIPLY", depth, 0.10), 0, 0), mats["cavity"]),
        j0.inputs[0])
    line = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Slats"), in_sock(line, "Count"))
    lo = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("DIVIDE", g.math("MULTIPLY", W, 0.74),
               g.math("MAXIMUM", 1.0,
                      g.math("SUBTRACT", group_in(g, "Slats"), 1.0))),
        lo.inputs[1])
    g.l(lo.outputs[0], in_sock(line, "Offset"))
    lmv = g.n("GeometryNodeTransform")
    g.l(out_sock(line, "Mesh"), lmv.inputs[0])
    ltv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", depth, 0.04), ltv.inputs[0])
    g.l(g.math("MULTIPLY", W, -0.37), ltv.inputs[1])
    g.l(ltv.outputs[0], in_sock(lmv, "Translation"))
    lpts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(lmv, "Geometry"), lpts.inputs[0])
    slat = set_dmat(_prim(g, "cube",
                          (g.math("MULTIPLY", depth, 0.10),
                           g.math("MULTIPLY", W, 0.045),
                           g.math("MULTIPLY", H, 0.62)), None, None, None))
    si = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(lpts, "Points"), si.inputs[0])
    g.l(slat, in_sock(si, "Instance"))
    g.l(out_sock(si, "Instances"), j0.inputs[0])
    for sgn in (0.46, -0.46):   # vector vanes
        g.l(_prim(g, "cube", (g.math("MULTIPLY", depth, 0.9),
                              g.math("MULTIPLY", W, 0.04),
                              g.math("MULTIPLY", H, 1.15)),
                  (0.0, 0.0, 0.28 * (1 if sgn > 0 else -1)),
                  (g.math("MULTIPLY", depth, 0.35),
                   g.math("MULTIPLY", W, sgn), 0), mats["dark"]),
            j0.inputs[0])

    # --- type 1: halo ring ---
    j1 = g.n("GeometryNodeJoinGeometry")
    R = g.math("MULTIPLY", H, 0.85)
    pts = g.n("GeometryNodePoints")
    in_sock(pts, "Count").default_value = 14
    idx = g.n("GeometryNodeInputIndex")
    th = g.math("MULTIPLY", g.math("DIVIDE", out_sock(idx, "Index"), 14.0),
                TAU)
    pv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", g.math("COSINE", th), R), pv.inputs[1])
    g.l(g.math("MULTIPLY", g.math("SINE", th), R), pv.inputs[2])
    g.l(pv.outputs[0], in_sock(pts, "Position"))
    segp = _prim(g, "cyl", (g.math("MULTIPLY", H, 0.14),
                            g.math("MULTIPLY", R, 0.47)), None, None,
                 mats["metal"], verts=8)
    rv = g.n("ShaderNodeCombineXYZ")
    g.l(th, rv.inputs[0])
    ii = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(pts, "Points"), ii.inputs[0])
    g.l(segp, in_sock(ii, "Instance"))
    g.l(rv.outputs[0], in_sock(ii, "Rotation"))
    g.l(out_sock(ii, "Instances"), j1.inputs[0])
    g.l(set_dmat(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.88), 0.12),
                       (0, math.pi / 2, 0), None, None, verts=SEG)),
        j1.inputs[0])
    for ang in (0.0, 2.094, 4.189):   # pylons to the hull
        g.l(_prim(g, "cube", (g.math("MULTIPLY", W, 0.4), 0.3,
                              g.math("MULTIPLY", R, 0.16)),
                  (ang, 0.0, 0.0),
                  (g.math("MULTIPLY", W, 0.2),
                   g.math("MULTIPLY", R, -0.55 * math.sin(ang)),
                   g.math("MULTIPLY", R, 0.55 * math.cos(ang))),
                  mats["metal"]), j1.inputs[0])

    # --- type 2: tri-prong ---
    j2 = g.n("GeometryNodeJoinGeometry")
    g.l(set_dmat(_prim(g, "sphere", (g.math("MULTIPLY", H, 0.30),), None,
                       (g.math("MULTIPLY", W, -0.05), 0, 0), None,
                       verts=SEG)), j2.inputs[0])
    for ang in (1.571, 3.665, 5.760):
        py = g.math("MULTIPLY", H, 0.62 * math.cos(ang))
        pz = g.math("MULTIPLY", H, 0.62 * math.sin(ang))
        g.l(_prim(g, "cube", (g.math("MULTIPLY", W, 0.75),
                              g.math("MULTIPLY", H, 0.10),
                              g.math("MULTIPLY", H, 0.28)),
                  (ang, 0.0, 0.0),
                  (g.math("MULTIPLY", W, 0.30), py, pz), mats["metal"]),
            j2.inputs[0])
        g.l(set_dmat(_prim(g, "cube", (g.math("MULTIPLY", W, 0.18),
                                       g.math("MULTIPLY", H, 0.05),
                                       g.math("MULTIPLY", H, 0.20)),
                           (ang, 0.0, 0.0),
                           (g.math("MULTIPLY", W, -0.06), py, pz), None)),
            j2.inputs[0])

    def int_eq(a, b):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(a, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    s1 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(int_eq(group_in(g, "Type"), 1), in_sock(s1, "Switch"))
    g.l(out_sock(j0, "Geometry"), in_sock(s1, "False", "GEOMETRY"))
    g.l(out_sock(j1, "Geometry"), in_sock(s1, "True", "GEOMETRY"))
    s2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(int_eq(group_in(g, "Type"), 2), in_sock(s2, "Switch"))
    g.l(out_sock(s1, "Output", "GEOMETRY"), in_sock(s2, "False", "GEOMETRY"))
    g.l(out_sock(j2, "Geometry"), in_sock(s2, "True", "GEOMETRY"))
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(s2, "Output", "GEOMETRY"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


# ------------------------------------------------------ hardpoint groups ---

def build_pdc_turret(mats):
    """Flush low-profile turret in a recessed seat."""
    g = G("FI_PDCTurret")
    g.sock_in("Size", "NodeSocketFloat", 1.0, 0.1, 10.0)
    g.sock_in("Segments", "NodeSocketInt", 10, 6, 32)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    SEG = group_in(g, "Segments")
    j = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.62),
                         g.math("MULTIPLY", S, 0.06)), None,
              (0, 0, g.math("MULTIPLY", S, -0.01)), mats["cavity"],
              verts=SEG), j.inputs[0])
    dome = _prim(g, "sphere", (g.math("MULTIPLY", S, 0.42),), None, None,
                 mats["dark"], verts=SEG)
    sq = g.n("GeometryNodeTransform")
    g.l(dome, sq.inputs[0])
    stv = g.n("ShaderNodeCombineXYZ")
    stv.inputs[0].default_value = 1.0
    stv.inputs[1].default_value = 1.0
    stv.inputs[2].default_value = 0.45
    g.l(stv.outputs[0], in_sock(sq, "Scale"))
    g.l(out_sock(sq, "Geometry"), j.inputs[0])
    for sgn in (0.10, -0.10):
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.04),
                             g.math("MULTIPLY", S, 0.95)),
                  (0, math.pi / 2, 0),
                  (g.math("MULTIPLY", S, 0.5),
                   g.math("MULTIPLY", S, sgn),
                   g.math("MULTIPLY", S, 0.16)), mats["dark"], verts=6),
            j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_vls_pod(mats):
    g = G("FI_VLSPod")
    g.sock_in("Width", "NodeSocketFloat", 3.0, 0.4, 30.0)
    g.sock_in("Tubes X", "NodeSocketInt", 4, 1, 10)
    g.sock_in("Tubes Y", "NodeSocketInt", 3, 1, 8)
    g.sock_out("Geometry", "NodeSocketGeometry")
    W = group_in(g, "Width")
    j = g.n("GeometryNodeJoinGeometry")
    depth = g.math("MULTIPLY", W, 0.14)   # flush profile
    ln = g.math("MULTIPLY", W, 1.35)
    g.l(_prim(g, "cube", (ln, W, depth), None,
              (0, 0, g.math("MULTIPLY", depth, 0.5)), mats["metal"]),
        j.inputs[0])
    grid = g.n("GeometryNodeMeshGrid")
    g.l(g.math("MULTIPLY", ln, 0.8), in_sock(grid, "Size X"))
    g.l(g.math("MULTIPLY", W, 0.72), in_sock(grid, "Size Y"))
    g.l(group_in(g, "Tubes X"), in_sock(grid, "Vertices X"))
    g.l(group_in(g, "Tubes Y"), in_sock(grid, "Vertices Y"))
    gp = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(grid, "Mesh"), gp.inputs[0])
    gm = g.n("GeometryNodeTransform")
    g.l(out_sock(gp, "Points"), gm.inputs[0])
    gv = g.n("ShaderNodeCombineXYZ")
    g.l(depth, gv.inputs[2])
    g.l(gv.outputs[0], in_sock(gm, "Translation"))
    lid = _prim(g, "cube",
                (g.math("MULTIPLY", W, 0.14),
                 g.math("MULTIPLY", W, 0.14),
                 g.math("MULTIPLY", depth, 0.3)), None, None,
                mats["cavity"])
    li = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(gm, "Geometry"), li.inputs[0])
    g.l(lid, in_sock(li, "Instance"))
    rl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(li, "Instances"), rl.inputs[0])
    g.l(out_sock(rl, "Geometry"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_fin_mast(mats):
    """Swept sensor fin — replaces boxy comm blades."""
    g = G("FI_FinMast")
    g.sock_in("Size", "NodeSocketFloat", 1.0, 0.1, 10.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    for i, (lx, hz, sw) in enumerate(((1.6, 1.9, -0.5), (1.1, 1.3, -0.35))):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", S, lx),
                              g.math("MULTIPLY", S, 0.06),
                              g.math("MULTIPLY", S, hz)),
                  (0.0, sw, 0.0),
                  (g.math("MULTIPLY", S, -0.3 * i - 0.2), 0,
                   g.math("MULTIPLY", S, 0.75 * hz / 1.9)), mats["dark"]),
            j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


# ------------------------------------------------------------ war ship -----

def build_war_ship(mats, hg, parts):
    g = G("FI_WarShip")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Detail", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Drive Type", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Pods", "NodeSocketInt", 2, 0, 6)
    g.sock_in("Panel Depth", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Greeble Density", "NodeSocketFloat", 0.18, 0.0, 5.0)
    g.sock_in("Turrets", "NodeSocketInt", 4, 0, 6)
    g.sock_in("VLS Pods", "NodeSocketInt", 2, 0, 2)
    g.sock_in("Greebles", "NodeSocketCollection")
    g.sock_in("Scale", "NodeSocketFloat", 1.0, 0.1, 10.0)
    g.sock_in("Silhouette", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Asymmetry", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Section", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Section Exponent", "NodeSocketFloat", 1.0, 0.5, 2.5)
    g.sock_in("Side Profile", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Step Strength", "NodeSocketFloat", 1.0, 0.0, 2.0)
    g.sock_in("Step Count", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Nose Frac", "NodeSocketFloat", 0.35, 0.05, 0.9)
    g.sock_in("Tail Frac", "NodeSocketFloat", 0.45, 0.05, 0.9)
    g.sock_in("Bend", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Blend", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Dorsal Taper", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Hump Position", "NodeSocketFloat", -1.0, -1.0, 0.9)
    g.sock_in("Hump Length", "NodeSocketFloat", -1.0, -1.0, 0.5)
    g.sock_in("Hump Height", "NodeSocketFloat", -1.0, -1.0, 0.6)
    g.sock_in("Detail Extrusions", "NodeSocketInt", 0, 0, 8)
    g.sock_in("Visor", "NodeSocketBool", True)
    g.sock_in("Visor Size", "NodeSocketFloat", 0.6, 0.2, 1.0)
    g.sock_in("Trench", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Armor Plates", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Panel Density", "NodeSocketInt", 2, 1, 4)
    g.sock_in("Sub Panels", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Light Lines", "NodeSocketInt", 5, 0, 8)
    g.sock_in("Retro Thrusters", "NodeSocketBool", True)
    g.sock_in("Manoeuvring Ports", "NodeSocketBool", True)
    g.sock_in("Length Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Beam Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Depth Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    seed = group_in(g, "Seed")

    def fsw(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, in_sock(n, "Switch"))
        for nm, v in (("False", off), ("True", on)):
            s = in_sock(n, nm, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, s)
            else:
                s.default_value = v
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

    def gsw(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(cond, in_sock(n, "Switch"))
        if off is not None:
            g.l(off, in_sock(n, "False", "GEOMETRY"))
        g.l(on, in_sock(n, "True", "GEOMETRY"))
        return out_sock(n, "Output", "GEOMETRY")

    is_dd = int_eq(group_in(g, "Class"), 1)
    SC = group_in(g, "Scale")
    L = g.math("MULTIPLY", g.math("MULTIPLY", fsw(is_dd, 48.0, 165.0), SC),
               group_in(g, "Length Mult"))
    B = g.math("MULTIPLY", g.math("MULTIPLY", fsw(is_dd, 11.0, 30.0), SC),
               group_in(g, "Beam Mult"))
    D = g.math("MULTIPLY", g.math("MULTIPLY", fsw(is_dd, 7.5, 20.0), SC),
               group_in(g, "Depth Mult"))
    det = group_in(g, "Detail")
    d1, d2 = int_gt(det, 0), int_gt(det, 1)
    seg = fsw(d1, 12.0, fsw(d2, 18.0, 26.0))
    stations = fsw(d1, 28.0, fsw(d2, 40.0, 56.0))

    hull = gcall(g, parts["hull"], wires={
        "Seed": seed, "Length": L, "Beam": B, "Depth": D,
        "Pods": group_in(g, "Pods"), "Stations": stations,
        "Silhouette": group_in(g, "Silhouette"),
        "Asymmetry": group_in(g, "Asymmetry"),
        "Section": group_in(g, "Section"),
        "Section Exponent": group_in(g, "Section Exponent"),
        "Side Profile": group_in(g, "Side Profile"),
        "Step Strength": group_in(g, "Step Strength"),
        "Step Count": group_in(g, "Step Count"),
        "Nose Frac": group_in(g, "Nose Frac"),
        "Tail Frac": group_in(g, "Tail Frac"),
        "Bend": group_in(g, "Bend"),
        "Blend": group_in(g, "Blend"),
        "Dorsal Taper": group_in(g, "Dorsal Taper"),
        "Hump Position": group_in(g, "Hump Position"),
        "Hump Length": group_in(g, "Hump Length"),
        "Hump Height": group_in(g, "Hump Height"),
        "Detail Extrusions": group_in(g, "Detail Extrusions")})
    core = out_sock(hull, "Geometry")

    # shallow sleek panel hierarchy
    # Limit Distance floors the division size: slivers thinner than the
    # final 2 mm weld would collapse and tear their recess walls open
    panels = gcall(g, hg["Mesh Face Divider"], wires={
        "Mesh": core, "Seed": seed,
        "Iterations": group_in(g, "Panel Density"),
        "Limit Distance": g.math("MULTIPLY", B, 0.03)},
        values={"U/V Ratio": 2.2,
                "Divide Probability": 0.7, "Even Probability": 0.4,
                "Distortion": 0.0})
    # micro-panel zone: a seeded band gets recursive sub-paneling
    band_a = g.rand_float(0.15, 0.55, None, g.math("ADD", seed, 81.0))
    pz = g.n("GeometryNodeInputPosition")
    pzs2 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pz, "Position"), pzs2.inputs[0])
    tpos_f = g.math("ADD", g.math("DIVIDE", pzs2.outputs[0], L), 0.5)
    in_bandp = g.math("MULTIPLY",
                      g.math("GREATER_THAN", tpos_f, band_a),
                      g.math("GREATER_THAN",
                             g.math("ADD", band_a, 0.18), tpos_f))
    # keep the micro-band OUT of the trench zone when the trench is on:
    # a 0.5 m trench shaft per 15 cm mosaic tile reads as a wall forest
    exN = g.n("GeometryNodeInputNormal")
    exNs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(exN, "Normal"), exNs.inputs[0])
    in_tzone = g.math("MULTIPLY",
                      g.math("MULTIPLY",
                             g.math("GREATER_THAN",
                                    g.math("ABSOLUTE", exNs.outputs[1]),
                                    0.7),
                             g.math("LESS_THAN",
                                    g.math("ABSOLUTE", pzs2.outputs[0]),
                                    g.math("MULTIPLY", L, 0.16))),
                      g.math("GREATER_THAN", group_in(g, "Trench"), 0.02))
    in_band2 = g.math("MULTIPLY", in_bandp,
                      g.math("SUBTRACT", 1.0, in_tzone))
    frs = gcall(g, hg["Mesh Face Divider"], wires={
        "Mesh": out_sock(panels, "Mesh"), "Selection": in_band2,
        "Seed": g.math("ADD", seed, 47.0),
        "Limit Distance": g.math("MULTIPLY", B, 0.015)},
        values={"Iterations": 3, "U/V Ratio": 1.0,
                "Divide Probability": 0.9, "Even Probability": 0.5,
                "Distortion": 0.0})
    sub_on = g.math("GREATER_THAN", group_in(g, "Sub Panels"), 0.02)
    subsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(sub_on, in_sock(subsw, "Switch"))
    g.l(out_sock(panels, "Mesh"), in_sock(subsw, "False", "GEOMETRY"))
    g.l(out_sock(frs, "Mesh"), in_sock(subsw, "True", "GEOMETRY"))
    # brand the band ONCE as a face attribute: recess walls inherit it, so
    # later deep cuts (trench) can structurally avoid everything the
    # mosaic owns -- normal-based re-tests disagree once Bend is in play
    brand = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                domain="FACE")
    g.l(out_sock(subsw, "Output", "GEOMETRY"), brand.inputs[0])
    in_sock(brand, "Name").default_value = "fi_band"
    bval = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(in_band2, bval.inputs[0])
    g.l(sub_on, bval.inputs[1])
    g.l(bval.outputs[0], in_sock(brand, "Value"))
    panels_out = out_sock(brand, "Geometry")
    area = g.n("GeometryNodeInputMeshFaceArea")
    big = g.math("GREATER_THAN", out_sock(area, "Area"),
                 g.math("MULTIPLY", g.math("MULTIPLY", L, B), 0.0016))

    # WATERTIGHT recess/boss primitive: ExtrudeMesh(individual) sinks or
    # raises the faces with straight walls (borders never move -> divider
    # T-junctions stay sealed), then a multiplicative ScaleElements frame
    # chamfers the top -- a pure shrink toward each face's own centre can
    # never self-cross, unlike an additive border inset on sliver faces.
    def recess(mesh, sel, depth, frame):
        ex = g.n("GeometryNodeExtrudeMesh", mode="FACES")
        g.l(mesh, ex.inputs[0])
        g.l(sel, in_sock(ex, "Selection"))
        if hasattr(depth, "is_linked"):
            g.l(depth, in_sock(ex, "Offset Scale"))
        else:
            in_sock(ex, "Offset Scale").default_value = depth
        in_sock(ex, "Individual").default_value = True
        sh = g.n("GeometryNodeScaleElements", domain="FACE")
        g.l(out_sock(ex, "Mesh"), sh.inputs[0])
        g.l(out_sock(ex, "Top"), in_sock(sh, "Selection"))
        if hasattr(frame, "is_linked"):
            g.l(frame, in_sock(sh, "Scale"))
        else:
            in_sock(sh, "Scale").default_value = frame
        return (out_sock(sh, "Geometry"), out_sock(ex, "Top"),
                out_sock(ex, "Side"))

    plated, inner, _ = recess(
        panels_out, big,
        g.math("MULTIPLY", g.math("MULTIPLY", D, -0.012),
               group_in(g, "Panel Depth")), 0.86)
    # SKIN guard: position/normal selections must not grab the WALLS of
    # earlier recesses (sideways extrusions of walls read as battle
    # damage). Skin = face normal points radially outward in the yz ring.
    skN = g.n("GeometryNodeInputNormal")
    skNs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(skN, "Normal"), skNs.inputs[0])
    skP = g.n("GeometryNodeInputPosition")
    skPs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(skP, "Position"), skPs.inputs[0])
    r_len = g.math("MAXIMUM",
                   g.math("SQRT",
                          g.math("ADD",
                                 g.math("MULTIPLY", skPs.outputs[1],
                                        skPs.outputs[1]),
                                 g.math("MULTIPLY", skPs.outputs[2],
                                        skPs.outputs[2]))), 0.001)
    dot_r = g.math("DIVIDE",
                   g.math("ADD",
                          g.math("MULTIPLY", skNs.outputs[1],
                                 skPs.outputs[1]),
                          g.math("MULTIPLY", skNs.outputs[2],
                                 skPs.outputs[2])), r_len)
    skin = g.math("GREATER_THAN", dot_r, 0.5)

    # Sub Panels: the divided micro-band becomes a machinery mosaic --
    # every band face sunk a seeded shallow amount (conforming: pure
    # recess on welded-back divider output)
    fidb = g.n("GeometryNodeInputIndex")
    band_sel0 = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(in_band2, band_sel0.inputs[0])
    g.l(skin, band_sel0.inputs[1])
    band_sel = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(band_sel0.outputs[0], band_sel.inputs[0])
    g.l(sub_on, band_sel.inputs[1])
    bd = g.math("MULTIPLY", g.math("MULTIPLY", D, -0.006),
                g.rand_float(0.3, 1.0, out_sock(fidb, "Index"),
                             g.math("ADD", seed, 53.0)))
    plated, _, _ = recess(plated, band_sel.outputs[0], bd, 0.90)
    # proud armor plates: seeded subset of big panels raised as chamfered
    # slabs with real side walls
    fid3 = g.n("GeometryNodeInputIndex")
    pl_r = g.rand_float(0.0, 1.0, out_sock(fid3, "Index"),
                        g.math("ADD", seed, 91.0))
    pl_sel = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(g.math("LESS_THAN", pl_r, group_in(g, "Armor Plates")),
        pl_sel.inputs[0])
    g.l(big, pl_sel.inputs[1])
    not_inner = g.n("FunctionNodeBooleanMath", operation="NOT")
    g.l(inner, not_inner.inputs[0])
    pl_sel2 = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pl_sel.outputs[0], pl_sel2.inputs[0])
    g.l(not_inner.outputs[0], pl_sel2.inputs[1])
    plated, _, _ = recess(plated, pl_sel2.outputs[0],
                       g.math("MULTIPLY", D, 0.012), 0.93)

    # ---- faction materials FIRST: hull everywhere, accent on a checker
    # subset of panel inners. Visor glass / trench cavity / drive glow are
    # assigned LATER and legitimately override (previously hull was set
    # after them with no selection and silently repainted the whole ship).
    is_unn = int_eq(group_in(g, "Faction"), 1)
    is_bel = int_eq(group_in(g, "Faction"), 2)

    def mat3(role):
        m1 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
        g.l(is_unn, in_sock(m1, "Switch"))
        in_sock(m1, "False", "MATERIAL").default_value = mats[f"{role}_MCR"]
        in_sock(m1, "True", "MATERIAL").default_value = mats[f"{role}_UNN"]
        m2 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
        g.l(is_bel, in_sock(m2, "Switch"))
        g.l(out_sock(m1, "Output", "MATERIAL"),
            in_sock(m2, "False", "MATERIAL"))
        in_sock(m2, "True", "MATERIAL").default_value = mats[f"{role}_BEL"]
        return out_sock(m2, "Output", "MATERIAL")

    smh = g.n("GeometryNodeSetMaterial")
    g.l(plated, smh.inputs[0])
    g.l(mat3("hull"), in_sock(smh, "Material"))
    chk = gcall(g, hg["Checker Selection"], values={
        "Selected": 1, "Deselected": 5, "Offset": 0, "Start Index": 0})
    accsel = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(out_sock(chk, "Selection"), accsel.inputs[0])
    g.l(inner, accsel.inputs[1])
    sma = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(smh, "Geometry"), sma.inputs[0])
    g.l(accsel.outputs[0], in_sock(sma, "Selection"))
    g.l(mat3("accent"), in_sock(sma, "Material"))
    plated = out_sock(sma, "Geometry")
    # canopy visor: angled glass cut on the upper-fore facets
    vN = g.n("GeometryNodeInputNormal")
    vNs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(vN, "Normal"), vNs.inputs[0])
    vP = g.n("GeometryNodeInputPosition")
    vPs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(vP, "Position"), vPs.inputs[0])
    vis_from = g.math("MULTIPLY", L,
                      g.math("SUBTRACT", 0.46,
                             g.math("MULTIPLY",
                                    group_in(g, "Visor Size"), 0.22)))
    vis_sel = g.math("MULTIPLY",
                     g.math("MULTIPLY",
                            g.math("MULTIPLY",
                                   g.math("GREATER_THAN",
                                          vNs.outputs[2], 0.35),
                                   g.math("GREATER_THAN",
                                          vNs.outputs[0], 0.20)),
                            g.math("GREATER_THAN", vPs.outputs[0],
                                   vis_from)),
                     skin)
    vins_geo, vins_top, _ = recess(plated, vis_sel,
                                g.math("MULTIPLY", D, -0.010), 0.80)
    vsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Visor"), in_sock(vsw, "Switch"))
    g.l(plated, in_sock(vsw, "False", "GEOMETRY"))
    g.l(vins_geo, in_sock(vsw, "True", "GEOMETRY"))
    plated = out_sock(vsw, "Output", "GEOMETRY")
    smv2 = g.n("GeometryNodeSetMaterial")
    g.l(plated, smv2.inputs[0])
    vgl = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(vins_top, vgl.inputs[0])
    g.l(group_in(g, "Visor"), vgl.inputs[1])
    g.l(vgl.outputs[0], in_sock(smv2, "Selection"))
    in_sock(smv2, "Material").default_value = mats["glass"]
    plated = out_sock(smv2, "Geometry")
    # flank trench with recursive machinery fill
    tN = g.n("GeometryNodeInputNormal")
    tNs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(tN, "Normal"), tNs.inputs[0])
    tP = g.n("GeometryNodeInputPosition")
    tPs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(tP, "Position"), tPs.inputs[0])
    t_band = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
    in_sock(t_band, "Name").default_value = "fi_band"
    t_noband = g.n("FunctionNodeBooleanMath", operation="NOT")
    g.l(out_sock(t_band, "Attribute"), t_noband.inputs[0])
    t_sel = g.math("MULTIPLY",
                   g.math("MULTIPLY",
                          g.math("MULTIPLY",
                                 g.math("GREATER_THAN",
                                        g.math("ABSOLUTE",
                                               tNs.outputs[1]), 0.8),
                                 g.math("LESS_THAN",
                                        g.math("ABSOLUTE", tPs.outputs[0]),
                                        g.math("MULTIPLY", L, 0.16))),
                          skin),
                   t_noband.outputs[0])
    tins_geo, tins_top, t_side = recess(plated, t_sel,
                                g.math("MULTIPLY",
                                       g.math("MULTIPLY", B, -0.05),
                                       group_in(g, "Trench")), 0.88)
    tdark = g.n("GeometryNodeSetMaterial")
    g.l(tins_geo, tdark.inputs[0])
    t_cav = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(tins_top, t_cav.inputs[0])
    g.l(t_side, t_cav.inputs[1])
    g.l(t_cav.outputs[0], in_sock(tdark, "Selection"))
    in_sock(tdark, "Material").default_value = mats["cavity"]
    trench_on = g.math("GREATER_THAN", group_in(g, "Trench"), 0.02)
    tsw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(trench_on, in_sock(tsw2, "Switch"))
    g.l(plated, in_sock(tsw2, "False", "GEOMETRY"))
    g.l(out_sock(tdark, "Geometry"), in_sock(tsw2, "True", "GEOMETRY"))
    plated = out_sock(tsw2, "Output", "GEOMETRY")
    trench_inner = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(tins_top, trench_inner.inputs[0])
    g.l(trench_on, trench_inner.inputs[1])

    dressed = plated

    _pending_strips = []

    # ---- chine light-lines (the FI Naval signature) -----------------------
    prof = parts["profile"]
    _ll_positions = (0.30, 0.42, 0.54, 0.66, 0.78, 0.24, 0.60, 0.72)
    for _lli, tpos in enumerate(_ll_positions):
        tpa = gcall(g, prof, wires={
            "Seed": seed, "Silhouette": group_in(g, "Silhouette")},
            values={"t": tpos - 0.05})
        tpb = gcall(g, prof, wires={
            "Seed": seed, "Silhouette": group_in(g, "Silhouette")},
            values={"t": tpos + 0.05})
        w_min = g.math("MINIMUM", out_sock(tpa, "W", "VALUE"),
                       out_sock(tpb, "W", "VALUE"))
        seg_len = g.math("MULTIPLY", L, 0.105)
        xw = g.math("MULTIPLY", L, tpos - 0.5)
        yw = g.math("MULTIPLY", w_min,
                    g.math("MULTIPLY", g.math("DIVIDE", B, 2.0), 0.96))
        for sgn in (1.0, -1.0):
            strip = _prim(g, "cube",
                          (seg_len, g.math("MULTIPLY", B, 0.012),
                           g.math("MULTIPLY", D, 0.03)), None, None, None)
            smn = g.n("GeometryNodeSetMaterial")
            g.l(strip, smn.inputs[0])
            g.l(mat3("line"), in_sock(smn, "Material"))
            mv = g.n("GeometryNodeTransform")
            g.l(out_sock(smn, "Geometry"), mv.inputs[0])
            tv = g.n("ShaderNodeCombineXYZ")
            g.l(xw, tv.inputs[0])
            g.l(g.math("MULTIPLY", yw, sgn), tv.inputs[1])
            g.l(tv.outputs[0], in_sock(mv, "Translation"))
            llg = g.n("FunctionNodeCompare", data_type="INT",
                      operation="GREATER_THAN")
            g.l(group_in(g, "Light Lines"), in_sock(llg, "A", "INT"))
            in_sock(llg, "B", "INT").default_value = _lli
            llsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
            g.l(out_sock(llg, "Result"), in_sock(llsw, "Switch"))
            g.l(out_sock(mv, "Geometry"), in_sock(llsw, "True", "GEOMETRY"))
            _pending_strips.append(out_sock(llsw, "Output", "GEOMETRY"))

    # ---- INTEGRATED drives: apertures cut into the hull's own faces -------
    # main drive: big recessed glow on aft-facing stern faces; retro
    # thrusters: inset into the FORWARD-facing step walls the plan-form
    # steps create; manoeuvring: small ports at the flank extremes.
    nD = g.n("GeometryNodeInputNormal")
    nDs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nD, "Normal"), nDs.inputs[0])
    pD = g.n("GeometryNodeInputPosition")
    pDs = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pD, "Position"), pDs.inputs[0])
    aft_main = g.math("MULTIPLY",
                      g.math("LESS_THAN", nDs.outputs[0], -0.85),
                      g.math("LESS_THAN", pDs.outputs[0],
                             g.math("MULTIPLY", L, -0.30)))
    retro = g.math("MULTIPLY",
                   g.math("MULTIPLY",
                          g.math("GREATER_THAN", nDs.outputs[0], 0.85),
                          g.math("LESS_THAN", pDs.outputs[0],
                                 g.math("MULTIPLY", L, 0.42))),
                   group_in(g, "Retro Thrusters"))
    fidm = g.n("GeometryNodeInputIndex")
    manv_pick = g.math("LESS_THAN",
                       g.rand_float(0.0, 1.0, out_sock(fidm, "Index"),
                                    g.math("ADD", seed, 29.0)), 0.30)
    manv = g.math("MULTIPLY",
                  g.math("MULTIPLY",
                         g.math("MULTIPLY",
                                g.math("MULTIPLY",
                                       g.math("GREATER_THAN",
                                              g.math("ABSOLUTE",
                                                     nDs.outputs[1]), 0.85),
                                       g.math("GREATER_THAN",
                                              g.math("ABSOLUTE",
                                                     pDs.outputs[0]),
                                              g.math("MULTIPLY", L, 0.30))),
                                skin),
                         manv_pick),
                  group_in(g, "Manoeuvring Ports"))
    # Drive Type varies the main-aperture pattern: 0 wide / 1 framed /
    # 2 multi-cell (stern faces pre-divided)
    is_t2 = int_eq(group_in(g, "Drive Type"), 2)
    # multi-cell stern: TRIANGULATE the aft faces (adds only diagonals
    # between existing verts -- conforming on any n-gon, unlike the
    # divider, which leaks daylight on the non-planar tail cap) and let
    # the aperture recess cut each triangle into its own nozzle cell
    dd = g.n("GeometryNodeTriangulate")
    g.l(dressed, dd.inputs[0])
    g.l(aft_main, in_sock(dd, "Selection"))
    pre_sw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(is_t2, in_sock(pre_sw, "Switch"))
    g.l(dressed, in_sock(pre_sw, "False", "GEOMETRY"))
    g.l(out_sock(dd, "Mesh"), in_sock(pre_sw, "True", "GEOMETRY"))
    stage0 = out_sock(pre_sw, "Output", "GEOMETRY")
    frame_main = fsw(int_eq(group_in(g, "Drive Type"), 1), 0.82, 0.58)
    dm_geo, dm_top, dm_side = recess(stage0, aft_main,
                            g.math("MULTIPLY", D, -0.10), frame_main)
    dr_geo, dr_top, dr_side = recess(dm_geo, retro,
                            g.math("MULTIPLY", D, -0.04), 0.58)
    dv_geo, dv_top, dv_side = recess(dr_geo, manv,
                            g.math("MULTIPLY", D, -0.02), 0.42)
    glow_sel = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(dm_top, glow_sel.inputs[0])
    g.l(dr_top, glow_sel.inputs[1])
    glow_sel2 = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(glow_sel.outputs[0], glow_sel2.inputs[0])
    g.l(dv_top, glow_sel2.inputs[1])
    # aperture walls: dark nozzle throats, never hull/accent colour
    dk_sel = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(dm_side, dk_sel.inputs[0])
    g.l(dr_side, dk_sel.inputs[1])
    dk_sel2 = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(dk_sel.outputs[0], dk_sel2.inputs[0])
    g.l(dv_side, dk_sel2.inputs[1])
    smw = g.n("GeometryNodeSetMaterial")
    g.l(dv_geo, smw.inputs[0])
    g.l(dk_sel2.outputs[0], in_sock(smw, "Selection"))
    in_sock(smw, "Material").default_value = mats["dark"]
    smd = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(smw, "Geometry"), smd.inputs[0])
    g.l(glow_sel2.outputs[0], in_sock(smd, "Selection"))
    g.l(mat3("drive"), in_sock(smd, "Material"))
    # WELD: the FI_FaceDivider detaches divided faces into islands
    # whose borders merely COINCIDE with the parent mesh (z-fighting slits,
    # glow bleeding through backfaces). Fuse everything coincident back
    # together; 2 mm is far below the smallest recess wall (~40 mm) so no
    # feature collapses, and conforming T-verts are simply left in place.
    weld = g.n("GeometryNodeMergeByDistance")
    g.l(out_sock(smd, "Geometry"), weld.inputs[0])
    in_sock(weld, "Distance").default_value = 0.002
    dressed = out_sock(weld, "Geometry")
    # rebuild the output join on the aperture-cut hull
    out = g.n("GeometryNodeJoinGeometry")
    g.l(dressed, out.inputs[0])
    for pending in _pending_strips:
        g.l(pending, out.inputs[0])

    # ---- flush hardpoints via raycast --------------------------------------    # ---- flush hardpoints via raycast --------------------------------------
    def deck_place(x_f, y_f, part_geo, gate=None, down=True):
        srcv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", L, x_f), srcv.inputs[0])
        g.l(g.math("MULTIPLY", B, y_f), srcv.inputs[1])
        g.l(g.math("MULTIPLY", D, 2.0 if down else -2.0), srcv.inputs[2])
        rc = g.n("GeometryNodeRaycast")
        g.l(dressed, in_sock(rc, "Target Geometry"))
        g.l(srcv.outputs[0], in_sock(rc, "Source Position"))
        in_sock(rc, "Ray Direction").default_value = \
            (0, 0, -1.0 if down else 1.0)
        g.l(g.math("MULTIPLY", D, 4.0), in_sock(rc, "Ray Length"))
        pt = g.n("GeometryNodePoints")
        in_sock(pt, "Count").default_value = 1
        sinkv = g.n("ShaderNodeVectorMath", operation="SCALE")
        g.l(out_sock(rc, "Hit Normal"), sinkv.inputs[0])
        g.l(g.math("MULTIPLY", B, -0.02), sinkv.inputs[3])
        sunk = g.n("ShaderNodeVectorMath", operation="ADD")
        g.l(out_sock(rc, "Hit Position"), sunk.inputs[0])
        g.l(sinkv.outputs[0], sunk.inputs[1])
        g.l(out_sock(sunk, "Vector", "VECTOR"), in_sock(pt, "Position"))
        alh = g.n("FunctionNodeAlignEulerToVector", axis="Z")
        g.l(out_sock(rc, "Hit Normal"), in_sock(alh, "Vector"))
        ih = g.n("GeometryNodeInstanceOnPoints")
        g.l(out_sock(pt, "Points"), ih.inputs[0])
        g.l(part_geo, in_sock(ih, "Instance"))
        g.l(out_sock(alh, "Rotation"), in_sock(ih, "Rotation"))
        rlh = g.n("GeometryNodeRealizeInstances")
        g.l(out_sock(ih, "Instances"), rlh.inputs[0])
        geo = out_sock(rlh, "Geometry")
        # only accept DECK hits (near-vertical normals) — no more tilted
        # hardware on step walls (her "fins sticking out" catch)
        nz_ok = g.n("ShaderNodeSeparateXYZ")
        g.l(out_sock(rc, "Hit Normal"), nz_ok.inputs[0])
        flatn = g.math("GREATER_THAN",
                       g.math("MULTIPLY", nz_ok.outputs[2],
                              1.0 if down else -1.0), 0.6)
        okhit = g.n("FunctionNodeBooleanMath", operation="AND")
        g.l(out_sock(rc, "Is Hit"), okhit.inputs[0])
        g.l(flatn, okhit.inputs[1])
        hsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(okhit.outputs[0], in_sock(hsw, "Switch"))
        g.l(geo, in_sock(hsw, "True", "GEOMETRY"))
        geo = out_sock(hsw, "Output", "GEOMETRY")
        if gate is not None:
            geo = gsw(gate, None, geo)
        g.l(geo, out.inputs[0])

    turret = gcall(g, parts["pdc"], wires={
        "Size": g.math("MULTIPLY", B, 0.10), "Segments": seg})
    for i, spot in enumerate(((0.30, 0.06), (0.06, -0.16), (-0.16, 0.14),
                              (0.20, -0.08, False), (-0.02, 0.12, False),
                              (-0.30, -0.05))):
        down = spot[2] if len(spot) > 2 else True
        deck_place(spot[0], spot[1], out_sock(turret, "Geometry"),
                   gate=int_gt(group_in(g, "Turrets"), i), down=down)
    vls = gcall(g, parts["vls"], wires={
        "Width": g.math("MULTIPLY", B, 0.22)},
        values={"Tubes X": 4, "Tubes Y": 3})
    for i, (xf, yf) in enumerate(((0.02, 0.22), (-0.20, -0.20))):
        deck_place(xf, yf, out_sock(vls, "Geometry"),
                   gate=int_gt(group_in(g, "VLS Pods"), i))
    # light deck greebles
    dpof = g.n("GeometryNodeDistributePointsOnFaces",
               distribute_method="POISSON")
    g.l(dressed, dpof.inputs[0])
    nrm3 = g.n("GeometryNodeInputNormal")
    ns3 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm3, "Normal"), ns3.inputs[0])
    gtop = g.math("GREATER_THAN", ns3.outputs[2], 0.62)
    gsel2 = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(gtop, gsel2.inputs[0])
    g.l(trench_inner.outputs[0], gsel2.inputs[1])
    g.l(gsel2.outputs[0], in_sock(dpof, "Selection"))
    g.l(group_in(g, "Greeble Density"), in_sock(dpof, "Density Max"))
    g.l(g.math("DIVIDE", 0.55,
               g.math("SQRT", g.math("MAXIMUM",
                                     group_in(g, "Greeble Density"),
                                     0.01))), in_sock(dpof, "Distance Min"))
    g.l(seed, in_sock(dpof, "Seed"))
    cinf = g.n("GeometryNodeCollectionInfo", transform_space="ORIGINAL")
    g.l(group_in(g, "Greebles"), in_sock(cinf, "Collection"))
    in_sock(cinf, "Separate Children").default_value = True
    in_sock(cinf, "Reset Children").default_value = True
    al = g.n("FunctionNodeAlignEulerToVector", axis="Z")
    g.l(out_sock(dpof, "Rotation"), in_sock(al, "Rotation"))
    g.l(out_sock(dpof, "Normal"), in_sock(al, "Vector"))
    gid = g.n("GeometryNodeInputID")
    pick = g.math("FLOORED_MODULO",
                  g.rand_float(0.0, 4096.0, out_sock(gid, "ID"),
                               g.math("ADD", seed, 3.0)), 27.0)
    gi_ = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(dpof, "Points"), gi_.inputs[0])
    g.l(out_sock(cinf, "Instances"), in_sock(gi_, "Instance"))
    in_sock(gi_, "Pick Instance").default_value = True
    g.l(pick, in_sock(gi_, "Instance Index"))
    g.l(out_sock(al, "Rotation"), in_sock(gi_, "Rotation"))
    scl = g.n("GeometryNodeScaleInstances")
    g.l(out_sock(gi_, "Instances"), scl.inputs[0])
    in_sock(scl, "Scale").default_value = (0.6, 0.6, 0.6)
    rg2 = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(scl, "Instances"), rg2.inputs[0])
    smg = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(rg2, "Geometry"), smg.inputs[0])
    in_sock(smg, "Material").default_value = mats["metal"]
    g.l(out_sock(smg, "Geometry"), out.inputs[0])

    final = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(out, "Geometry"), final.inputs[0])
    return g.finish(out_sock(final, "Geometry"))


# ---------------------------------------------------------------- main -----

def main():
    outp = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    hg = fi_deps(DEP_WANT)
    mats = build_war_materials()
    parts = {
        "profile": build_war_profile(),
        "pdc": build_pdc_turret(mats),
        "vls": build_vls_pod(mats),
        "fin": build_fin_mast(mats),
        "drive": build_linear_drive(mats),
    }
    parts["hull"] = build_war_hull(hg, parts["profile"])
    parts["ship"] = build_war_ship(mats, hg, parts)
    contract = {}
    for ng in parts.values():
        contract[ng.name] = [
            {"name": it.name, "in_out": it.in_out,
             "type": getattr(it, "socket_type", "?"),
             "identifier": it.identifier}
            for it in ng.interface.items_tree
            if it.item_type == "SOCKET"]
    with open(os.path.join(os.path.dirname(outp), "war_contract.json"),
              "w") as f:
        json.dump(contract, f, indent=1, sort_keys=True)
    for ng in parts.values():
        ng.asset_mark()
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    print(f"build_warkit: OK -> {outp} ({len(parts)} groups + "
          f"{len(hg)} native deps)")


main()
