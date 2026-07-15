#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# build_fleetkit.py -- FI_FleetKit.blend: the FI FLEET generator — bright
# slab-fleet ships in the Homeworld register (her 5 reference images).
#
#   blender -b --python build_fleetkit.py -- [--out FI_FleetKit.blend]
#
# HOUSE LANGUAGE:
#   - broad flat SLAB hulls (beam >> depth), cube-grid loft — NO mirror
#     pass, symmetric by construction; every region is a rectangle
#   - layered plateau decks with single chamfer rims (boss() region mode),
#     beveled chine flanks, chisel bow with deck rake, wider stern block
#   - unit-space fi_u captured FIRST; all region selections test it
#     (structural fix for the normal-retest bug class)
#   - integrated drive: rectangular slot nozzles recessed into the aft
#     cap grid + corner vernier ports; glow floors, dark throats
#   - BRIGHT flat palettes: NAV teal/orange, OXR oxide, NYX charcoal/red

import bpy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fi_gn_lib import (G, boss, gcall, group_in, in_sock, out_sock,  # noqa
                       mat, _prim, _shader_wear, _base_flat,
                       _base_patchwork, fi_deps)

HERE = os.path.dirname(os.path.abspath(__file__))

DEP_WANT = ["Mesh Face Divider"]


def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = os.path.join(HERE, "FI_FleetKit.blend")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    return out


# ---------------------------------------------------------- materials ------
# W1: flat palette stand-ins (patchwork shader system lands in W2 on the
# same material names).

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
}


def build_fleet_materials():
    m = {}
    m["dark"] = mat("FI_Fleet_Dark", (0.08, 0.08, 0.09), 0.7, 0.4)
    m["cavity"] = mat("FI_Fleet_Cavity", (0.03, 0.03, 0.04), 0.9, 0.1)
    m["metal"] = mat("FI_Fleet_Metal", (0.32, 0.33, 0.35), 0.5, 0.8)
    m["slat"] = mat("FI_Fleet_Slat", (0.78, 0.75, 0.66), 0.6, 0.2)
    m["radome"] = mat("FI_Fleet_Radome", (0.85, 0.85, 0.83), 0.5, 0.1)
    m["decalw"] = mat("FI_Fleet_DecalW", (0.92, 0.92, 0.90), 0.5, 0.0)
    m["tiplight"] = mat("FI_Fleet_TipLight", (0.10, 0.09, 0.06), 0.4, 0.0,
                        emissive=(1.0, 0.85, 0.55), estrength=5.0)
    m["glow_generic"] = mat("FI_Fleet_GlowG", (0.05, 0.05, 0.06), 0.5, 0.0,
                            emissive=(0.75, 0.85, 1.0), estrength=5.0)
    for key, f in FACS.items():
        hull = mat(f"FI_Fleet_{key}_Hull", f["base"], 0.5, 0.2)
        _shader_wear(hull, lambda nt, k=key: _base_patchwork(nt, FACS[k]),
                     wear=f["wear"], grime=f["grime"], rough=0.5,
                     metal=0.2, bump_str=0.02, seam=0.12,
                     emit=(f["light"], 5.0))
        m[f"hull_{key}"] = hull
        acc = mat(f"FI_Fleet_{key}_Accent", f["accent"], 0.5, 0.1)
        _shader_wear(acc, lambda nt, k=key: _base_flat(
                         nt, FACS[k]["accent"]),
                     wear=f["wear"] * 0.8, grime=f["grime"] * 0.6,
                     wear_col=(0.35, 0.34, 0.33), rough=0.5, metal=0.1,
                     bump_str=0.02)
        m[f"accent_{key}"] = acc
        m[f"deck_{key}"] = mat(f"FI_Fleet_{key}_Deck", f["deck"], 0.85, 0.05)
        m[f"decal_{key}"] = mat(f"FI_Fleet_{key}_Decal", f["decal"],
                                0.5, 0.0)
        m[f"light_{key}"] = mat(f"FI_Fleet_{key}_Light",
                                tuple(c * 0.1 for c in f["light"]), 0.4, 0.0,
                                emissive=f["light"], estrength=4.0)
        m[f"drive_{key}"] = mat(f"FI_Fleet_{key}_Drive",
                                (0.05, 0.05, 0.06), 0.5, 0.0,
                                emissive=f["glow"], estrength=7.0)
    return m


# ----------------------------------------------------- fleet components ----

def build_vent_grate(mats):
    """Recessed slatted vent tray (the reference dark gratings): chamfered
    metal tray + dark floor + cream slat array. All closed prims."""
    g = G("FI_VentGrate")
    g.sock_in("Length", "NodeSocketFloat", 6.0, 0.5, 200.0)
    g.sock_in("Width", "NodeSocketFloat", 3.0, 0.3, 100.0)
    g.sock_in("Slats", "NodeSocketInt", 10, 4, 20)
    g.sock_out("Geometry", "NodeSocketGeometry")
    L = group_in(g, "Length")
    W = group_in(g, "Width")
    h = g.math("MULTIPLY", W, 0.12)
    j = g.n("GeometryNodeJoinGeometry")
    tray = _prim(g, "cube", (L, W, h), None,
                 (0.0, 0.0, g.math("MULTIPLY", h, 0.5)), mats["metal"])
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    topf = g.math("GREATER_THAN", ns.outputs[2], 0.5)
    tray2, ttop, _ = boss(g, tray, topf,
                          g.math("MULTIPLY", h, -0.55), 0.88)
    smt = g.n("GeometryNodeSetMaterial")
    g.l(tray2, smt.inputs[0])
    g.l(ttop, in_sock(smt, "Selection"))
    in_sock(smt, "Material").default_value = mats["cavity"]
    g.l(out_sock(smt, "Geometry"), j.inputs[0])
    # slats across the width, arrayed along the length
    line = g.n("GeometryNodeMeshLine", mode="END_POINTS")
    g.l(group_in(g, "Slats"), in_sock(line, "Count"))
    sv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", L, -0.40), sv.inputs[0])
    g.l(g.math("MULTIPLY", h, 0.62), sv.inputs[2])
    g.l(sv.outputs[0], in_sock(line, "Start Location"))
    ev = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", L, 0.40), ev.inputs[0])
    g.l(g.math("MULTIPLY", h, 0.62), ev.inputs[2])
    g.l(ev.outputs[0], in_sock(line, "Offset"))
    slat = _prim(g, "cube", (g.math("MULTIPLY", L, 0.032),
                             g.math("MULTIPLY", W, 0.74),
                             g.math("MULTIPLY", h, 0.34)), None, None,
                 mats["slat"])
    iop = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(line, "Mesh"), iop.inputs[0])
    g.l(slat, in_sock(iop, "Instance"))
    rl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(iop, "Instances"), rl.inputs[0])
    g.l(out_sock(rl, "Geometry"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_radome(mats):
    """Pedestal sensor: Variant 0 = squashed dome, 1 = pitched dish."""
    g = G("FI_Radome")
    g.sock_in("Size", "NodeSocketFloat", 3.0, 0.2, 60.0)
    g.sock_in("Variant", "NodeSocketInt", 0, 0, 1)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.30),
                         g.math("MULTIPLY", S, 0.45)), None,
              (0.0, 0.0, g.math("MULTIPLY", S, 0.225)), mats["metal"],
              verts=10), j.inputs[0])
    dome = _prim(g, "sphere", (g.math("MULTIPLY", S, 0.40),), None, None,
                 mats["radome"])
    dsq = g.n("GeometryNodeTransform")
    g.l(dome, dsq.inputs[0])
    in_sock(dsq, "Scale").default_value = (1.0, 1.0, 0.62)
    dtr = g.n("GeometryNodeTransform")
    g.l(out_sock(dsq, "Geometry"), dtr.inputs[0])
    tv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", S, 0.52), tv.inputs[2])
    g.l(tv.outputs[0], in_sock(dtr, "Translation"))
    dish = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.10),
                          g.math("MULTIPLY", S, 0.24),
                          g.math("MULTIPLY", S, 0.26)), None,
              (0.0, 0.0, g.math("MULTIPLY", S, 0.56)), mats["dark"]),
        dish.inputs[0])
    dcone = _prim(g, "cone", (g.math("MULTIPLY", S, 0.44),
                              g.math("MULTIPLY", S, 0.06),
                              g.math("MULTIPLY", S, 0.16)),
                  (0.0, 0.9, 0.0), None, mats["radome"], verts=12)
    dmov = g.n("GeometryNodeTransform")
    g.l(dcone, dmov.inputs[0])
    tv2 = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", S, 0.10), tv2.inputs[0])
    g.l(g.math("MULTIPLY", S, 0.72), tv2.inputs[2])
    g.l(tv2.outputs[0], in_sock(dmov, "Translation"))
    g.l(out_sock(dmov, "Geometry"), dish.inputs[0])
    vsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    iv = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
    g.l(group_in(g, "Variant"), in_sock(iv, "A", "INT"))
    in_sock(iv, "B", "INT").default_value = 1
    g.l(out_sock(iv, "Result"), in_sock(vsw, "Switch"))
    g.l(out_sock(dtr, "Geometry"), in_sock(vsw, "False", "GEOMETRY"))
    g.l(out_sock(dish, "Geometry"), in_sock(vsw, "True", "GEOMETRY"))
    g.l(out_sock(vsw, "Output", "GEOMETRY"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_antenna_mast(mats):
    """Paired thin masts + crossbar + emissive tips (the reference
    vertical antennas, always in pairs)."""
    g = G("FI_AntennaMast")
    g.sock_in("Size", "NodeSocketFloat", 4.0, 0.3, 80.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.34),
                          g.math("MULTIPLY", S, 0.66),
                          g.math("MULTIPLY", S, 0.06)), None,
              (0.0, 0.0, g.math("MULTIPLY", S, 0.03)), mats["metal"]),
        j.inputs[0])
    for sgn in (1.0, -1.0):
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.028), S), None,
                  (0.0, g.math("MULTIPLY", S, 0.22 * sgn),
                   g.math("MULTIPLY", S, 0.5)), mats["dark"], verts=6),
            j.inputs[0])
        g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.06),
                              g.math("MULTIPLY", S, 0.06),
                              g.math("MULTIPLY", S, 0.06)), None,
                  (0.0, g.math("MULTIPLY", S, 0.22 * sgn),
                   g.math("MULTIPLY", S, 1.02)), mats["tiplight"]),
            j.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.045),
                          g.math("MULTIPLY", S, 0.50),
                          g.math("MULTIPLY", S, 0.045)), None,
              (0.0, 0.0, g.math("MULTIPLY", S, 0.74)), mats["dark"]),
        j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_sponson(mats):
    """Chamfered flank pod with outboard plate + aft mini-thruster."""
    g = G("FI_Sponson")
    g.sock_in("Size", "NodeSocketFloat", 12.0, 1.0, 200.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    body = _prim(g, "cube", (S, g.math("MULTIPLY", S, 0.36),
                             g.math("MULTIPLY", S, 0.28)), None, None,
                 mats["metal"])
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    # plate on BOTH flanks so one group serves port and starboard
    outb = g.math("GREATER_THAN",
                  g.math("ABSOLUTE", ns.outputs[1]), 0.5)
    b1, _, _ = boss(g, body, outb, g.math("MULTIPLY", S, 0.045), 0.80)
    aft = g.math("LESS_THAN", ns.outputs[0], -0.5)
    b2, a_top, a_side = boss(g, b1, aft,
                             g.math("MULTIPLY", S, -0.05), 0.68)
    smd = g.n("GeometryNodeSetMaterial")
    g.l(b2, smd.inputs[0])
    g.l(a_side, in_sock(smd, "Selection"))
    in_sock(smd, "Material").default_value = mats["dark"]
    smg = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(smd, "Geometry"), smg.inputs[0])
    g.l(a_top, in_sock(smg, "Selection"))
    in_sock(smg, "Material").default_value = mats["glow_generic"]
    return g.finish(out_sock(smg, "Geometry"))


def build_sensor_boom(mats):
    """Bow sensor spike + emissive tip (placed in mirrored pairs)."""
    g = G("FI_SensorBoom")
    g.sock_in("Size", "NodeSocketFloat", 7.0, 0.5, 150.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.14),
                          g.math("MULTIPLY", S, 0.14),
                          g.math("MULTIPLY", S, 0.14)), None, None,
              mats["dark"]), j.inputs[0])
    g.l(_prim(g, "cone", (g.math("MULTIPLY", S, 0.018),
                          g.math("MULTIPLY", S, 0.06), S),
              (0.0, 1.5707963, 0.0), None, mats["metal"], verts=6),
        j.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.05),
                          g.math("MULTIPLY", S, 0.05),
                          g.math("MULTIPLY", S, 0.05)), None,
              (S, 0.0, 0.0), mats["tiplight"]), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_chevron(mats):
    """Wing-chevron insignia as thin raised geometry (no textures)."""
    g = G("FI_Chevron")
    g.sock_in("Size", "NodeSocketFloat", 8.0, 0.5, 150.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    th = g.math("MULTIPLY", S, 0.02)
    j = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.34),
                          g.math("MULTIPLY", S, 0.10), th),
              None, (g.math("MULTIPLY", S, 0.12), 0.0, 0.0),
              mats["decalw"]), j.inputs[0])
    for sgn in (1.0, -1.0):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", S, 0.42),
                              g.math("MULTIPLY", S, 0.09), th),
                  (0.0, 0.0, 0.55 * sgn),
                  (g.math("MULTIPLY", S, -0.10),
                   g.math("MULTIPLY", S, 0.16 * sgn), 0.0),
                  mats["decalw"]), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_hull_number(mats):
    """Seeded 0-99 hull number as two 7-segment digits of thin boxes
    (String-to-Curves fill is an open mesh — daylight risk; boxes are
    closed)."""
    g = G("FI_HullNumber")
    g.sock_in("Value", "NodeSocketInt", 42, 0, 99)
    g.sock_in("Size", "NodeSocketFloat", 6.0, 0.5, 120.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    val = group_in(g, "Value")
    tens = g.math("FLOOR", g.math("DIVIDE", val, 10.0))
    ones = g.math("FLOORED_MODULO", val, 10.0)
    th = g.math("MULTIPLY", S, 0.06)
    segw = g.math("MULTIPLY", S, 0.30)
    segt = g.math("MULTIPLY", S, 0.075)
    j = g.n("GeometryNodeJoinGeometry")

    def d_eq(dsock, k):
        n = g.n("FunctionNodeCompare", data_type="FLOAT",
                operation="EQUAL")
        g.l(dsock, in_sock(n, "A", "VALUE"))
        in_sock(n, "B", "VALUE").default_value = float(k)
        in_sock(n, "Epsilon").default_value = 0.1
        return out_sock(n, "Result")

    def or_set(dsock, ks):
        cur = None
        for k in ks:
            e = d_eq(dsock, k)
            if cur is None:
                cur = e
            else:
                n = g.n("FunctionNodeBooleanMath", operation="OR")
                g.l(cur, n.inputs[0])
                g.l(e, n.inputs[1])
                cur = n.outputs[0]
        return cur

    def not_in(dsock, ks):
        n = g.n("FunctionNodeBooleanMath", operation="NOT")
        g.l(or_set(dsock, ks), n.inputs[0])
        return n.outputs[0]

    # 7-seg layout in the XY plane (reads from +Z)
    segs = (
        ("a", (0.0, 0.36), False),
        ("b", (0.18, 0.18), True),
        ("c", (0.18, -0.18), True),
        ("d", (0.0, -0.36), False),
        ("e", (-0.18, -0.18), True),
        ("f", (-0.18, 0.18), True),
        ("g", (0.0, 0.0), False),
    )
    gates = {
        "a": lambda d: not_in(d, (1, 4)),
        "b": lambda d: not_in(d, (5, 6)),
        "c": lambda d: not_in(d, (2,)),
        "d": lambda d: not_in(d, (1, 4, 7)),
        "e": lambda d: or_set(d, (0, 2, 6, 8)),
        "f": lambda d: not_in(d, (1, 2, 3, 7)),
        "g": lambda d: not_in(d, (0, 1, 7)),
    }
    for dsock, xoff in ((tens, -0.30), (ones, 0.30)):
        for name, (sx, sy), vertical in segs:
            dims = ((segt, segw, th) if vertical else (segw, segt, th))
            cube = _prim(g, "cube", dims, None,
                         (g.math("MULTIPLY", S, sx + xoff),
                          g.math("MULTIPLY", S, sy),
                          g.math("MULTIPLY", S, 0.06)),
                         mats["decalw"])
            sw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
            g.l(gates[name](dsock), in_sock(sw, "Switch"))
            g.l(cube, in_sock(sw, "True", "GEOMETRY"))
            g.l(out_sock(sw, "Output", "GEOMETRY"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))



def _msock(g, node_or_geo, mat_sock):
    """SetMaterial wired from a group material input socket."""
    sm = g.n("GeometryNodeSetMaterial")
    g.l(node_or_geo, sm.inputs[0])
    g.l(mat_sock, in_sock(sm, "Material"))
    return out_sock(sm, "Geometry")


def build_fin(mats):
    """Raked dorsal/ventral fin: sheared slab + accent leading edge."""
    g = G("FI_FleetFin")
    g.sock_in("Size", "NodeSocketFloat", 8.0, 0.5, 150.0)
    g.sock_in("Hull Mat", "NodeSocketMaterial")
    g.sock_in("Accent Mat", "NodeSocketMaterial")
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    j = g.n("GeometryNodeJoinGeometry")
    slab = _prim(g, "cube",
                 (g.math("MULTIPLY", S, 0.72),
                  g.math("MULTIPLY", S, 0.07), S),
                 None, (0.0, 0.0, g.math("MULTIPLY", S, 0.42)), None)
    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    shear = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", sep.outputs[2], 0.55), shear.inputs[0])
    # taper the chord with height too (trapezoid fin)
    sp = g.n("GeometryNodeSetPosition")
    g.l(slab, sp.inputs[0])
    g.l(shear.outputs[0], in_sock(sp, "Offset"))
    g.l(_msock(g, out_sock(sp, "Geometry"), group_in(g, "Hull Mat")),
        j.inputs[0])
    edge = _prim(g, "cube",
                 (g.math("MULTIPLY", S, 0.09),
                  g.math("MULTIPLY", S, 0.09),
                  g.math("MULTIPLY", S, 0.92)),
                 None, None, None)
    pos2 = g.n("GeometryNodeInputPosition")
    sep2 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos2, "Position"), sep2.inputs[0])
    sh2 = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", sep2.outputs[2], 0.55), sh2.inputs[0])
    sp2 = g.n("GeometryNodeSetPosition")
    g.l(edge, sp2.inputs[0])
    g.l(sh2.outputs[0], in_sock(sp2, "Offset"))
    mv = g.n("GeometryNodeTransform")
    g.l(out_sock(sp2, "Geometry"), mv.inputs[0])
    tv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", S, 0.38), tv.inputs[0])
    g.l(g.math("MULTIPLY", S, 0.44), tv.inputs[2])
    g.l(tv.outputs[0], in_sock(mv, "Translation"))
    g.l(_msock(g, out_sock(mv, "Geometry"), group_in(g, "Accent Mat")),
        j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_prong(mats):
    """Tapered prow tine (fork/trident/lance) + glow tip. Root at
    x = -Length/2, tip at +Length/2."""
    g = G("FI_FleetProng")
    g.sock_in("Length", "NodeSocketFloat", 20.0, 1.0, 400.0)
    g.sock_in("Hull Mat", "NodeSocketMaterial")
    g.sock_in("Glow Mat", "NodeSocketMaterial")
    g.sock_out("Geometry", "NodeSocketGeometry")
    Lp = group_in(g, "Length")
    j = g.n("GeometryNodeJoinGeometry")
    tine = _prim(g, "cube",
                 (Lp, g.math("MULTIPLY", Lp, 0.16),
                  g.math("MULTIPLY", Lp, 0.13)), None, None, None)
    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    tfrac = g.math("ADD", g.math("DIVIDE", sep.outputs[0], Lp), 0.5)
    shrink = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", tfrac, 0.62))
    sc = g.n("ShaderNodeCombineXYZ")
    sc.inputs[0].default_value = 0.0
    g.l(g.math("MULTIPLY", sep.outputs[1],
               g.math("SUBTRACT", shrink, 1.0)), sc.inputs[1])
    g.l(g.math("MULTIPLY", sep.outputs[2],
               g.math("SUBTRACT", shrink, 1.0)), sc.inputs[2])
    sp = g.n("GeometryNodeSetPosition")
    g.l(tine, sp.inputs[0])
    g.l(sc.outputs[0], in_sock(sp, "Offset"))
    g.l(_msock(g, out_sock(sp, "Geometry"), group_in(g, "Hull Mat")),
        j.inputs[0])
    tip = _prim(g, "cube",
                (g.math("MULTIPLY", Lp, 0.06),
                 g.math("MULTIPLY", Lp, 0.075),
                 g.math("MULTIPLY", Lp, 0.062)),
                None, (g.math("MULTIPLY", Lp, 0.50), 0.0, 0.0), None)
    g.l(_msock(g, tip, group_in(g, "Glow Mat")), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_nacelle(mats):
    """External engine pod in THE HULL'S geometric language (her call):
    flat-shaded chamfered prism (the chine-section octagon, flats up),
    SetPosition boat-tail nose, and a rectangular recessed nozzle like
    the drive slots — no smooth cylinders, no discs."""
    g = G("FI_FleetNacelle")
    g.sock_in("Size", "NodeSocketFloat", 12.0, 1.0, 200.0)
    g.sock_in("Hull Mat", "NodeSocketMaterial")
    g.sock_in("Glow Mat", "NodeSocketMaterial")
    g.sock_in("Dark Mat", "NodeSocketMaterial")
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    body = _prim(g, "cyl", (g.math("MULTIPLY", S, 0.18), S),
                 (0.0, 1.5707963, 0.3926990), None, None, verts=8,
                 smooth=False)
    # boat-tail nose: taper the forward third in the pod's own frame
    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    nf = g.n("ShaderNodeMapRange")
    in_sock(nf, "From Min", "VALUE").default_value = 0.0
    g.l(g.math("MULTIPLY", S, 0.18), in_sock(nf, "From Min", "VALUE"))
    g.l(g.math("MULTIPLY", S, 0.50), in_sock(nf, "From Max", "VALUE"))
    in_sock(nf, "To Min", "VALUE").default_value = 0.0
    in_sock(nf, "To Max", "VALUE").default_value = 0.55
    g.l(sep.outputs[0], in_sock(nf, "Value"))
    shrink = out_sock(nf, "Result", "VALUE")
    off = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", sep.outputs[1],
               g.math("MULTIPLY", shrink, -1.0)), off.inputs[1])
    g.l(g.math("MULTIPLY", sep.outputs[2],
               g.math("MULTIPLY", shrink, -1.0)), off.inputs[2])
    sp = g.n("GeometryNodeSetPosition")
    g.l(body, sp.inputs[0])
    g.l(off.outputs[0], in_sock(sp, "Offset"))
    geo_n = _msock(g, out_sock(sp, "Geometry"), group_in(g, "Hull Mat"))
    # rectangular recessed nozzle on the aft cap (drive-slot language)
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    aft = g.math("LESS_THAN", ns.outputs[0], -0.9)
    geo_n, nz_top, nz_side = boss(g, geo_n, aft,
                                  g.math("MULTIPLY", S, -0.09), 0.74)
    smd2 = g.n("GeometryNodeSetMaterial")
    g.l(geo_n, smd2.inputs[0])
    g.l(nz_side, in_sock(smd2, "Selection"))
    g.l(group_in(g, "Dark Mat"), in_sock(smd2, "Material"))
    smg2 = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(smd2, "Geometry"), smg2.inputs[0])
    g.l(nz_top, in_sock(smg2, "Selection"))
    g.l(group_in(g, "Glow Mat"), in_sock(smg2, "Material"))
    return g.finish(out_sock(smg2, "Geometry"))


# ------------------------------------------------------- fleet profile -----

def build_fleet_profile():
    """t (0 tail .. 1 nose) -> W, H, Zc. Slab plan-form: chisel bow with
    deck rake, WIDER/taller stern block, seeded segmentation steps."""
    g = G("FI_FleetProfile")
    g.sock_in("t", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Bow Wedge", "NodeSocketFloat", 0.25, 0.05, 0.45)
    g.sock_in("Stern Block", "NodeSocketFloat", 0.18, 0.05, 0.35)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Nose Style", "NodeSocketInt", 0, 0, 5)
    g.sock_in("Nose Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Nose Tip", "NodeSocketFloat", 1.0, 0.1, 1.5)
    g.sock_in("Mass Bias", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Waist Position", "NodeSocketFloat", 0.5, 0.3, 0.7)
    g.sock_in("Saddle", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Stern Style", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Stern Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Stern Tip", "NodeSocketFloat", 1.0, 0.15, 1.5)
    g.sock_in("Stern Rake", "NodeSocketFloat", 0.05, -0.3, 0.3)
    g.sock_out("W", "NodeSocketFloat")
    g.sock_out("H", "NodeSocketFloat")
    g.sock_out("Zc", "NodeSocketFloat")
    t = group_in(g, "t")
    seed = group_in(g, "Seed")
    bw = group_in(g, "Bow Wedge")
    sb = group_in(g, "Stern Block")

    def clamp01(v):
        return g.math("MINIMUM", g.math("MAXIMUM", v, 0.0), 1.0)

    bow_f = clamp01(g.math("DIVIDE",
                           g.math("SUBTRACT", t,
                                  g.math("SUBTRACT", 1.0, bw)), bw))
    stern_f = clamp01(g.math("DIVIDE", g.math("SUBTRACT", sb, t), sb))

    # ---- NOSE ARCHETYPES ("different tapering styles"): Nose Style picks
    # the language, Nose Taper bends its curvature (concave<->convex),
    # Nose Tip pinches or blunts the endpoint. All are functions of
    # bf = bow_f^Taper so the two shape knobs work across every style.
    #   0 chisel   linear taper + seeded hard step, raked deck (house)
    #   1 spear    accelerating convex taper to a fine point
    #   2 hammer   waisted then FLARED tip (hammerhead prow)
    #   3 blade    width pinches hard, depth stays — vertical ram
    #               cutwater, centreline dives
    #   4 shovel   stays wide, depth thins hard, strong down-rake
    #   5 terraced three hard cascade steps (carrier bow)
    style = group_in(g, "Nose Style")
    tipk = group_in(g, "Nose Tip")
    bf = g.math("POWER", bow_f, group_in(g, "Nose Taper"))

    def ieq(k):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="EQUAL")
        g.l(style, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = k
        return out_sock(n, "Result")

    def fsw_p(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, in_sock(n, "Switch"))
        for nm, v in (("False", off), ("True", on)):
            s = in_sock(n, nm, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, s)
            else:
                s.default_value = v
        return out_sock(n, "Output", "VALUE")

    def taper_to(tip_frac):
        """1 -> tip_frac*Nose Tip along bf (clamped above 0.08)"""
        tipv = g.math("MAXIMUM",
                      g.math("MULTIPLY", tip_frac, tipk), 0.08)
        return g.math("SUBTRACT", 1.0,
                      g.math("MULTIPLY", bf,
                             g.math("SUBTRACT", 1.0, tipv)))

    def sub_f(v, lo, hi):
        """clamp01((v-lo)/(hi-lo)) — piecewise ramp helper"""
        return clamp01(g.math("DIVIDE", g.math("SUBTRACT", v, lo),
                              hi - lo))

    bs1 = g.rand_float(0.35, 0.65, None, g.math("ADD", seed, 11.0))
    step0 = g.math("MULTIPLY", 0.10, g.math("GREATER_THAN", bow_f, bs1))

    # W per style
    w0 = g.math("SUBTRACT", taper_to(0.45), step0)
    bf18 = g.math("POWER", bf, 1.8)
    tip1 = g.math("MAXIMUM", g.math("MULTIPLY", 0.12, tipk), 0.08)
    w1 = g.math("SUBTRACT", 1.0,
                g.math("MULTIPLY", bf18,
                       g.math("SUBTRACT", 1.0, tip1)))
    waist = g.math("MAXIMUM", g.math("MULTIPLY", 0.55, tipk), 0.15)
    flare = g.math("MAXIMUM", g.math("MULTIPLY", 0.85, tipk), 0.25)
    w2 = g.math("ADD",
                g.math("SUBTRACT", 1.0,
                       g.math("MULTIPLY", sub_f(bf, 0.0, 0.6),
                              g.math("SUBTRACT", 1.0, waist))),
                g.math("MULTIPLY", sub_f(bf, 0.6, 1.0),
                       g.math("SUBTRACT", flare, waist)))
    w3 = taper_to(0.20)
    w4 = taper_to(0.85)
    t5 = g.math("SUBTRACT", 1.0,
                g.math("MULTIPLY", 0.43, tipk))     # total terraced drop
    casc = g.math("ADD",
                  g.math("ADD",
                         g.math("MULTIPLY", 0.26,
                                g.math("GREATER_THAN", bf, 0.25)),
                         g.math("MULTIPLY", 0.35,
                                g.math("GREATER_THAN", bf, 0.55))),
                  g.math("MULTIPLY", 0.39,
                         g.math("GREATER_THAN", bf, 0.85)))
    w5 = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", t5, casc))
    w_bow = fsw_p(ieq(1), w0, w1)
    w_bow = fsw_p(ieq(2), w_bow, w2)
    w_bow = fsw_p(ieq(3), w_bow, w3)
    w_bow = fsw_p(ieq(4), w_bow, w4)
    w_bow = fsw_p(ieq(5), w_bow, w5)

    # H per style (chisel/terraced keep steps; blade stays deep;
    # shovel thins hard; spear tapers with the width)
    h0 = g.math("SUBTRACT", taper_to(0.30),
                g.math("MULTIPLY", 0.8, step0))
    h1 = g.math("SUBTRACT", 1.0,
                g.math("MULTIPLY", bf18,
                       g.math("SUBTRACT", 1.0, tip1)))
    h2 = taper_to(0.55)
    h3 = taper_to(0.90)
    h4 = taper_to(0.16)
    h5 = g.math("SUBTRACT", 1.0,
                g.math("MULTIPLY", g.math("MULTIPLY", t5, 0.85), casc))
    h_bow = fsw_p(ieq(1), h0, h1)
    h_bow = fsw_p(ieq(2), h_bow, h2)
    h_bow = fsw_p(ieq(3), h_bow, h3)
    h_bow = fsw_p(ieq(4), h_bow, h4)
    h_bow = fsw_p(ieq(5), h_bow, h5)

    # Zc rake per style (blade dives, shovel scoops, spear stays level)
    zc0 = fsw_p(ieq(1), -0.15, -0.06)
    zc0 = fsw_p(ieq(2), zc0, -0.10)
    zc0 = fsw_p(ieq(3), zc0, -0.28)
    zc0 = fsw_p(ieq(4), zc0, -0.25)
    zc0 = fsw_p(ieq(5), zc0, -0.12)
    zc_bow = g.math("MULTIPLY", bow_f, zc0)

    # ---- STERN ARCHETYPES (mirror of the nose system on stern_f) -------
    #   0 block     seeded step-up, wider/taller engine block (house)
    #   1 boat-tail multiplicative taper to a narrow transom
    #   2 skirt     flared transom, depth thins
    #   3 terraced  two hard cascade steps down
    sstyle = group_in(g, "Stern Style")
    stipk = group_in(g, "Stern Tip")
    sf = g.math("POWER", stern_f, group_in(g, "Stern Taper"))

    def seq(k):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="EQUAL")
        g.l(sstyle, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = k
        return out_sock(n, "Result")

    ss1 = g.rand_float(0.15, 0.45, None, g.math("ADD", seed, 12.0))
    ss2 = g.rand_float(0.20, 0.50, None, g.math("ADD", seed, 15.0))
    stipv = g.math("MAXIMUM", g.math("MULTIPLY", 0.45, stipk), 0.15)
    # style 0: additive step-up (the current block)
    wa0 = g.math("MULTIPLY", 0.12, g.math("GREATER_THAN", stern_f, ss1))
    ha0 = g.math("MULTIPLY", 0.10, g.math("GREATER_THAN", stern_f, ss2))
    # style 1: boat-tail multipliers
    wm1 = g.math("SUBTRACT", 1.0,
                 g.math("MULTIPLY", sf,
                        g.math("SUBTRACT", 1.0, stipv)))
    hm1 = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", sf, 0.45))
    # style 2: flared skirt (widens at the transom, thins vertically)
    wa2 = g.math("MULTIPLY",
                 g.math("MULTIPLY", 0.25, stipk),
                 g.math("MULTIPLY", sf, sf))
    hm2 = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", sf, 0.28))
    # style 3: terraced cascade down
    wa3 = g.math("MULTIPLY", -1.0,
                 g.math("ADD",
                        g.math("MULTIPLY", 0.14,
                               g.math("GREATER_THAN", sf, 0.35)),
                        g.math("MULTIPLY", 0.18,
                               g.math("GREATER_THAN", sf, 0.75))))
    ha3 = g.math("MULTIPLY", -0.12, g.math("GREATER_THAN", sf, 0.55))
    w_add = fsw_p(seq(2), fsw_p(seq(3), wa0, wa3), wa2)
    w_add = fsw_p(seq(1), w_add, 0.0)
    w_mul = fsw_p(seq(1), 1.0, wm1)
    h_add = fsw_p(seq(3), ha0, ha3)
    h_add = fsw_p(seq(1), fsw_p(seq(2), h_add, 0.0), 0.0)
    h_mul = fsw_p(seq(1), fsw_p(seq(2), 1.0, hm2), hm1)

    w = g.math("ADD", g.math("MULTIPLY", w_bow, w_mul), w_add)
    h = g.math("ADD", g.math("MULTIPLY", h_bow, h_mul), h_add)

    # ---- midship mass: bias / waist / saddle ----------------------------
    mb = group_in(g, "Mass Bias")
    w = g.math("MULTIPLY", w,
               g.math("ADD", 1.0,
                      g.math("MULTIPLY", mb,
                             g.math("MULTIPLY", 0.7,
                                    g.math("SUBTRACT", t, 0.5)))))
    wp = group_in(g, "Waist Position")
    # linear TENT windows, not smooth bells — the register is angular
    # creases, not organic pinches
    wd = g.math("DIVIDE", g.math("SUBTRACT", t, wp), 0.18)
    bellw = g.math("MAXIMUM", 0.0,
                   g.math("SUBTRACT", 1.0, g.math("ABSOLUTE", wd)))
    w = g.math("MULTIPLY", w,
               g.math("SUBTRACT", 1.0,
                      g.math("MULTIPLY",
                             g.math("MULTIPLY", group_in(g, "Waist"),
                                    0.30), bellw)))
    sdd = g.math("DIVIDE", g.math("SUBTRACT", t, 0.5), 0.25)
    bells = g.math("MAXIMUM", 0.0,
                   g.math("SUBTRACT", 1.0, g.math("ABSOLUTE", sdd)))
    h = g.math("MULTIPLY", h,
               g.math("SUBTRACT", 1.0,
                      g.math("MULTIPLY",
                             g.math("MULTIPLY", group_in(g, "Saddle"),
                                    0.25), bells)))

    # seeded segmentation steps (unchanged)
    amp_bias = g.math("ADD", 1.0,
                      g.math("MULTIPLY", group_in(g, "Class"), 0.5))
    for i in range(2):
        pos = g.rand_float(0.30, 0.72, None,
                           g.math("ADD", seed, 13.0 + i * 7.0))
        amp = g.math("MULTIPLY",
                     g.math("SUBTRACT",
                            g.rand_float(0.0, 1.0, None,
                                         g.math("ADD", seed,
                                                14.0 + i * 7.0)), 0.5),
                     g.math("MULTIPLY", 0.16, amp_bias))
        w = g.math("ADD", w,
                   g.math("MULTIPLY", amp, g.math("GREATER_THAN", t, pos)))
    w = g.math("MINIMUM", g.math("MAXIMUM", w, 0.08), 1.15)
    h = g.math("MINIMUM", g.math("MAXIMUM", h, 0.10), 1.15)

    # Zc: style rake over the bow, KNOBBED stern rake (D units)
    zc = g.math("ADD", zc_bow,
                g.math("MULTIPLY", stern_f, group_in(g, "Stern Rake")))

    g.gout = g.n("NodeGroupOutput")
    g.l(w, g.gout.inputs[0])
    g.l(h, g.gout.inputs[1])
    g.l(zc, g.gout.inputs[2])
    g.ng.asset_mark()
    return g.ng


# ---------------------------------------------------------- fleet hull -----

def build_fleet_hull(profile):
    """Cube-grid slab loft. fi_u unit-space capture FIRST; chine chamfer
    projection; profile loft; zone attrs; plateau/keel/deck-well bosses."""
    g = G("FI_FleetHull")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Length", "NodeSocketFloat", 120.0, 10.0, 2000.0)
    g.sock_in("Beam", "NodeSocketFloat", 38.0, 2.0, 800.0)
    g.sock_in("Depth", "NodeSocketFloat", 16.0, 1.0, 400.0)
    g.sock_in("Stations", "NodeSocketInt", 24, 8, 96)
    g.sock_in("Cols", "NodeSocketInt", 11, 5, 21)
    g.sock_in("Rows", "NodeSocketInt", 5, 3, 11)
    g.sock_in("Chine", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Chine Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Bow Wedge", "NodeSocketFloat", 0.25, 0.05, 0.45)
    g.sock_in("Stern Block", "NodeSocketFloat", 0.18, 0.05, 0.35)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Nose Style", "NodeSocketInt", 0, 0, 5)
    g.sock_in("Nose Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Nose Tip", "NodeSocketFloat", 1.0, 0.1, 1.5)
    g.sock_in("Mass Bias", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Waist Position", "NodeSocketFloat", 0.5, 0.3, 0.7)
    g.sock_in("Saddle", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Stern Style", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Stern Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Stern Tip", "NodeSocketFloat", 1.0, 0.15, 1.5)
    g.sock_in("Stern Rake", "NodeSocketFloat", 0.05, -0.3, 0.3)
    g.sock_in("Deck Crown", "NodeSocketFloat", 0.0, 0.0, 0.75)
    g.sock_in("Keel Crown", "NodeSocketFloat", 0.0, 0.0, 0.75)
    g.sock_in("Chine 2", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Chine 2 Slope", "NodeSocketFloat", 1.6, 0.3, 3.0)
    g.sock_in("Plateaus", "NodeSocketInt", 2, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Plateau Width", "NodeSocketFloat", 0.55, 0.30, 0.80)
    g.sock_in("Keel", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Towers", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Tower Levels", "NodeSocketInt", 3, 1, 3)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Width", "NodeSocketFloat", 1.0, 0.6, 1.6)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    L, B, D = (group_in(g, "Length"), group_in(g, "Beam"),
               group_in(g, "Depth"))
    seed = group_in(g, "Seed")

    cube = g.n("GeometryNodeMeshCube")
    in_sock(cube, "Size").default_value = (1.0, 1.0, 1.0)
    g.l(group_in(g, "Stations"), in_sock(cube, "Vertices X"))
    g.l(group_in(g, "Cols"), in_sock(cube, "Vertices Y"))
    g.l(group_in(g, "Rows"), in_sock(cube, "Vertices Z"))

    # fi_u: unit-space position, captured BEFORE any deformation — every
    # downstream region selection tests this, never live positions
    st_u = g.n("GeometryNodeStoreNamedAttribute", data_type="FLOAT_VECTOR",
               domain="POINT")
    g.l(out_sock(cube, "Mesh"), st_u.inputs[0])
    in_sock(st_u, "Name").default_value = "fi_u"
    pos0 = g.n("GeometryNodeInputPosition")
    g.l(out_sock(pos0, "Position"), in_sock(st_u, "Value", "VECTOR"))

    # chine chamfer projection + loft in one Set Position
    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    x, y, z = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    yn = g.math("MULTIPLY", y, 2.0)
    zn = g.math("MULTIPLY", z, 2.0)
    ay = g.math("ABSOLUTE", yn)
    az = g.math("ABSOLUTE", zn)
    m = g.math("MAXIMUM", g.math("MAXIMUM", ay, az), 0.001)
    s = g.math("MAXIMUM",
               g.math("MULTIPLY", g.math("DIVIDE", B, D),
                      group_in(g, "Chine Slope")), 0.2)
    cprime = g.math("DIVIDE",
                    g.math("SUBTRACT", 1.0,
                           g.math("MULTIPLY", group_in(g, "Chine"), 0.8)),
                    s)
    k = g.math("MAXIMUM", m,
               g.math("DIVIDE",
                      g.math("ADD", ay, g.math("DIVIDE", az, s)),
                      g.math("ADD", 1.0, cprime)))
    # second chine plane (self-neutralizing at Chine 2 = 0)
    s2 = g.math("MAXIMUM",
                g.math("MULTIPLY", g.math("DIVIDE", B, D),
                       group_in(g, "Chine 2 Slope")), 0.2)
    c2p = g.math("DIVIDE",
                 g.math("SUBTRACT", 1.0,
                        g.math("MULTIPLY", group_in(g, "Chine 2"), 0.8)),
                 s2)
    k = g.math("MAXIMUM", k,
               g.math("DIVIDE",
                      g.math("ADD", ay, g.math("DIVIDE", az, s2)),
                      g.math("ADD", 1.0, c2p)))
    # crown planes: pinch the deck (or keel) toward a narrower flat
    # crown. The plane never cuts the centreline column (ay=0 ->
    # k_crown < 1), so a flat deck/belly strip ALWAYS survives and the
    # fi_deck/fi_belly zones stay populated.
    zpos = g.math("MAXIMUM", zn, 0.0)
    ccd = g.math("SUBTRACT", 0.35,
                 g.math("MULTIPLY", group_in(g, "Deck Crown"), 0.30))
    k = g.math("MAXIMUM", k,
               g.math("DIVIDE",
                      g.math("ADD", zpos, g.math("MULTIPLY", ay, 0.35)),
                      g.math("ADD", 1.0, ccd)))
    zneg = g.math("MAXIMUM", g.math("MULTIPLY", zn, -1.0), 0.0)
    cck = g.math("SUBTRACT", 0.35,
                 g.math("MULTIPLY", group_in(g, "Keel Crown"), 0.30))
    k = g.math("MAXIMUM", k,
               g.math("DIVIDE",
                      g.math("ADD", zneg, g.math("MULTIPLY", ay, 0.35)),
                      g.math("ADD", 1.0, cck)))
    f = g.math("DIVIDE", m, k)
    ynp = g.math("MULTIPLY", yn, f)
    znp = g.math("MULTIPLY", zn, f)

    t = g.math("ADD", x, 0.5)
    tp = gcall(g, profile, wires={
        "t": t, "Seed": seed,
        "Bow Wedge": group_in(g, "Bow Wedge"),
        "Stern Block": group_in(g, "Stern Block"),
        "Class": group_in(g, "Class"),
        "Nose Style": group_in(g, "Nose Style"),
        "Nose Taper": group_in(g, "Nose Taper"),
        "Nose Tip": group_in(g, "Nose Tip"),
        "Mass Bias": group_in(g, "Mass Bias"),
        "Waist": group_in(g, "Waist"),
        "Waist Position": group_in(g, "Waist Position"),
        "Saddle": group_in(g, "Saddle"),
        "Stern Style": group_in(g, "Stern Style"),
        "Stern Taper": group_in(g, "Stern Taper"),
        "Stern Tip": group_in(g, "Stern Tip"),
        "Stern Rake": group_in(g, "Stern Rake")})
    tb = g.math("SUBTRACT", 1.0,
                g.math("MULTIPLY",
                       g.math("GREATER_THAN", znp, 0.0), 0.06))
    X = g.math("MULTIPLY", x, L)
    Y = g.math("MULTIPLY", ynp,
               g.math("MULTIPLY", g.math("DIVIDE", B, 2.0),
                      out_sock(tp, "W", "VALUE")))
    Z = g.math("ADD",
               g.math("MULTIPLY", znp,
                      g.math("MULTIPLY",
                             g.math("MULTIPLY", g.math("DIVIDE", D, 2.0),
                                    out_sock(tp, "H", "VALUE")), tb)),
               g.math("MULTIPLY", out_sock(tp, "Zc", "VALUE"), D))
    cmb = g.n("ShaderNodeCombineXYZ")
    g.l(X, cmb.inputs[0])
    g.l(Y, cmb.inputs[1])
    g.l(Z, cmb.inputs[2])
    sp = g.n("GeometryNodeSetPosition")
    g.l(out_sock(st_u, "Geometry"), sp.inputs[0])
    g.l(cmb.outputs[0], in_sock(sp, "Position"))
    geo = out_sock(sp, "Geometry")

    # zone attrs, stored ONCE (walls inherit them later)
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    zones = (("fi_deck", g.math("GREATER_THAN", ns.outputs[2], 0.8)),
             ("fi_belly", g.math("LESS_THAN", ns.outputs[2], -0.8)),
             ("fi_flank", g.math("GREATER_THAN",
                                 g.math("ABSOLUTE", ns.outputs[1]), 0.6)),
             ("fi_cap_aft", g.math("LESS_THAN", ns.outputs[0], -0.85)),
             ("fi_cap_fore", g.math("GREATER_THAN", ns.outputs[0], 0.85)))
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

    ux, uy, uz = named_vec("fi_u")
    tx = g.math("ADD", ux, 0.5)            # 0 tail .. 1 nose
    ay2 = g.math("MULTIPLY", g.math("ABSOLUTE", uy), 2.0)  # 0..1 beam frac
    pw = group_in(g, "Plateau Width")
    sb = group_in(g, "Stern Block")
    bw = group_in(g, "Bow Wedge")
    nplat = group_in(g, "Plateaus")

    def band(v, lo, hi):
        return g.math("MULTIPLY",
                      g.math("GREATER_THAN", v, lo),
                      g.math("LESS_THAN", v, hi))

    # plateau level 1: single chamfer-rimmed region boss on the deck
    p1_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY", named_bool("fi_deck"),
                           g.math("LESS_THAN", ay2, pw)),
                    g.math("MULTIPLY",
                           band(tx, g.math("ADD", sb, 0.03),
                                g.math("SUBTRACT",
                                       g.math("SUBTRACT", 1.0, bw), 0.05)),
                           g.math("GREATER_THAN", nplat, 0.5)))
    ph = g.math("MULTIPLY", group_in(g, "Plateau Height"),
                g.math("MULTIPLY", D, 0.22))
    geo, p1_top, _ = boss(g, geo, p1_sel, ph, 0.90)
    geo = store_bool(geo, "fi_plat1", p1_top)

    # plateau level 2: narrower, shorter, on level-1 tops (skin-guarded)
    nz2 = g.n("GeometryNodeInputNormal")
    ns2 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nz2, "Normal"), ns2.inputs[0])
    up2 = g.math("GREATER_THAN", ns2.outputs[2], 0.8)
    p2_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY", named_bool("fi_plat1"),
                           g.math("MULTIPLY",
                                  g.math("LESS_THAN", ay2,
                                         g.math("MULTIPLY", pw, 0.55)),
                                  up2)),
                    g.math("MULTIPLY",
                           band(tx, g.math("ADD", sb, 0.08),
                                g.math("SUBTRACT",
                                       g.math("SUBTRACT", 1.0, bw), 0.12)),
                           g.math("GREATER_THAN", nplat, 1.5)))
    geo, p2_top, _ = boss(g, geo, g.math("MULTIPLY", p2_sel, 1.0),
                          g.math("MULTIPLY", ph, 0.60), 0.88)
    geo = store_bool(geo, "fi_plat2", p2_top)

    # ventral keel block
    keel_on = g.math("GREATER_THAN", group_in(g, "Keel"), 0.02)
    k_sel = g.math("MULTIPLY",
                   g.math("MULTIPLY", named_bool("fi_belly"),
                          g.math("LESS_THAN", ay2, 0.22)),
                   g.math("MULTIPLY",
                          band(tx, g.math("ADD", sb, 0.05), 0.75),
                          keel_on))
    kh = g.math("MULTIPLY", group_in(g, "Keel"),
                g.math("MULTIPLY", D, 0.12))
    geo, k_top, _ = boss(g, geo, k_sel, kh, 0.92)
    geo = store_bool(geo, "fi_keel", k_top)

    # charcoal deck wells: the strips between plateau shoulder and chine
    nz3 = g.n("GeometryNodeInputNormal")
    ns3 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nz3, "Normal"), ns3.inputs[0])
    up3 = g.math("GREATER_THAN", ns3.outputs[2], 0.8)
    not_p1 = g.n("FunctionNodeBooleanMath", operation="NOT")
    g.l(named_bool("fi_plat1"), not_p1.inputs[0])
    dw_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY",
                           g.math("MULTIPLY", named_bool("fi_deck"),
                                  not_p1.outputs[0]),
                           g.math("MULTIPLY", up3,
                                  band(ay2, g.math("ADD", pw, 0.10),
                                       0.80))),
                    band(tx, g.math("ADD", sb, 0.04),
                         g.math("SUBTRACT",
                                g.math("SUBTRACT", 1.0, bw), 0.06)))
    geo, dw_top, _ = boss(g, geo, dw_sel,
                          g.math("MULTIPLY", D, -0.015), 0.94)
    geo = store_bool(geo, "fi_deckwell", dw_top)

    # ---- INTEGRATED superstructure ("part of the actual mesh", hers):
    # stacked region bosses grown from the deck grid — the plateau
    # machinery with a per-level rake shift. Because the tower IS hull
    # skin, the divider panels it, the patchwork paints it and the
    # window shader lights it downstream — consistent by construction.
    tw_n = group_in(g, "Towers")
    tw_lv = group_in(g, "Tower Levels")
    tw_h = group_in(g, "Tower Height")
    tw_w = group_in(g, "Tower Width")
    tw_r = group_in(g, "Tower Rake")
    # level windows are sized in GRID-STEP units so every level always
    # captures at least one face column (absolute windows went dead
    # between stations); rake shifts stay within the previous level's
    # footprint by construction
    step_tx = g.math("DIVIDE", 1.0,
                     g.math("SUBTRACT", group_in(g, "Stations"), 1.0))
    lvl_wx = (1.6, 1.1, 0.6)      # x grid steps
    lvl_wy = (0.35, 0.25, 0.12)   # uy2 units (cols step 0.2)
    lvl_hz = (0.16, 0.13, 0.11)
    for ti, txc in enumerate((0.34, 0.54)):
        tgate = g.math("GREATER_THAN", tw_n, float(ti) + 0.5)
        for lv in range(3):
            lgate = g.math("GREATER_THAN", tw_lv, float(lv) - 0.5)
            nrm_t = g.n("GeometryNodeInputNormal")
            nst = g.n("ShaderNodeSeparateXYZ")
            g.l(out_sock(nrm_t, "Normal"), nst.inputs[0])
            up_t = g.math("GREATER_THAN", nst.outputs[2], 0.8)
            wx = g.math("MULTIPLY",
                        g.math("MULTIPLY", lvl_wx[lv], step_tx), tw_w)
            sel_t = g.math("MULTIPLY",
                           g.math("MULTIPLY",
                                  g.math("LESS_THAN",
                                         g.math("ABSOLUTE",
                                                g.math("SUBTRACT", tx,
                                                       txc)), wx),
                                  g.math("LESS_THAN", ay2,
                                         g.math("MULTIPLY",
                                                lvl_wy[lv], tw_w))),
                           g.math("MULTIPLY",
                                  g.math("MULTIPLY", up_t, tgate),
                                  lgate))
            geo, t_top2, _ = boss(g, geo, sel_t,
                                  g.math("MULTIPLY",
                                         g.math("MULTIPLY", D,
                                                lvl_hz[lv]),
                                         tw_h), 0.86)
            # rake = geometric SHEAR of the level top (+x); borders stay
            # put so it is watertight, and it is continuous (window
            # re-selection was grid-quantized and went knob-dead)
            shx = g.n("ShaderNodeCombineXYZ")
            g.l(g.math("MULTIPLY", tw_r,
                       g.math("MULTIPLY", D, 0.10)), shx.inputs[0])
            spt = g.n("GeometryNodeSetPosition")
            g.l(geo, spt.inputs[0])
            g.l(t_top2, in_sock(spt, "Selection"))
            g.l(shx.outputs[0], in_sock(spt, "Offset"))
            geo = out_sock(spt, "Geometry")

    return g.finish(geo)



def build_fleet_dressed(mats, hg, parts):
    """The complete DRESSED hull — loft, paneling, patchwork attrs,
    relief, blisters, faction materials, drive slots, apertures, weld,
    emission mask — factored into one group so HULL FORMS can instance
    it (mono / catamaran / asymmetric module). Takes explicit L/B/D so
    the form composer can feed per-hull dims."""
    g = G("FI_FleetDressedHull")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Length", "NodeSocketFloat", 120.0, 10.0, 2000.0)
    g.sock_in("Beam", "NodeSocketFloat", 38.0, 2.0, 800.0)
    g.sock_in("Depth", "NodeSocketFloat", 16.0, 1.0, 400.0)
    g.sock_in("Stations", "NodeSocketInt", 24, 8, 96)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Plateaus", "NodeSocketInt", 2, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Plateau Width", "NodeSocketFloat", 0.55, 0.30, 0.80)
    g.sock_in("Chine", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Chine Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Bow Wedge", "NodeSocketFloat", 0.25, 0.05, 0.45)
    g.sock_in("Stern Block", "NodeSocketFloat", 0.18, 0.05, 0.35)
    g.sock_in("Nose Style", "NodeSocketInt", 0, 0, 5)
    g.sock_in("Nose Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Nose Tip", "NodeSocketFloat", 1.0, 0.1, 1.5)
    g.sock_in("Mass Bias", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Waist Position", "NodeSocketFloat", 0.5, 0.3, 0.7)
    g.sock_in("Saddle", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Stern Style", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Stern Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Stern Tip", "NodeSocketFloat", 1.0, 0.15, 1.5)
    g.sock_in("Stern Rake", "NodeSocketFloat", 0.05, -0.3, 0.3)
    g.sock_in("Deck Crown", "NodeSocketFloat", 0.0, 0.0, 0.75)
    g.sock_in("Keel Crown", "NodeSocketFloat", 0.0, 0.0, 0.75)
    g.sock_in("Chine 2", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Chine 2 Slope", "NodeSocketFloat", 1.6, 0.3, 3.0)
    g.sock_in("Keel", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Towers", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Tower Levels", "NodeSocketInt", 3, 1, 3)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Width", "NodeSocketFloat", 1.0, 0.6, 1.6)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Nozzles", "NodeSocketInt", 2, 1, 3)
    g.sock_in("Panel Density", "NodeSocketInt", 2, 1, 4)
    g.sock_in("Patchwork", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Accent Fields", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Blisters", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 4, 0, 6)
    g.sock_in("Accent Bands", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Dorsal Stripe", "NodeSocketBool", False)
    g.sock_in("Hue Jitter", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Deck Markings", "NodeSocketBool", True)
    g.sock_in("Thrusters", "NodeSocketBool", False)
    g.sock_in("Bow Mouth", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Hangars", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hangar Size", "NodeSocketFloat", 1.0, 0.5, 1.5)
    g.sock_in("Deck Trench", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    seed = group_in(g, "Seed")
    L = group_in(g, "Length")
    B = group_in(g, "Beam")
    D = group_in(g, "Depth")
    stations = group_in(g, "Stations")

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

    hull = gcall(g, parts["hull"], wires={
        "Seed": seed, "Length": L, "Beam": B, "Depth": D,
        "Stations": stations,
        "Chine": group_in(g, "Chine"),
        "Chine Slope": group_in(g, "Chine Slope"),
        "Bow Wedge": group_in(g, "Bow Wedge"),
        "Stern Block": group_in(g, "Stern Block"),
        "Class": group_in(g, "Class"),
        "Nose Style": group_in(g, "Nose Style"),
        "Nose Taper": group_in(g, "Nose Taper"),
        "Nose Tip": group_in(g, "Nose Tip"),
        "Mass Bias": group_in(g, "Mass Bias"),
        "Waist": group_in(g, "Waist"),
        "Waist Position": group_in(g, "Waist Position"),
        "Saddle": group_in(g, "Saddle"),
        "Stern Style": group_in(g, "Stern Style"),
        "Stern Taper": group_in(g, "Stern Taper"),
        "Stern Tip": group_in(g, "Stern Tip"),
        "Stern Rake": group_in(g, "Stern Rake"),
        "Deck Crown": group_in(g, "Deck Crown"),
        "Keel Crown": group_in(g, "Keel Crown"),
        "Chine 2": group_in(g, "Chine 2"),
        "Chine 2 Slope": group_in(g, "Chine 2 Slope"),
        "Plateaus": group_in(g, "Plateaus"),
        "Plateau Height": group_in(g, "Plateau Height"),
        "Plateau Width": group_in(g, "Plateau Width"),
        "Keel": group_in(g, "Keel"),
        "Towers": group_in(g, "Towers"),
        "Tower Levels": group_in(g, "Tower Levels"),
        "Tower Height": group_in(g, "Tower Height"),
        "Tower Width": group_in(g, "Tower Width"),
        "Tower Rake": group_in(g, "Tower Rake")})
    geo = out_sock(hull, "Geometry")

    # ---- shared attribute readers --------------------------------------
    def named_bool2(name):
        n = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
        in_sock(n, "Name").default_value = name
        return out_sock(n, "Attribute")

    def named_float(name):
        n = g.n("GeometryNodeInputNamedAttribute", data_type="FLOAT")
        in_sock(n, "Name").default_value = name
        return out_sock(n, "Attribute")

    def named_vec2(name):
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

    def band(v, lo, hi):
        return g.math("MULTIPLY",
                      g.math("GREATER_THAN", v, lo),
                      g.math("LESS_THAN", v, hi))

    # ---- paneling: divider -> patchwork attrs -> per-panel relief ------
    # the aft cap is EXCLUDED from the divider: drive slots need the
    # pristine contiguous cap grid (deep region recesses on detached
    # divider islands tear their borders loose)
    # aperture zones, stored BEFORE the divider (deep region cuts must
    # never land on divider-detached faces — the drive-slot rule).
    zux, zuy, zuz = named_vec2("fi_u")
    ztx = g.math("ADD", zux, 0.5)
    zay2 = g.math("MULTIPLY", g.math("ABSOLUTE", zuy), 2.0)
    zuz2 = g.math("MULTIPLY", zuz, 2.0)
    znrm = g.n("GeometryNodeInputNormal")
    zns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(znrm, "Normal"), zns.inputs[0])
    hz_sum = None
    for i in range(2):
        hc = g.rand_float(0.28, 0.62, None,
                          g.math("ADD", seed, 83.0 + i * 7.0))
        hw2 = g.math("MULTIPLY", 0.055, group_in(g, "Hangar Size"))
        hzone = g.math("MULTIPLY",
                       g.math("MULTIPLY",
                              g.math("GREATER_THAN",
                                     g.math("ABSOLUTE", zns.outputs[1]),
                                     0.9),
                              band(ztx, g.math("SUBTRACT", hc, hw2),
                                   g.math("ADD", hc, hw2))),
                       g.math("MULTIPLY",
                              g.math("LESS_THAN",
                                     g.math("ABSOLUTE", zuz2), 0.45),
                              int_gt(group_in(g, "Hangars"), i)))
        hz_sum = hzone if hz_sum is None else g.math("ADD", hz_sum, hzone)
    st_hg = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                domain="FACE")
    g.l(geo, st_hg.inputs[0])
    in_sock(st_hg, "Name").default_value = "fi_hangar"
    g.l(g.math("GREATER_THAN", hz_sum, 0.5), in_sock(st_hg, "Value"))
    geo = out_sock(st_hg, "Geometry")
    tr_on = g.math("GREATER_THAN", group_in(g, "Deck Trench"), 0.02)
    trz = g.math("MULTIPLY",
                 g.math("MULTIPLY",
                        g.math("GREATER_THAN", zns.outputs[2], 0.8),
                        g.math("LESS_THAN", zay2, 0.10)),
                 g.math("MULTIPLY",
                        band(ztx, g.math("ADD",
                                         group_in(g, "Stern Block"),
                                         0.06),
                             g.math("SUBTRACT",
                                    g.math("SUBTRACT", 1.0,
                                           group_in(g, "Bow Wedge")),
                                    0.08)),
                        tr_on))
    st_tr = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                domain="FACE")
    g.l(geo, st_tr.inputs[0])
    in_sock(st_tr, "Name").default_value = "fi_trench"
    g.l(trz, in_sock(st_tr, "Value"))
    geo = out_sock(st_tr, "Geometry")

    cap0 = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
    in_sock(cap0, "Name").default_value = "fi_cap_aft"
    ncap0 = g.n("FunctionNodeBooleanMath", operation="NOT")
    g.l(out_sock(cap0, "Attribute"), ncap0.inputs[0])
    capf0 = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
    in_sock(capf0, "Name").default_value = "fi_cap_fore"
    mouth_on = g.math("GREATER_THAN", group_in(g, "Bow Mouth"), 0.02)
    excl_f = g.math("MULTIPLY", out_sock(capf0, "Attribute"), mouth_on)
    hgr0 = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
    in_sock(hgr0, "Name").default_value = "fi_hangar"
    trr0 = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
    in_sock(trr0, "Name").default_value = "fi_trench"
    keep = g.math("MULTIPLY",
                  g.math("MULTIPLY", ncap0.outputs[0],
                         g.math("SUBTRACT", 1.0, excl_f)),
                  g.math("MULTIPLY",
                         g.math("SUBTRACT", 1.0,
                                out_sock(hgr0, "Attribute")),
                         g.math("SUBTRACT", 1.0,
                                out_sock(trr0, "Attribute"))))
    panels = gcall(g, hg["Mesh Face Divider"], wires={
        "Mesh": geo, "Seed": seed,
        "Selection": keep,
        "Iterations": group_in(g, "Panel Density"),
        "Limit Distance": g.math("MULTIPLY", B, 0.03)},
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
    # hue jitter attr: knob scales the ATTR, shader applies full range
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

    # accent fields: 1-3 seeded rectangular unit-space zones on the skin
    pux, puy, puz = named_vec2("fi_u")
    ptx = g.math("ADD", pux, 0.5)
    pay2 = g.math("MULTIPLY", g.math("ABSOLUTE", puy), 2.0)
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
                             band(ptx, za, g.math("ADD", za, zl)),
                             g.math("LESS_THAN", pay2, zw)),
                      int_gt(group_in(g, "Accent Fields"), i))
        acc_sum = zone if acc_sum is None else g.math("ADD", acc_sum, zone)
    # transverse accent BANDS (full rings) + dorsal stripe
    for i in range(2):
        bc = g.rand_float(0.20, 0.75, None,
                          g.math("ADD", seed, 41.0 + i * 9.0))
        bwd = g.rand_float(0.025, 0.05, None,
                           g.math("ADD", seed, 42.0 + i * 9.0))
        bandz = g.math("MULTIPLY",
                       band(ptx, g.math("SUBTRACT", bc, bwd),
                            g.math("ADD", bc, bwd)),
                       int_gt(group_in(g, "Accent Bands"), i))
        acc_sum = g.math("ADD", acc_sum, bandz)
    stripe = g.math("MULTIPLY",
                    g.math("MULTIPLY",
                           g.math("LESS_THAN", pay2, 0.10),
                           named_bool2("fi_deck")),
                    group_in(g, "Dorsal Stripe"))
    acc_sum = g.math("ADD", acc_sum, stripe)
    accf = g.math("MULTIPLY",
                  g.math("MULTIPLY",
                         g.math("GREATER_THAN", acc_sum, 0.5),
                         bnot(named_bool2("fi_deckwell"))),
                  bnot(named_bool2("fi_cap_aft")))
    st_a = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
               domain="FACE")
    g.l(geo, st_a.inputs[0])
    in_sock(st_a, "Name").default_value = "fi_accent"
    g.l(accf, in_sock(st_a, "Value"))
    geo = out_sock(st_a, "Geometry")
    # painted deck dashes (knob -> attr; shaders can't read knobs)
    st_dm = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                domain="FACE")
    g.l(geo, st_dm.inputs[0])
    in_sock(st_dm, "Name").default_value = "fi_deckmark"
    dm_and = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(named_bool2("fi_deckwell"), dm_and.inputs[0])
    g.l(group_in(g, "Deck Markings"), dm_and.inputs[1])
    g.l(dm_and.outputs[0], in_sock(st_dm, "Value"))
    geo = out_sock(st_dm, "Geometry")
    # lit-window panels: seeded flank faces near the deck line
    nrmw = g.n("GeometryNodeInputNormal")
    nsw2 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrmw, "Normal"), nsw2.inputs[0])
    fidw = g.n("GeometryNodeInputIndex")
    glow_sel = g.math("MULTIPLY",
                      g.math("MULTIPLY",
                             g.math("GREATER_THAN",
                                    g.math("ABSOLUTE", nsw2.outputs[1]),
                                    0.6),
                             band(g.math("MULTIPLY", puz, 2.0),
                                  0.10, 1.60)),
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
    st_gw = g.n("GeometryNodeStoreNamedAttribute", data_type="BOOLEAN",
                domain="FACE")
    g.l(geo, st_gw.inputs[0])
    in_sock(st_gw, "Name").default_value = "fi_glowpanel"
    g.l(glow_sel, in_sock(st_gw, "Value"))
    geo = out_sock(st_gw, "Geometry")

    # per-panel relief: panels sink by their tint (Patchwork scales it),
    # accent fields ride PROUD — geometry-coupled so both knobs sweep
    acc_r = named_bool2("fi_accent")
    tint_r = named_float("fi_tint")
    d_sink = g.math("MULTIPLY", D,
                    g.math("MULTIPLY", -1.0,
                           g.math("ADD", 0.006,
                                  g.math("MULTIPLY", 0.008,
                                         g.math("MULTIPLY", tint_r,
                                                group_in(g,
                                                         "Patchwork"))))))
    d_relief = g.math("ADD",
                      g.math("MULTIPLY", d_sink,
                             g.math("SUBTRACT", 1.0, acc_r)),
                      g.math("MULTIPLY", g.math("MULTIPLY", D, 0.004),
                             acc_r))
    # area floor: never sink slivers (thin chine strips / step walls) —
    # an individual recess deeper than a face is wide orphans its walls.
    # Slivers keep their fi_tint patchwork colour via the shader.
    areap = g.n("GeometryNodeInputMeshFaceArea")
    bigp = g.math("GREATER_THAN", out_sock(areap, "Area"),
                  g.math("MULTIPLY", g.math("MULTIPLY", L, B), 0.0008))
    pr_sel = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(bnot(named_bool2("fi_deckwell")), pr_sel.inputs[0])
    g.l(bnot(named_bool2("fi_cap_aft")), pr_sel.inputs[1])
    pr_selb = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pr_sel.outputs[0], pr_selb.inputs[0])
    g.l(bnot(named_bool2("fi_hangar")), pr_selb.inputs[1])
    pr_selc = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pr_selb.outputs[0], pr_selc.inputs[0])
    g.l(bnot(named_bool2("fi_trench")), pr_selc.inputs[1])
    pr_sel2 = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(pr_selc.outputs[0], pr_sel2.inputs[0])
    g.l(bigp, pr_sel2.inputs[1])
    geo, _, _ = boss(g, geo, pr_sel2.outputs[0], d_relief, 0.90,
                     individual=True)

    # blisters: two-step chamfered module housings on seeded deck panels
    nrmb = g.n("GeometryNodeInputNormal")
    nsb = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrmb, "Normal"), nsb.inputs[0])
    upb = g.math("GREATER_THAN", nsb.outputs[2], 0.8)
    areab = g.n("GeometryNodeInputMeshFaceArea")
    bigb = g.math("GREATER_THAN", out_sock(areab, "Area"),
                  g.math("MULTIPLY", g.math("MULTIPLY", L, B), 0.0012))
    fidb = g.n("GeometryNodeInputIndex")
    b_pick = g.math("LESS_THAN",
                    g.rand_float(0.0, 1.0, out_sock(fidb, "Index"),
                                 g.math("ADD", seed, 91.0)),
                    g.math("MULTIPLY", group_in(g, "Blisters"), 0.35))
    deckish = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(named_bool2("fi_deck"), deckish.inputs[0])
    g.l(named_bool2("fi_plat1"), deckish.inputs[1])
    b_sel = g.math("MULTIPLY",
                   g.math("MULTIPLY",
                          g.math("MULTIPLY", deckish.outputs[0], upb),
                          g.math("MULTIPLY", bigb, b_pick)),
                   bnot(named_bool2("fi_deckwell")))
    geo, b1t, b1s = boss(g, geo, b_sel,
                         g.math("MULTIPLY", D, 0.030), 0.82,
                         individual=True)
    geo, b2t, b2s = boss(g, geo, b1t,
                         g.math("MULTIPLY", D, 0.012), 0.85,
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

    # ---- faction material switch --------------------------------------
    is_oxr = int_eq(group_in(g, "Faction"), 1)
    is_nyx = int_eq(group_in(g, "Faction"), 2)

    def mat3(role):
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
        return out_sock(m2, "Output", "MATERIAL")

    def named_bool(name):
        n = g.n("GeometryNodeInputNamedAttribute", data_type="BOOLEAN")
        in_sock(n, "Name").default_value = name
        return out_sock(n, "Attribute")

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
    geo = set_mat(geo, None, mat3("hull"))
    geo = set_mat(geo, named_bool("fi_deckwell"), mat3("deck"))

    # ---- integrated drive: slot nozzles recessed into the aft cap -----
    def named_vec(name):
        n = g.n("GeometryNodeInputNamedAttribute",
                data_type="FLOAT_VECTOR")
        in_sock(n, "Name").default_value = name
        sp2 = g.n("ShaderNodeSeparateXYZ")
        g.l(out_sock(n, "Attribute"), sp2.inputs[0])
        return sp2.outputs[0], sp2.outputs[1], sp2.outputs[2]

    ux, uy, uz = named_vec("fi_u")
    uy2 = g.math("MULTIPLY", uy, 2.0)
    uz2 = g.math("MULTIPLY", uz, 2.0)
    cap = named_bool("fi_cap_aft")
    N = group_in(g, "Nozzles")
    n_odd = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(int_eq(N, 1), n_odd.inputs[0])
    g.l(int_eq(N, 3), n_odd.inputs[1])

    # fixed slot bands, tuned to the cap grid (column centres sit at
    # uy2 = ±0.1, ±0.3, ±0.5 ... — band edges land BETWEEN centres so no
    # float coin-flips): A = centre pair, B/C = outboard pairs. N=1 -> A,
    # N=2 -> B+C, N=3 -> all three; each set is a distinct region.
    slot_tops, slot_sides = [], []
    slots = ((0.0, 0.14, n_odd.outputs[0]),
             (0.40, 0.19, int_gt(N, 1)), (-0.40, 0.19, int_gt(N, 1)))
    for cy, hw, gate in slots:
        sel = g.math("MULTIPLY",
                     g.math("MULTIPLY", cap, gate),
                     g.math("MULTIPLY",
                            g.math("LESS_THAN",
                                   g.math("ABSOLUTE",
                                          g.math("SUBTRACT", uy2, cy)),
                                   hw),
                            g.math("LESS_THAN",
                                   g.math("ABSOLUTE", uz2), 0.55)))
        geo, s_top, s_side = boss(g, geo, sel,
                                  g.math("MULTIPLY", D, -0.25), 0.80)
        slot_tops.append(s_top)
        slot_sides.append(s_side)

    # corner vernier ports (per-face)
    v_sel = g.math("MULTIPLY", cap,
                   g.math("MULTIPLY",
                          g.math("GREATER_THAN",
                                 g.math("ABSOLUTE", uy2), 0.72),
                          g.math("GREATER_THAN",
                                 g.math("ABSOLUTE", uz2), 0.50)))
    geo, v_top, v_side = boss(g, geo, v_sel,
                              g.math("MULTIPLY", D, -0.05), 0.55,
                              individual=True)

    # optional manoeuvring ports (Thrusters, default OFF — her call):
    # sparse seeded glow recesses on big skin faces away from midship
    fidth = g.n("GeometryNodeInputIndex")
    th_pick = g.math("LESS_THAN",
                     g.rand_float(0.0, 1.0, out_sock(fidth, "Index"),
                                  g.math("ADD", seed, 57.0)), 0.05)
    areath = g.n("GeometryNodeInputMeshFaceArea")
    bigth = g.math("GREATER_THAN", out_sock(areath, "Area"),
                   g.math("MULTIPLY", g.math("MULTIPLY", L, B), 0.0008))
    th_sel = g.math("MULTIPLY",
                    g.math("MULTIPLY",
                           g.math("MULTIPLY", group_in(g, "Thrusters"),
                                  th_pick),
                           g.math("MULTIPLY", bigth,
                                  g.math("GREATER_THAN",
                                         g.math("ABSOLUTE", ux), 0.22))),
                    g.math("MULTIPLY",
                           g.math("SUBTRACT", 1.0, cap),
                           g.math("SUBTRACT", 1.0,
                                  named_bool("fi_deckwell"))))
    geo, th_top, th_side = boss(g, geo, th_sel,
                                g.math("MULTIPLY", D, -0.035), 0.5,
                                individual=True)

    # ---- apertures: bow mouth / hangars / deck trench (Tier B) ---------
    prof = parts["profile"]
    capf = named_bool("fi_cap_fore")
    tp_tip = gcall(g, prof, values={"t": 0.995}, wires={
        "Seed": seed,
        "Bow Wedge": group_in(g, "Bow Wedge"),
        "Stern Block": group_in(g, "Stern Block"),
        "Class": group_in(g, "Class"),
        "Nose Style": group_in(g, "Nose Style"),
        "Nose Taper": group_in(g, "Nose Taper"),
        "Nose Tip": group_in(g, "Nose Tip"),
        "Mass Bias": group_in(g, "Mass Bias"),
        "Waist": group_in(g, "Waist"),
        "Waist Position": group_in(g, "Waist Position"),
        "Saddle": group_in(g, "Saddle"),
        "Stern Style": group_in(g, "Stern Style"),
        "Stern Taper": group_in(g, "Stern Taper"),
        "Stern Tip": group_in(g, "Stern Tip"),
        "Stern Rake": group_in(g, "Stern Rake")})
    m_sel = g.math("MULTIPLY",
                   g.math("MULTIPLY", capf,
                          g.math("GREATER_THAN",
                                 group_in(g, "Bow Mouth"), 0.02)),
                   g.math("MULTIPLY",
                          g.math("LESS_THAN",
                                 g.math("ABSOLUTE", uy2), 0.55),
                          g.math("LESS_THAN",
                                 g.math("ABSOLUTE", uz2), 0.55)))
    m_depth = g.math("MULTIPLY",
                     g.math("MULTIPLY", group_in(g, "Bow Mouth"), -0.30),
                     g.math("MULTIPLY", D,
                            g.math("MINIMUM",
                                   g.math("MULTIPLY",
                                          out_sock(tp_tip, "W", "VALUE"),
                                          1.2), 1.0)))
    geo, m_top, m_side = boss(g, geo, m_sel, m_depth, 0.78)
    hg_sel = named_bool("fi_hangar")
    geo, hg_top, hg_side = boss(g, geo, hg_sel,
                                g.math("MULTIPLY", B, -0.09), 0.88)
    tr_sel = named_bool("fi_trench")
    geo, tr_top, tr_side = boss(g, geo, tr_sel,
                                g.math("MULTIPLY",
                                       g.math("MULTIPLY", D, -0.06),
                                       group_in(g, "Deck Trench")), 0.92)

    def or_chain(sels):
        cur = sels[0]
        for nxt in sels[1:]:
            n = g.n("FunctionNodeBooleanMath", operation="OR")
            g.l(cur, n.inputs[0])
            g.l(nxt, n.inputs[1])
            cur = n.outputs[0]
        return cur

    geo = set_mat(geo, or_chain(slot_sides + [v_side, th_side, m_side,
                                              hg_side, tr_side]), "dark")
    geo = set_mat(geo, or_chain([hg_top, tr_top]), "cavity")
    geo = set_mat(geo, or_chain(slot_tops + [v_top, th_top, m_top]),
                  mat3("drive"))

    # final weld: fuse divider islands / coincident borders. The weld
    # distance must SCALE with the ship — divider border coincidence
    # error grows with face size, and a fixed 2 mm silently stops
    # welding at cruiser scale (every sunk panel then shows its full
    # sink as daylight). B*2e-4 = 7.6 mm frigate / 16 mm cruiser, still
    # far below the smallest feature (min panel sink ~0.006*D).
    weld = g.n("GeometryNodeMergeByDistance")
    g.l(geo, weld.inputs[0])
    g.l(g.math("MAXIMUM", g.math("MULTIPLY", B, 0.0002), 0.002),
        in_sock(weld, "Distance"))
    welded = out_sock(weld, "Geometry")

    # ---- running lights as EMISSION (her call: shader, not geometry).
    # fi_light = per-POINT band mask in unit space (plateau shoulders /
    # deck edges / flank chines, thresholds on the Light Rows knob); the
    # hull shader multiplies it by an object-space X dot pulse and drives
    # Principled emission -> bakes into the emissive map. Living inside
    # the hull chain, it survives any hull form for free.
    lux, luy, luz = named_vec("fi_u")
    l_ay2 = g.math("MULTIPLY", g.math("ABSOLUTE", luy), 2.0)
    l_uz2 = g.math("MULTIPLY", luz, 2.0)
    l_tx = g.math("ADD", lux, 0.5)
    sbk = group_in(g, "Stern Block")
    bwk = group_in(g, "Bow Wedge")
    in_x = g.math("MULTIPLY",
                  g.math("GREATER_THAN", l_tx,
                         g.math("ADD", sbk, 0.10)),
                  g.math("LESS_THAN", l_tx,
                         g.math("SUBTRACT",
                                g.math("SUBTRACT", 1.0, bwk), 0.14)))
    pw_b = g.math("MULTIPLY", group_in(g, "Plateau Width"), 0.92)
    band_a = g.math("MULTIPLY",
                    g.math("LESS_THAN",
                           g.math("ABSOLUTE",
                                  g.math("SUBTRACT", l_ay2, pw_b)), 0.06),
                    g.math("GREATER_THAN", l_uz2, 0.5))
    band_b = g.math("MULTIPLY",
                    g.math("LESS_THAN",
                           g.math("ABSOLUTE",
                                  g.math("SUBTRACT", l_ay2, 0.72)), 0.06),
                    g.math("GREATER_THAN", l_uz2, 0.5))
    band_c = g.math("MULTIPLY",
                    g.math("LESS_THAN",
                           g.math("ABSOLUTE",
                                  g.math("ADD", l_uz2, 0.10)), 0.12),
                    g.math("GREATER_THAN", l_ay2, 0.90))
    lr = group_in(g, "Light Rows")
    lmask = g.math("ADD",
                   g.math("ADD",
                          g.math("MULTIPLY", band_a, int_gt(lr, 0)),
                          g.math("MULTIPLY", band_b, int_gt(lr, 2))),
                   g.math("MULTIPLY", band_c, int_gt(lr, 4)))
    lmask = g.math("MULTIPLY",
                   g.math("MINIMUM", lmask, 1.0), in_x)
    st_l = g.n("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
               domain="POINT")
    g.l(welded, st_l.inputs[0])
    in_sock(st_l, "Name").default_value = "fi_light"
    g.l(lmask, in_sock(st_l, "Value", "VALUE"))
    welded = out_sock(st_l, "Geometry")
    return g.finish(welded)


# ---------------------------------------------------------- fleet ship -----

def build_fleet_ship(mats, hg, parts):
    g = G("FI_FleetShip")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Detail", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Scale", "NodeSocketFloat", 1.0, 0.1, 10.0)
    g.sock_in("Length Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Beam Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Depth Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Plateaus", "NodeSocketInt", 2, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Plateau Width", "NodeSocketFloat", 0.55, 0.30, 0.80)
    g.sock_in("Chine", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Chine Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Bow Wedge", "NodeSocketFloat", 0.25, 0.05, 0.45)
    g.sock_in("Stern Block", "NodeSocketFloat", 0.18, 0.05, 0.35)
    g.sock_in("Nose Style", "NodeSocketInt", 0, 0, 5)
    g.sock_in("Nose Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Nose Tip", "NodeSocketFloat", 1.0, 0.1, 1.5)
    g.sock_in("Keel", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Nozzles", "NodeSocketInt", 2, 1, 3)
    g.sock_in("Panel Density", "NodeSocketInt", 2, 1, 4)
    g.sock_in("Patchwork", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Accent Fields", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Blisters", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 4, 0, 6)
    g.sock_in("Vents", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Radomes", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Antennas", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Sponsons", "NodeSocketInt", 1, 0, 3)
    g.sock_in("Booms", "NodeSocketBool", True)
    g.sock_in("Decals", "NodeSocketInt", 2, 0, 2)
    # her call: this family likely flies without RCS — option, default OFF
    g.sock_in("Thrusters", "NodeSocketBool", False)
    g.sock_in("Mass Bias", "NodeSocketFloat", 0.0, -1.0, 1.0)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Waist Position", "NodeSocketFloat", 0.5, 0.3, 0.7)
    g.sock_in("Saddle", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Stern Style", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Stern Taper", "NodeSocketFloat", 1.0, 0.5, 2.2)
    g.sock_in("Stern Tip", "NodeSocketFloat", 1.0, 0.15, 1.5)
    g.sock_in("Stern Rake", "NodeSocketFloat", 0.05, -0.3, 0.3)
    g.sock_in("Deck Crown", "NodeSocketFloat", 0.0, 0.0, 0.75)
    g.sock_in("Keel Crown", "NodeSocketFloat", 0.0, 0.0, 0.75)
    g.sock_in("Chine 2", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Chine 2 Slope", "NodeSocketFloat", 1.6, 0.3, 3.0)
    g.sock_in("Accent Bands", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Dorsal Stripe", "NodeSocketBool", False)
    g.sock_in("Hue Jitter", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Window Glow", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Deck Markings", "NodeSocketBool", True)
    g.sock_in("Towers", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Tower Levels", "NodeSocketInt", 3, 1, 3)
    g.sock_in("Tower Width", "NodeSocketFloat", 1.0, 0.6, 1.6)
    g.sock_in("Dorsal Fins", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Ventral Fins", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Fin Size", "NodeSocketFloat", 1.0, 0.5, 1.6)
    g.sock_in("Prow Pods", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Prow Pod Length", "NodeSocketFloat", 1.0, 0.5, 1.8)
    g.sock_in("Nacelles", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Nacelle Position", "NodeSocketFloat", 0.30, 0.15, 0.75)
    g.sock_in("Nacelle Standoff", "NodeSocketFloat", 0.18, 0.05, 0.5)
    g.sock_in("Nacelle Scale", "NodeSocketFloat", 1.0, 0.6, 1.6)
    g.sock_in("Bow Mouth", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Overbite", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Hangars", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hangar Size", "NodeSocketFloat", 1.0, 0.5, 1.5)
    g.sock_in("Deck Trench", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Hull Form", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hull Spacing", "NodeSocketFloat", 0.75, 0.55, 1.1)
    g.sock_in("Module Scale", "NodeSocketFloat", 0.45, 0.3, 0.6)
    g.sock_in("Bridge Blocks", "NodeSocketInt", 2, 1, 3)
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

    is_cr = int_eq(group_in(g, "Class"), 1)
    L = g.math("MULTIPLY", fsw(is_cr, 120.0, 250.0),
               g.math("MULTIPLY", group_in(g, "Scale"),
                      group_in(g, "Length Mult")))
    B = g.math("MULTIPLY", fsw(is_cr, 38.0, 80.0),
               g.math("MULTIPLY", group_in(g, "Scale"),
                      group_in(g, "Beam Mult")))
    D = g.math("MULTIPLY", fsw(is_cr, 16.0, 30.0),
               g.math("MULTIPLY", group_in(g, "Scale"),
                      group_in(g, "Depth Mult")))
    stations = g.math("ADD", 24.0,
                      g.math("MULTIPLY", group_in(g, "Detail"), 12.0))

    form = group_in(g, "Hull Form")
    is_f1 = int_eq(form, 1)
    is_f2 = int_eq(form, 2)
    B_h = fsw(is_f1, B, g.math("MULTIPLY", B, 0.55))
    dwires = {"Seed": seed, "Class": group_in(g, "Class"),
              "Length": L, "Beam": B_h, "Depth": D, "Stations": stations}
    for _k in ("Towers", "Tower Levels", "Tower Height", "Tower Width",
               "Tower Rake",
               "Faction", "Plateaus", "Plateau Height", "Plateau Width",
               "Chine", "Chine Slope", "Bow Wedge", "Stern Block",
               "Nose Style", "Nose Taper", "Nose Tip", "Mass Bias",
               "Waist", "Waist Position", "Saddle", "Stern Style",
               "Stern Taper", "Stern Tip", "Stern Rake", "Deck Crown",
               "Keel Crown", "Chine 2", "Chine 2 Slope", "Keel",
               "Nozzles", "Panel Density", "Patchwork", "Accent Fields",
               "Blisters", "Light Rows", "Accent Bands", "Dorsal Stripe",
               "Hue Jitter", "Window Glow", "Deck Markings", "Thrusters",
               "Bow Mouth", "Hangars", "Hangar Size", "Deck Trench"):
        dwires[_k] = group_in(g, _k)
    dressed = gcall(g, parts["dressed"], wires=dwires)
    dgeo = out_sock(dressed, "Geometry")

    # ---- faction materials for pods/fixtures (the dressed hull carries
    # its own copy inside) ------------------------------------------------
    is_oxr = int_eq(group_in(g, "Faction"), 1)
    is_nyx = int_eq(group_in(g, "Faction"), 2)

    def mat3(role):
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
        return out_sock(m2, "Output", "MATERIAL")

    # ---- hull-form assembly ---------------------------------------------
    ys = g.math("MULTIPLY", group_in(g, "Hull Spacing"),
                g.math("MULTIPLY", B, 0.5))
    cat = g.n("GeometryNodeJoinGeometry")
    for sgn in (1.0, -1.0):
        tcopy = g.n("GeometryNodeTransform")
        g.l(dgeo, tcopy.inputs[0])
        tvv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", ys, sgn), tvv.inputs[1])
        g.l(tvv.outputs[0], in_sock(tcopy, "Translation"))
        g.l(out_sock(tcopy, "Geometry"), cat.inputs[0])
    for bi, bxf in enumerate((-0.15, 0.15, 0.0)):
        brd = _prim(g, "cube",
                    (g.math("MULTIPLY", L, 0.10),
                     g.math("ADD", g.math("MULTIPLY", ys, 2.0),
                            g.math("MULTIPLY", B_h, 0.30)),
                     g.math("MULTIPLY", D, 0.22)), None, None, None)
        smb = g.n("GeometryNodeSetMaterial")
        g.l(brd, smb.inputs[0])
        g.l(mat3("hull"), in_sock(smb, "Material"))
        mvb2 = g.n("GeometryNodeTransform")
        g.l(out_sock(smb, "Geometry"), mvb2.inputs[0])
        tvb2 = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", L, bxf), tvb2.inputs[0])
        g.l(g.math("MULTIPLY", D, 0.05), tvb2.inputs[2])
        g.l(tvb2.outputs[0], in_sock(mvb2, "Translation"))
        bsw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(int_gt(group_in(g, "Bridge Blocks"), bi),
            in_sock(bsw2, "Switch"))
        g.l(out_sock(mvb2, "Geometry"), in_sock(bsw2, "True", "GEOMETRY"))
        g.l(out_sock(bsw2, "Output", "GEOMETRY"), cat.inputs[0])
    # asymmetric: main hull + one scaled side module + pylon block
    mscl = group_in(g, "Module Scale")
    side = g.math("SUBTRACT",
                  g.math("MULTIPLY",
                         g.math("GREATER_THAN",
                                g.rand_float(0.0, 1.0, None,
                                             g.math("ADD", seed, 97.0)),
                                0.5), 2.0), 1.0)
    y_mod = g.math("MULTIPLY",
                   g.math("MULTIPLY", B,
                          g.math("ADD", 0.5,
                                 g.math("MULTIPLY", mscl, 0.45))), side)
    asym = g.n("GeometryNodeJoinGeometry")
    g.l(dgeo, asym.inputs[0])
    msc3 = g.n("GeometryNodeTransform")
    g.l(dgeo, msc3.inputs[0])
    scv = g.n("ShaderNodeCombineXYZ")
    for _i in range(3):
        g.l(mscl, scv.inputs[_i])
    g.l(scv.outputs[0], in_sock(msc3, "Scale"))
    tvm = g.n("ShaderNodeCombineXYZ")
    g.l(y_mod, tvm.inputs[1])
    g.l(tvm.outputs[0], in_sock(msc3, "Translation"))
    g.l(out_sock(msc3, "Geometry"), asym.inputs[0])
    pylon2 = _prim(g, "cube",
                   (g.math("MULTIPLY", L, 0.35),
                    g.math("MULTIPLY", B, 0.55),
                    g.math("MULTIPLY", D, 0.16)), None, None, None)
    smp2 = g.n("GeometryNodeSetMaterial")
    g.l(pylon2, smp2.inputs[0])
    g.l(mat3("hull"), in_sock(smp2, "Material"))
    mvp2 = g.n("GeometryNodeTransform")
    g.l(out_sock(smp2, "Geometry"), mvp2.inputs[0])
    tvp2 = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", y_mod, 0.5), tvp2.inputs[1])
    g.l(tvp2.outputs[0], in_sock(mvp2, "Translation"))
    g.l(out_sock(mvp2, "Geometry"), asym.inputs[0])

    wsel1 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(is_f1, in_sock(wsel1, "Switch"))
    g.l(dgeo, in_sock(wsel1, "False", "GEOMETRY"))
    g.l(out_sock(cat, "Geometry"), in_sock(wsel1, "True", "GEOMETRY"))
    wsel2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(is_f2, in_sock(wsel2, "Switch"))
    g.l(out_sock(wsel1, "Output", "GEOMETRY"),
        in_sock(wsel2, "False", "GEOMETRY"))
    g.l(out_sock(asym, "Geometry"), in_sock(wsel2, "True", "GEOMETRY"))
    welded = out_sock(wsel2, "Output", "GEOMETRY")

    # fixture/pod anchor frame: the +y hull for catamarans, else centre
    B_a = fsw(is_f1, B, B_h)
    y_off = fsw(is_f1, 0.0, ys)
    out = g.n("GeometryNodeJoinGeometry")
    g.l(welded, out.inputs[0])

    # ---- instanced fixtures: deck raycast + profile-sampled pairs ------
    def deck_place(xf, yf, part_geo, gate, down=True, upright=False,
                   sink=None, rot=None):
        rc = g.n("GeometryNodeRaycast")
        g.l(welded, in_sock(rc, "Target Geometry"))
        srcv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", L, xf), srcv.inputs[0])
        g.l(g.math("ADD", y_off, g.math("MULTIPLY", B_a, yf)),
            srcv.inputs[1])
        g.l(g.math("MULTIPLY", D, 2.0 if down else -2.0), srcv.inputs[2])
        g.l(srcv.outputs[0], in_sock(rc, "Source Position"))
        in_sock(rc, "Ray Direction").default_value = \
            (0.0, 0.0, -1.0 if down else 1.0)
        g.l(g.math("MULTIPLY", D, 4.0), in_sock(rc, "Ray Length"))
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
        "Length": g.math("MULTIPLY", L, 0.085),
        "Width": g.math("MULTIPLY", B, 0.055)}, values={"Slats": 10})
    for i, (xf, yf) in enumerate(((-0.06, 0.20), (0.08, -0.20),
                                  (-0.20, 0.22), (0.16, 0.24))):
        deck_place(xf, yf, out_sock(grate, "Geometry"),
                   int_gt(group_in(g, "Vents"), i))
    rad0 = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", D, 0.35)}, values={"Variant": 0})
    rad1 = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", D, 0.28)}, values={"Variant": 1})
    deck_place(-0.02, -0.12, out_sock(rad0, "Geometry"),
               int_gt(group_in(g, "Radomes"), 0))
    deck_place(0.20, -0.08, out_sock(rad1, "Geometry"),
               int_gt(group_in(g, "Radomes"), 1))
    mast = gcall(g, parts["mast"], wires={
        "Size": g.math("MULTIPLY", D, 0.40)})
    for i, (xf, yf) in enumerate(((-0.30, 0.10), (-0.36, -0.14),
                                  (0.02, 0.16))):
        deck_place(xf, yf, out_sock(mast, "Geometry"),
                   int_gt(group_in(g, "Antennas"), i))
    chev = gcall(g, parts["chevron"], wires={
        "Size": g.math("MULTIPLY", B, 0.28)})
    deck_place(0.30, 0.0, out_sock(chev, "Geometry"),
               int_gt(group_in(g, "Decals"), 0))
    hnum = gcall(g, parts["number"], wires={
        "Size": g.math("MULTIPLY", B, 0.16),
        "Value": g.rand_float(0.0, 99.9, None,
                              g.math("ADD", seed, 77.0))})
    deck_place(0.15, 0.0, out_sock(hnum, "Geometry"),
               int_gt(group_in(g, "Decals"), 1))

    # ---- attached silhouette: towers, fins, tines, nacelles ------------
    prof = parts["profile"]
    finp = gcall(g, parts["fin"], wires={
        "Size": g.math("MULTIPLY", g.math("MULTIPLY", D, 0.60),
                       group_in(g, "Fin Size")),
        "Hull Mat": mat3("hull"), "Accent Mat": mat3("accent")})
    for i, xf in enumerate((-0.33, -0.43)):
        deck_place(xf, 0.0, out_sock(finp, "Geometry"),
                   int_gt(group_in(g, "Dorsal Fins"), i), upright=True,
                   sink=g.math("MULTIPLY", D, 0.05))
    deck_place(-0.38, 0.0, out_sock(finp, "Geometry"),
               int_gt(group_in(g, "Ventral Fins"), 0), down=False,
               upright=True, sink=g.math("MULTIPLY", D, 0.05),
               rot=(3.14159265, 0.0, 0.0))

    # prow tines: profile-anchored at the bow root, generous embed
    ppl = group_in(g, "Prow Pod Length")
    pp = group_in(g, "Prow Pods")
    t_r = g.math("SUBTRACT", 1.0,
                 g.math("MULTIPLY", group_in(g, "Bow Wedge"), 0.35))
    tp_p = gcall(g, prof, wires={
        "t": t_r, "Seed": seed,
        "Bow Wedge": group_in(g, "Bow Wedge"),
        "Stern Block": group_in(g, "Stern Block"),
        "Class": group_in(g, "Class"),
        "Nose Style": group_in(g, "Nose Style"),
        "Nose Taper": group_in(g, "Nose Taper"),
        "Nose Tip": group_in(g, "Nose Tip"),
        "Mass Bias": group_in(g, "Mass Bias"),
        "Waist": group_in(g, "Waist"),
        "Waist Position": group_in(g, "Waist Position"),
        "Saddle": group_in(g, "Saddle"),
        "Stern Style": group_in(g, "Stern Style"),
        "Stern Taper": group_in(g, "Stern Taper"),
        "Stern Tip": group_in(g, "Stern Tip"),
        "Stern Rake": group_in(g, "Stern Rake")})
    Lp = g.math("MULTIPLY",
                g.math("MULTIPLY", group_in(g, "Bow Wedge"), L),
                g.math("MULTIPLY", 0.85, ppl))
    prong = gcall(g, parts["prong"], wires={
        "Length": Lp, "Hull Mat": mat3("hull"),
        "Glow Mat": mat3("drive")})
    px_c = g.math("ADD",
                  g.math("MULTIPLY", L,
                         g.math("SUBTRACT", t_r, 0.5)),
                  g.math("SUBTRACT", g.math("MULTIPLY", Lp, 0.5),
                         g.math("MULTIPLY", L, 0.06)))
    py_f = g.math("MULTIPLY", out_sock(tp_p, "W", "VALUE"),
                  g.math("MULTIPLY", B_a, 0.21))
    pz_f = g.math("MULTIPLY", out_sock(tp_p, "Zc", "VALUE"), D)
    pp_centre = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(int_eq(pp, 1), pp_centre.inputs[0])
    g.l(int_eq(pp, 3), pp_centre.inputs[1])
    for yfac, gate in ((0.0, pp_centre.outputs[0]),
                       (1.0, int_gt(pp, 1)), (-1.0, int_gt(pp, 1))):
        mvp = g.n("GeometryNodeTransform")
        g.l(out_sock(prong, "Geometry"), mvp.inputs[0])
        tvp = g.n("ShaderNodeCombineXYZ")
        g.l(px_c, tvp.inputs[0])
        g.l(g.math("ADD", y_off, g.math("MULTIPLY", py_f, yfac)),
            tvp.inputs[1])
        g.l(pz_f, tvp.inputs[2])
        g.l(tvp.outputs[0], in_sock(mvp, "Translation"))
        psw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(gate, in_sock(psw, "Switch"))
        g.l(out_sock(mvp, "Geometry"), in_sock(psw, "True", "GEOMETRY"))
        g.l(out_sock(psw, "Output", "GEOMETRY"), out.inputs[0])

    # nacelles: pod + composer-built pylon (it knows the standoff)
    nsc = g.math("MULTIPLY", g.math("MULTIPLY", L, 0.10),
                 group_in(g, "Nacelle Scale"))
    nac = gcall(g, parts["nacelle"], wires={
        "Size": nsc, "Hull Mat": mat3("hull"),
        "Glow Mat": mat3("drive")}, values={})
    in_sock(nac, "Dark Mat").default_value = mats["dark"]
    for i in range(2):
        tn = g.math("ADD", group_in(g, "Nacelle Position"), 0.22 * i)
        tp_n = gcall(g, prof, wires={
            "t": tn, "Seed": seed,
            "Bow Wedge": group_in(g, "Bow Wedge"),
            "Stern Block": group_in(g, "Stern Block"),
            "Class": group_in(g, "Class"),
            "Nose Style": group_in(g, "Nose Style"),
            "Nose Taper": group_in(g, "Nose Taper"),
            "Nose Tip": group_in(g, "Nose Tip"),
            "Mass Bias": group_in(g, "Mass Bias"),
            "Waist": group_in(g, "Waist"),
            "Waist Position": group_in(g, "Waist Position"),
            "Saddle": group_in(g, "Saddle"),
            "Stern Style": group_in(g, "Stern Style"),
            "Stern Taper": group_in(g, "Stern Taper"),
            "Stern Tip": group_in(g, "Stern Tip"),
            "Stern Rake": group_in(g, "Stern Rake")})
        y_h = g.math("MULTIPLY", out_sock(tp_n, "W", "VALUE"),
                     g.math("MULTIPLY", B_a, 0.5))
        y_p = g.math("ADD", y_h,
                     g.math("MULTIPLY", group_in(g, "Nacelle Standoff"),
                            B))
        x_n = g.math("MULTIPLY", L, g.math("SUBTRACT", tn, 0.5))
        z_n = g.math("MULTIPLY", out_sock(tp_n, "Zc", "VALUE"), D)
        gapw = g.math("ADD", g.math("SUBTRACT", y_p, y_h),
                      g.math("MULTIPLY", B, 0.10))
        y_mid = g.math("MULTIPLY", g.math("ADD", y_p, y_h), 0.5)
        gate_n = int_gt(group_in(g, "Nacelles"), i)
        for sgn in (1.0, -1.0):
            mvn = g.n("GeometryNodeTransform")
            g.l(out_sock(nac, "Geometry"), mvn.inputs[0])
            tvn = g.n("ShaderNodeCombineXYZ")
            g.l(x_n, tvn.inputs[0])
            g.l(g.math("ADD", y_off, g.math("MULTIPLY", y_p, sgn)),
                tvn.inputs[1])
            g.l(z_n, tvn.inputs[2])
            g.l(tvn.outputs[0], in_sock(mvn, "Translation"))
            pyl = _prim(g, "cube",
                        (g.math("MULTIPLY", nsc, 0.30), gapw,
                         g.math("MULTIPLY", nsc, 0.09)), None, None,
                        None)
            smp = g.n("GeometryNodeSetMaterial")
            g.l(pyl, smp.inputs[0])
            g.l(mat3("hull"), in_sock(smp, "Material"))
            mvpy = g.n("GeometryNodeTransform")
            g.l(out_sock(smp, "Geometry"), mvpy.inputs[0])
            tvpy = g.n("ShaderNodeCombineXYZ")
            g.l(x_n, tvpy.inputs[0])
            g.l(g.math("ADD", y_off,
                       g.math("MULTIPLY", y_mid, sgn)),
                tvpy.inputs[1])
            g.l(z_n, tvpy.inputs[2])
            g.l(tvpy.outputs[0], in_sock(mvpy, "Translation"))
            jn = g.n("GeometryNodeJoinGeometry")
            g.l(out_sock(mvn, "Geometry"), jn.inputs[0])
            g.l(out_sock(mvpy, "Geometry"), jn.inputs[0])
            nsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
            g.l(gate_n, in_sock(nsw, "Switch"))
            g.l(out_sock(jn, "Geometry"), in_sock(nsw, "True", "GEOMETRY"))
            g.l(out_sock(nsw, "Output", "GEOMETRY"), out.inputs[0])

    # profile-sampled mirrored pairs: sponsons + bow sensor booms
    prof = parts["profile"]
    spon = gcall(g, parts["sponson"], wires={
        "Size": g.math("MULTIPLY", L, 0.11)})
    for i, tpos in enumerate((0.38, 0.58, 0.48)):
        tp_s = gcall(g, prof, wires={
            "Seed": seed, "Bow Wedge": group_in(g, "Bow Wedge"),
            "Stern Block": group_in(g, "Stern Block"),
            "Class": group_in(g, "Class"),
            "Nose Style": group_in(g, "Nose Style"),
            "Nose Taper": group_in(g, "Nose Taper"),
            "Nose Tip": group_in(g, "Nose Tip"),
            "Mass Bias": group_in(g, "Mass Bias"),
            "Waist": group_in(g, "Waist"),
            "Waist Position": group_in(g, "Waist Position"),
            "Saddle": group_in(g, "Saddle"),
            "Stern Style": group_in(g, "Stern Style"),
            "Stern Taper": group_in(g, "Stern Taper"),
            "Stern Tip": group_in(g, "Stern Tip"),
            "Stern Rake": group_in(g, "Stern Rake")}, values={"t": tpos})
        # embed INTO the flank (the chine narrows the hull below the
        # profile half-beam — a pod at W*B/2 floats)
        yw = g.math("MULTIPLY", out_sock(tp_s, "W", "VALUE"),
                    g.math("MULTIPLY", B_a, 0.44))
        zw = g.math("MULTIPLY", out_sock(tp_s, "Zc", "VALUE"), D)
        for sgn in (1.0, -1.0):
            mv = g.n("GeometryNodeTransform")
            g.l(out_sock(spon, "Geometry"), mv.inputs[0])
            tv3 = g.n("ShaderNodeCombineXYZ")
            g.l(g.math("MULTIPLY", L, tpos - 0.5), tv3.inputs[0])
            g.l(g.math("ADD", y_off, g.math("MULTIPLY", yw, sgn)),
                tv3.inputs[1])
            g.l(zw, tv3.inputs[2])
            g.l(tv3.outputs[0], in_sock(mv, "Translation"))
            ssw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
            g.l(int_gt(group_in(g, "Sponsons"), i), in_sock(ssw, "Switch"))
            g.l(out_sock(mv, "Geometry"), in_sock(ssw, "True", "GEOMETRY"))
            g.l(out_sock(ssw, "Output", "GEOMETRY"), out.inputs[0])
    boomp = gcall(g, parts["boom"], wires={
        "Size": g.math("MULTIPLY", L, 0.055)})
    tp_b = gcall(g, prof, wires={
        "Seed": seed, "Bow Wedge": group_in(g, "Bow Wedge"),
        "Stern Block": group_in(g, "Stern Block"),
        "Class": group_in(g, "Class"),
        "Nose Style": group_in(g, "Nose Style"),
        "Nose Taper": group_in(g, "Nose Taper"),
        "Nose Tip": group_in(g, "Nose Tip"),
        "Mass Bias": group_in(g, "Mass Bias"),
        "Waist": group_in(g, "Waist"),
        "Waist Position": group_in(g, "Waist Position"),
        "Saddle": group_in(g, "Saddle"),
        "Stern Style": group_in(g, "Stern Style"),
        "Stern Taper": group_in(g, "Stern Taper"),
        "Stern Tip": group_in(g, "Stern Tip"),
        "Stern Rake": group_in(g, "Stern Rake")}, values={"t": 0.955})
    yb = g.math("MULTIPLY", out_sock(tp_b, "W", "VALUE"),
                g.math("MULTIPLY", B_a, 0.30))
    zb = g.math("MULTIPLY", out_sock(tp_b, "Zc", "VALUE"), D)
    for sgn in (1.0, -1.0):
        mvb = g.n("GeometryNodeTransform")
        g.l(out_sock(boomp, "Geometry"), mvb.inputs[0])
        tv4 = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", L, 0.455), tv4.inputs[0])
        g.l(g.math("ADD", y_off, g.math("MULTIPLY", yb, sgn)),
            tv4.inputs[1])
        g.l(zb, tv4.inputs[2])
        g.l(tv4.outputs[0], in_sock(mvb, "Translation"))
        bsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(group_in(g, "Booms"), in_sock(bsw, "Switch"))
        g.l(out_sock(mvb, "Geometry"), in_sock(bsw, "True", "GEOMETRY"))
        g.l(out_sock(bsw, "Output", "GEOMETRY"), out.inputs[0])

    # overbite: upper lip plate overhanging the bow (uses the boom
    # profile sample at t=0.955 for width/height anchoring)
    ob_k = group_in(g, "Overbite")
    lipL = g.math("MULTIPLY", L,
                  g.math("ADD", 0.04,
                         g.math("MULTIPLY", ob_k, 0.06)))
    lip = _prim(g, "cube",
                (lipL,
                 g.math("MULTIPLY",
                        out_sock(tp_b, "W", "VALUE"),
                        g.math("MULTIPLY", B, 0.55)),
                 g.math("MULTIPLY", D, 0.035)), None, None, None)
    sml = g.n("GeometryNodeSetMaterial")
    g.l(lip, sml.inputs[0])
    g.l(mat3("hull"), in_sock(sml, "Material"))
    mvl = g.n("GeometryNodeTransform")
    g.l(out_sock(sml, "Geometry"), mvl.inputs[0])
    tvl = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("ADD", g.math("MULTIPLY", L, 0.44),
               g.math("MULTIPLY", lipL, 0.5)), tvl.inputs[0])
    g.l(y_off, tvl.inputs[1])
    g.l(g.math("ADD",
               g.math("MULTIPLY", out_sock(tp_b, "Zc", "VALUE"), D),
               g.math("MULTIPLY",
                      g.math("MULTIPLY", out_sock(tp_b, "H", "VALUE"),
                             D), 0.30)), tvl.inputs[2])
    g.l(tvl.outputs[0], in_sock(mvl, "Translation"))
    lsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(g.math("GREATER_THAN", ob_k, 0.02), in_sock(lsw, "Switch"))
    g.l(out_sock(mvl, "Geometry"), in_sock(lsw, "True", "GEOMETRY"))
    g.l(out_sock(lsw, "Output", "GEOMETRY"), out.inputs[0])

    final = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(out, "Geometry"), final.inputs[0])
    return g.finish(out_sock(final, "Geometry"))


# ---------------------------------------------------------------- main -----

def main():
    outp = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    hg = fi_deps(DEP_WANT)
    mats = build_fleet_materials()
    parts = {"profile": build_fleet_profile()}
    parts["grate"] = build_vent_grate(mats)
    parts["radome"] = build_radome(mats)
    parts["mast"] = build_antenna_mast(mats)
    parts["sponson"] = build_sponson(mats)
    parts["boom"] = build_sensor_boom(mats)
    parts["chevron"] = build_chevron(mats)
    parts["number"] = build_hull_number(mats)
    parts["fin"] = build_fin(mats)
    parts["prong"] = build_prong(mats)
    parts["nacelle"] = build_nacelle(mats)
    parts["hull"] = build_fleet_hull(parts["profile"])
    parts["dressed"] = build_fleet_dressed(mats, hg, parts)
    parts["ship"] = build_fleet_ship(mats, hg, parts)
    contract = {}
    for ng in parts.values():
        contract[ng.name] = [
            {"name": it.name, "in_out": it.in_out,
             "type": getattr(it, "socket_type", "?"),
             "identifier": it.identifier}
            for it in ng.interface.items_tree
            if it.item_type == "SOCKET"]
    with open(os.path.join(os.path.dirname(outp), "fleet_contract.json"),
              "w") as f:
        json.dump(contract, f, indent=1, sort_keys=True)
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    print(f"build_fleetkit: OK -> {outp} ({len(parts)} groups + "
          f"{len(hg)} native deps)")


main()
