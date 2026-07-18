#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# build_buildingkit.py -- FI_BuildingKit.blend: the FI BUILDING generator —
# planetside cities in the fleet register (grounded siblings of the
# stations: setback towers, refinery works, courtyard hab slabs,
# spaceport terminals).
#
#   blender -b --python build_buildingkit.py -- [--out FI_BuildingKit.blend]
#
# HOUSE LANGUAGE:
#   - buildings are the STATION CORE STOOD ON THE GROUND: same profile /
#     core / dress trio imported from build_stationkit and renamed; a
#     rigid +H/2 lift grounds every body at z=0 (all region logic tests
#     stale fi_u, never live Z, so grounding is free)
#   - PERFORMANCE IS A KNOB: the LOD input (0 full dress / 1 light /
#     2 shell) value-maps loft resolution, panel density, relief and
#     fixture counts — real procedural low-poly, budget-checked by the
#     selftest and consumed by bake_ship.py --lods
#   - every form sits on a plinth apron; connective tissue (pipe runs,
#     truss racks) over-reaches 5% into the volumes it joins
#   - station materials VERBATIM (FI_Station_* datablocks) so cities
#     colour-match their orbitals; building-only roles added on top

import bpy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fi_gn_lib import (G, TAU, boss, gcall, group_in, in_sock,  # noqa
                       out_sock, mat, _prim, fi_deps)
import build_fleetkit as fleet      # __main__-guarded fixture builders
import build_stationkit as station  # __main__-guarded core/dress/etc.

HERE = os.path.dirname(os.path.abspath(__file__))

DEP_WANT = ["Mesh Face Divider"]


def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = os.path.join(HERE, "FI_BuildingKit.blend")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    return out


# ---------------------------------------------------------- materials ------
# Station materials verbatim (colour-match + dedupe when a city and its
# orbital are linked into one scene) plus building-only ground roles.

def build_building_materials():
    m = station.build_station_materials()
    m["asphalt"] = mat("FI_Building_Asphalt", (0.045, 0.045, 0.05),
                       0.95, 0.02)
    m["hazardstripe"] = mat("FI_Building_Hazard", (0.62, 0.51, 0.13),
                            0.6, 0.1)
    m["stackring"] = mat("FI_Building_StackRing", (0.06, 0.06, 0.07),
                         0.7, 0.3)
    return m


# --------------------------------------------------- building components ---

def build_building_plinth(mats):
    """Ground apron/foundation under every form: sidewalk lip ring,
    entrance recess with doorway light strip, step boxes, hazard-stripe
    edge bands. Spans z in [0, Height]."""
    g = G("FI_BuildingPlinth")
    g.sock_in("Width", "NodeSocketFloat", 40.0, 4.0, 800.0)
    g.sock_in("Depth", "NodeSocketFloat", 40.0, 4.0, 800.0)
    g.sock_in("Height", "NodeSocketFloat", 3.0, 1.0, 8.0)
    g.sock_in("Entrances", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Entrance Size", "NodeSocketFloat", 1.0, 0.5, 1.6)
    g.sock_out("Geometry", "NodeSocketGeometry")
    W = group_in(g, "Width")
    Dp = group_in(g, "Depth")
    Ht = group_in(g, "Height")
    j = g.n("GeometryNodeJoinGeometry")

    cube = g.n("GeometryNodeMeshCube")
    in_sock(cube, "Size").default_value = (1.0, 1.0, 1.0)
    in_sock(cube, "Vertices X").default_value = 5
    in_sock(cube, "Vertices Y").default_value = 5
    in_sock(cube, "Vertices Z").default_value = 2
    pos = g.n("GeometryNodeInputPosition")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos, "Position"), sep.inputs[0])
    cmb = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", sep.outputs[0], W), cmb.inputs[0])
    g.l(g.math("MULTIPLY", sep.outputs[1], Dp), cmb.inputs[1])
    g.l(g.math("MULTIPLY", g.math("ADD", sep.outputs[2], 0.5), Ht),
        cmb.inputs[2])
    sp = g.n("GeometryNodeSetPosition")
    g.l(out_sock(cube, "Mesh"), sp.inputs[0])
    g.l(cmb.outputs[0], in_sock(sp, "Position"))
    smb = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(sp, "Geometry"), smb.inputs[0])
    in_sock(smb, "Material").default_value = mats["asphalt"]
    geo = out_sock(smb, "Geometry")

    # sidewalk lip: raise the outer ring of the top grid
    nrm = g.n("GeometryNodeInputNormal")
    ns = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(nrm, "Normal"), ns.inputs[0])
    top = g.math("GREATER_THAN", ns.outputs[2], 0.5)
    pos2 = g.n("GeometryNodeInputPosition")
    ps2 = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(pos2, "Position"), ps2.inputs[0])
    inner = g.math("MULTIPLY",
                   g.math("LESS_THAN", g.math("ABSOLUTE", ps2.outputs[0]),
                          g.math("MULTIPLY", W, 0.30)),
                   g.math("LESS_THAN", g.math("ABSOLUTE", ps2.outputs[1]),
                          g.math("MULTIPLY", Dp, 0.30)))
    lip_sel = g.math("MULTIPLY", top,
                     g.math("SUBTRACT", 1.0, inner))
    geo, lip_top, _ = boss(g, geo, lip_sel,
                           g.math("MULTIPLY", Ht, 0.18), 0.96)
    smt = g.n("GeometryNodeSetMaterial")
    g.l(geo, smt.inputs[0])
    g.l(lip_top, in_sock(smt, "Selection"))
    in_sock(smt, "Material").default_value = mats["metal"]
    geo = out_sock(smt, "Geometry")

    # entrance recesses on the +/-X walls
    for i, sx in enumerate((1.0, -1.0)):
        nrm_e = g.n("GeometryNodeInputNormal")
        nse = g.n("ShaderNodeSeparateXYZ")
        g.l(out_sock(nrm_e, "Normal"), nse.inputs[0])
        facing = (g.math("GREATER_THAN", nse.outputs[0], 0.5) if sx > 0
                  else g.math("LESS_THAN", nse.outputs[0], -0.5))
        pos_e = g.n("GeometryNodeInputPosition")
        pse = g.n("ShaderNodeSeparateXYZ")
        g.l(out_sock(pos_e, "Position"), pse.inputs[0])
        ew = g.math("MULTIPLY",
                    g.math("MULTIPLY", Dp, 0.14),
                    group_in(g, "Entrance Size"))
        e_sel = g.math("MULTIPLY",
                       g.math("MULTIPLY", facing,
                              g.math("LESS_THAN",
                                     g.math("ABSOLUTE", pse.outputs[1]),
                                     ew)),
                       g.math("GREATER_THAN",
                              group_in(g, "Entrances"), float(i) + 0.5))
        geo, e_top, e_side = boss(g, geo, e_sel,
                                  g.math("MULTIPLY", W, -0.05), 0.85)
        sme = g.n("GeometryNodeSetMaterial")
        g.l(geo, sme.inputs[0])
        g.l(e_side, in_sock(sme, "Selection"))
        in_sock(sme, "Material").default_value = mats["dark"]
        smg = g.n("GeometryNodeSetMaterial")
        g.l(out_sock(sme, "Geometry"), smg.inputs[0])
        g.l(e_top, in_sock(smg, "Selection"))
        in_sock(smg, "Material").default_value = mats["padlight"]
        geo = out_sock(smg, "Geometry")
    g.l(geo, j.inputs[0])

    # step boxes + hazard-stripe edge bands
    for sx in (1.0, -1.0):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", W, 0.06),
                              g.math("MULTIPLY", Dp, 0.20),
                              g.math("MULTIPLY", Ht, 0.35)), None,
                  (g.math("MULTIPLY", g.math("MULTIPLY", W, 0.49), sx),
                   0.0, g.math("MULTIPLY", Ht, 0.175)),
                  mats["metal"]), j.inputs[0])
        g.l(_prim(g, "cube", (g.math("MULTIPLY", W, 1.0),
                              g.math("MULTIPLY", Dp, 0.02),
                              g.math("MULTIPLY", Ht, 0.12)), None,
                  (0.0, g.math("MULTIPLY", g.math("MULTIPLY", Dp, 0.505),
                               sx),
                   g.math("MULTIPLY", Ht, 1.0)),
                  mats["hazardstripe"]), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_stack(mats):
    """Industrial chimney: tapered cone + base drum + seeded collar
    rings + beacon tip. Grounded (cone spans [0, Height])."""
    g = G("FI_Stack")
    g.sock_in("Height", "NodeSocketFloat", 40.0, 4.0, 400.0)
    g.sock_in("Radius", "NodeSocketFloat", 2.5, 0.3, 40.0)
    g.sock_in("Collars", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Taper", "NodeSocketFloat", 0.62, 0.4, 1.0)
    g.sock_in("Verts", "NodeSocketInt", 10, 6, 16)
    g.sock_in("Beacon", "NodeSocketBool", True)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    Ht = group_in(g, "Height")
    R = group_in(g, "Radius")
    tp = group_in(g, "Taper")
    seed = group_in(g, "Seed")
    sverts = group_in(g, "Verts")
    j = g.n("GeometryNodeJoinGeometry")
    # GN cone spans [0, depth] from its base (lib lesson) — grounded
    g.l(_prim(g, "cone", (g.math("MULTIPLY", R, tp), R, Ht), None, None,
              mats["metal"], verts=sverts), j.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 1.35),
                         g.math("MULTIPLY", Ht, 0.08)), None,
              (0.0, 0.0, g.math("MULTIPLY", Ht, 0.04)), mats["dark"],
              verts=sverts), j.inputs[0])
    for i in range(3):
        hc = g.rand_float(0.25, 0.85, None,
                          g.math("ADD", seed, 7.0 + i * 5.0))
        rc = g.math("MULTIPLY",
                    g.math("MULTIPLY", R, 1.16),
                    g.math("SUBTRACT", 1.0,
                           g.math("MULTIPLY",
                                  g.math("SUBTRACT", 1.0, tp), hc)))
        col = _prim(g, "cyl", (rc, g.math("MULTIPLY", Ht, 0.03)), None,
                    None, mats["stackring"], verts=sverts)
        mv = g.n("GeometryNodeTransform")
        g.l(col, mv.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", hc, Ht), tv.inputs[2])
        g.l(tv.outputs[0], in_sock(mv, "Translation"))
        csw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        cg = g.n("FunctionNodeCompare", data_type="INT",
                 operation="GREATER_THAN")
        g.l(group_in(g, "Collars"), in_sock(cg, "A", "INT"))
        in_sock(cg, "B", "INT").default_value = i
        g.l(out_sock(cg, "Result"), in_sock(csw, "Switch"))
        g.l(out_sock(mv, "Geometry"), in_sock(csw, "True", "GEOMETRY"))
        g.l(out_sock(csw, "Output", "GEOMETRY"), j.inputs[0])
    bc = _prim(g, "cube", (g.math("MULTIPLY", R, 0.5),
                           g.math("MULTIPLY", R, 0.5),
                           g.math("MULTIPLY", R, 0.5)), None,
               (0.0, 0.0, Ht), mats["beacon"])
    bsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Beacon"), in_sock(bsw, "Switch"))
    g.l(bc, in_sock(bsw, "True", "GEOMETRY"))
    g.l(out_sock(bsw, "Output", "GEOMETRY"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


def build_pipe_run(mats):
    """Pipe rack along +X: per-pipe riser/overhead/riser cylinder trio
    with elbow spheres, H-post supports to the ground. Ends over-reach
    so the composer can bury them in the joined volumes (island rule)."""
    g = G("FI_PipeRun")
    g.sock_in("Length", "NodeSocketFloat", 60.0, 5.0, 600.0)
    g.sock_in("Rise", "NodeSocketFloat", 10.0, 2.0, 120.0)
    g.sock_in("Pipes", "NodeSocketInt", 3, 1, 4)
    g.sock_in("Radius", "NodeSocketFloat", 0.8, 0.1, 8.0)
    g.sock_in("Supports", "NodeSocketInt", 3, 2, 6)
    g.sock_in("Verts", "NodeSocketInt", 6, 6, 8)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    L = group_in(g, "Length")
    rise = group_in(g, "Rise")
    R = group_in(g, "Radius")
    seed = group_in(g, "Seed")
    pverts = group_in(g, "Verts")
    j = g.n("GeometryNodeJoinGeometry")
    for i in range(4):
        py = g.math("MULTIPLY", R,
                    g.math("SUBTRACT", 2.4 * i, 3.6))
        rj = g.math("MULTIPLY", rise,
                    g.rand_float(0.86, 1.0, None,
                                 g.math("ADD", seed, 9.0 + i * 7.0)))
        pipe = g.n("GeometryNodeJoinGeometry")
        for x in (0.0, 1.0):
            xr = g.math("MULTIPLY", L, x)
            g.l(_prim(g, "cyl", (R, rj), None,
                      (xr, py, g.math("MULTIPLY", rj, 0.5)),
                      mats["metal"], verts=pverts), pipe.inputs[0])
            g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, 1.25),), None,
                      (xr, py, rj), mats["metal"], verts=pverts),
                pipe.inputs[0])
        over = _prim(g, "cyl", (R, g.math("MULTIPLY", L, 1.02)),
                     (0.0, 1.5707963, 0.0),
                     (g.math("MULTIPLY", L, 0.5), py, rj),
                     mats["metal"], verts=pverts)
        g.l(over, pipe.inputs[0])
        psw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        pg = g.n("FunctionNodeCompare", data_type="INT",
                 operation="GREATER_THAN")
        g.l(group_in(g, "Pipes"), in_sock(pg, "A", "INT"))
        in_sock(pg, "B", "INT").default_value = i
        g.l(out_sock(pg, "Result"), in_sock(psw, "Switch"))
        g.l(out_sock(pipe, "Geometry"), in_sock(psw, "True", "GEOMETRY"))
        g.l(out_sock(psw, "Output", "GEOMETRY"), j.inputs[0])
    # H-post supports under the overhead span
    line = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Supports"), in_sock(line, "Count"))
    sv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", L, 0.15), sv.inputs[0])
    g.l(sv.outputs[0], in_sock(line, "Start Location"))
    ov = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("DIVIDE", g.math("MULTIPLY", L, 0.7),
               g.math("MAXIMUM",
                      g.math("SUBTRACT", group_in(g, "Supports"), 1.0),
                      1.0)), ov.inputs[0])
    g.l(ov.outputs[0], in_sock(line, "Offset"))
    post = g.n("GeometryNodeJoinGeometry")
    for sy in (1.0, -1.0):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", R, 0.6),
                              g.math("MULTIPLY", R, 0.6), rise), None,
                  (0.0, g.math("MULTIPLY", g.math("MULTIPLY", R, 4.6),
                               sy),
                   g.math("MULTIPLY", rise, 0.5)), mats["dark"]),
            post.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", R, 0.6),
                          g.math("MULTIPLY", R, 10.4),
                          g.math("MULTIPLY", R, 0.6)), None,
              (0.0, 0.0, g.math("MULTIPLY", rise, 0.92)), mats["dark"]),
        post.inputs[0])
    iop = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(line, "Mesh"), iop.inputs[0])
    g.l(out_sock(post, "Geometry"), in_sock(iop, "Instance"))
    rl = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(iop, "Instances"), rl.inputs[0])
    g.l(out_sock(rl, "Geometry"), j.inputs[0])
    return g.finish(out_sock(j, "Geometry"))


# ----------------------------------------------------------- FI_Building ---

def build_building(mats, hg, parts):
    """Top-level building. Form picks the archetype (0 tower block /
    1 industrial works / 2 hab slab / 3 spaceport terminal), assembled
    INLINE behind a lazy Index Switch (house pattern). The LOD input
    (0 full / 1 light / 2 shell) value-maps loft resolution, panel
    density, relief and fixture counts once, consumed by every branch —
    real parametric low-poly for city instancing."""
    g = G("FI_Building")
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Form", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Class", "NodeSocketInt", 0, 0, 1)
    g.sock_in("Faction", "NodeSocketInt", 0, 0, 3)
    g.sock_in("LOD", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Detail", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Scale", "NodeSocketFloat", 1.0, 0.3, 4.0)
    g.sock_in("Height Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Footprint Mult", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Footprint Aspect", "NodeSocketFloat", 1.0, 0.5, 1.0)
    g.sock_in("Silhouette Style", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Tiers", "NodeSocketInt", 4, 2, 7)
    g.sock_in("Tier Jitter", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Taper Top", "NodeSocketFloat", 0.25, 0.0, 1.0)
    g.sock_in("Taper Bottom", "NodeSocketFloat", 0.1, 0.0, 1.0)
    g.sock_in("Bulge", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Bulge Position", "NodeSocketFloat", 0.55, 0.2, 0.8)
    g.sock_in("Waist", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Skyline", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Corner Cut", "NodeSocketFloat", 0.35, 0.0, 1.0)
    g.sock_in("Corner Cut Slope", "NodeSocketFloat", 1.0, 0.3, 3.0)
    g.sock_in("Base Flare", "NodeSocketFloat", 0.3, 0.0, 1.0)
    g.sock_in("Ledges", "NodeSocketInt", 2, 0, 3)
    g.sock_in("Ledge Depth", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Top Plateaus", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Plateau Height", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Towers Up", "NodeSocketInt", 1, 0, 3)
    g.sock_in("Tower Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Tower Rake", "NodeSocketFloat", 0.1, 0.0, 1.0)
    g.sock_in("Entrances", "NodeSocketInt", 1, 0, 2)
    g.sock_in("Entrance Size", "NodeSocketFloat", 1.0, 0.5, 1.6)
    g.sock_in("Courtyard", "NodeSocketBool", True)
    g.sock_in("Courtyard Size", "NodeSocketFloat", 0.5, 0.3, 0.7)
    g.sock_in("Helipad", "NodeSocketBool", False)
    g.sock_in("Stacks", "NodeSocketInt", 3, 0, 6)
    g.sock_in("Stack Height", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Pipe Runs", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Tank Clusters", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Tanks Per Cluster", "NodeSocketInt", 4, 1, 7)
    g.sock_in("Tank Scale", "NodeSocketFloat", 1.0, 0.5, 2.0)
    g.sock_in("Pads", "NodeSocketInt", 3, 0, 4)
    g.sock_in("Pad Size", "NodeSocketFloat", 1.0, 0.5, 1.6)
    g.sock_in("Terminal Span", "NodeSocketFloat", 2.0, 1.0, 3.0)
    g.sock_in("Control Tower", "NodeSocketBool", True)
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
    g.sock_in("Window Glow", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("Light Rows", "NodeSocketInt", 2, 0, 6)
    g.sock_in("Deck Markings", "NodeSocketBool", True)
    g.sock_in("Trenches", "NodeSocketInt", 0, 0, 4)
    g.sock_in("Trench Depth", "NodeSocketFloat", 0.4, 0.0, 1.0)
    g.sock_in("Hangars", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Hangar Size", "NodeSocketFloat", 0.8, 0.5, 1.5)
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
        if hasattr(b, "is_linked"):
            g.l(b, in_sock(n, "B", "INT"))
        else:
            in_sock(n, "B", "INT").default_value = b
        return out_sock(n, "Result")

    # ---- LOD value map (the crux): wired ONCE, consumed everywhere ----
    lod = group_in(g, "LOD")
    is_l1 = int_eq(lod, 1)
    is_l2 = int_eq(lod, 2)
    is_l0 = int_eq(lod, 0)

    def lod3(a, b, c):
        return fsw(is_l2, fsw(is_l1, a, b), c)

    # buildings run station-density grids at a fraction of station
    # size, and the dress relief floor (W*H-scaled) passes nearly every
    # panel — so the LOD map cuts the grid, caps density at 2, and
    # overdrives Relief Floor Mult so only the biggest panels relieve.
    # Cols stays 9 at LOD0: selection windows (meridian stripe 0.15)
    # are sized to 0.125-multiple face centres (grid-step lesson).
    det = group_in(g, "Detail")
    levels = g.math("ADD", lod3(12.0, 10.0, 5.0),
                    g.math("MULTIPLY", det, 4.0))
    colsrows = g.math("ADD", lod3(9.0, 7.0, 4.0),
                      g.math("MULTIPLY", det, 2.0))
    pd_eff = g.math("MINIMUM", group_in(g, "Panel Density"),
                    lod3(3.0, 2.0, 1.0))
    # multi-body forms (hab slabs, terminal hall, works block) run one
    # density below the single-body tower — the station arm lesson
    pd_m1 = g.math("MAXIMUM", g.math("SUBTRACT", pd_eff, 1.0), 1.0)
    slab_levels = g.math("ADD", lod3(7.0, 6.0, 5.0),
                         g.math("MULTIPLY", det, 2.0))
    slab_cols = g.math("ADD", lod3(5.0, 5.0, 4.0), det)
    block_levels = g.math("ADD", lod3(10.0, 8.0, 5.0),
                          g.math("MULTIPLY", det, 3.0))
    relief_eff = is_l0
    not_l2 = g.n("FunctionNodeBooleanMath", operation="NOT")
    g.l(is_l2, not_l2.inputs[0])
    fixmul = lod3(1.0, 0.5, 0.0)

    def fix_cnt(name):
        return g.math("FLOOR",
                      g.math("ADD",
                             g.math("MULTIPLY", group_in(g, name), fixmul),
                             0.01))

    pad_verts = g.math("ADD", lod3(8.0, 6.0, 6.0),
                       g.math("MULTIPLY", det, 2.0))
    truss_bays = lod3(6.0, 4.0, 3.0)
    tank_verts = lod3(10.0, 6.0, 6.0)
    stack_verts = lod3(10.0, 6.0, 6.0)
    stack_collars = lod3(2.0, 2.0, 0.0)
    pipe_verts = lod3(6.0, 6.0, 6.0)
    pipes_eff = g.math("FLOOR",
                       g.math("ADD",
                              g.math("MULTIPLY", group_in(g, "Pipe Runs"),
                                     lod3(1.0, 0.5, 0.0)), 0.01))
    beacons_eff = fix_cnt("Beacons")
    tclusters_eff = g.math("MINIMUM", group_in(g, "Tank Clusters"),
                           lod3(4.0, 4.0, 1.0))
    tpc_eff = g.math("MINIMUM", group_in(g, "Tanks Per Cluster"),
                     lod3(7.0, 7.0, 2.0))
    pads_eff = g.math("MINIMUM", group_in(g, "Pads"),
                      lod3(4.0, 4.0, 2.0))
    entr_eff = g.math("FLOOR",
                      g.math("ADD",
                             g.math("MULTIPLY", group_in(g, "Entrances"),
                                    lod3(1.0, 1.0, 0.0)), 0.01))

    # ---- dims (grounded city scale) ----------------------------------
    is_cl = int_eq(group_in(g, "Class"), 1)
    H0 = g.math("MULTIPLY", fsw(is_cl, 120.0, 240.0),
                g.math("MULTIPLY", group_in(g, "Scale"),
                       group_in(g, "Height Mult")))
    W0 = g.math("MULTIPLY", fsw(is_cl, 30.0, 52.0),
                g.math("MULTIPLY", group_in(g, "Scale"),
                       group_in(g, "Footprint Mult")))
    Dp0 = g.math("MULTIPLY", W0, group_in(g, "Footprint Aspect"))
    ph = g.math("MULTIPLY", 3.0, group_in(g, "Scale"))

    SILH = (("Style", "Silhouette Style"), ("Tiers", "Tiers"),
            ("Tier Jitter", "Tier Jitter"), ("Taper Top", "Taper Top"),
            ("Taper Bottom", "Taper Bottom"), ("Bulge", "Bulge"),
            ("Bulge Position", "Bulge Position"), ("Waist", "Waist"),
            ("Skyline", "Skyline"),
            ("Corner Cut", "Corner Cut"),
            ("Corner Cut Slope", "Corner Cut Slope"))
    COREK = ("Base Flare", "Ledges", "Ledge Depth", "Top Plateaus",
             "Plateau Height", "Towers Up", "Tower Height", "Tower Rake")
    PAINTK = ("Patchwork", "Accent Fields", "Accent Bands",
              "Meridian Stripe", "Hue Jitter", "Window Glow",
              "Light Rows", "Deck Markings", "Trenches", "Trench Depth",
              "Hangars", "Hangar Size")

    def core_call(w, dp, h, seed_off=0.0, wires_over=None,
                  values_over=None):
        wires = {"Seed": g.math("ADD", seed, seed_off),
                 "Faction": group_in(g, "Faction"),
                 "Class": group_in(g, "Class"),
                 "Width": w, "Depth": dp, "Height": h,
                 "Levels": levels, "Cols": colsrows, "Rows": colsrows,
                 "Panel Density": pd_eff, "Relief": relief_eff}
        for dst, src in SILH:
            wires[dst] = group_in(g, src)
        for k in COREK:
            wires[k] = group_in(g, k)
        for k in PAINTK:
            wires[k] = group_in(g, k)
        wires.update(wires_over or {})
        values = dict(values_over or {})
        values.setdefault("Towers Down", 0)
        # rooftop machinery comes from fixtures; panel blisters never
        # pass the building-scale area floor (socket not exposed)
        values.setdefault("Blisters", 0.0)
        values.setdefault("Relief Floor Mult", 10.0)
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

    def ground(geo, h):
        """Base at plinth-socket height: body spans [0.4ph, h+0.4ph]."""
        return move(geo, 0.0, 0.0,
                    g.math("ADD", g.math("MULTIPLY", h, 0.5),
                           g.math("MULTIPLY", ph, 0.4)))

    def gated(geo, gate, join):
        sw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(gate, in_sock(sw, "Switch"))
        g.l(geo, in_sock(sw, "True", "GEOMETRY"))
        g.l(out_sock(sw, "Output", "GEOMETRY"), join.inputs[0])

    def plinth_call(w, dp):
        return gcall(g, parts["plinth"], wires={
            "Width": w, "Depth": dp, "Height": ph,
            "Entrances": entr_eff,
            "Entrance Size": group_in(g, "Entrance Size")})

    def mat4(role):
        is_oxr = int_eq(group_in(g, "Faction"), 1)
        is_nyx = int_eq(group_in(g, "Faction"), 2)
        is_fpt = int_eq(group_in(g, "Faction"), 3)
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

    # ============================ FORM 0: TOWER BLOCK ==================
    tower = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(plinth_call(g.math("MULTIPLY", W0, 1.25),
                             g.math("MULTIPLY", Dp0, 1.25)),
                 "Geometry"), tower.inputs[0])
    tw_core = core_call(W0, Dp0, H0)
    g.l(ground(out_sock(tw_core, "Geometry"), H0), tower.inputs[0])
    heli = gcall(g, parts["pad"], wires={
        "Reach": g.math("MULTIPLY", W0, 0.12),
        "Root": g.math("MULTIPLY", W0, 0.05),
        "Size": g.math("MULTIPLY",
                       g.math("MULTIPLY", W0, 0.24),
                       group_in(g, "Pad Size")),
        "Verts": pad_verts, "Lights": not_l2.outputs[0]})
    # placed later via raycast (needs the switched form)

    # ============================ FORM 1: INDUSTRIAL WORKS =============
    works = g.n("GeometryNodeJoinGeometry")
    wW = g.math("MULTIPLY", W0, 1.5)
    wD = g.math("MULTIPLY", Dp0, 1.3)
    wH = g.math("MULTIPLY", H0, 0.30)
    g.l(out_sock(plinth_call(g.math("MULTIPLY", W0, 3.4),
                             g.math("MULTIPLY", Dp0, 2.4)),
                 "Geometry"), works.inputs[0])
    wk_core = core_call(wW, wD, wH, seed_off=31.0,
                        wires_over={"Levels": block_levels,
                                    "Panel Density": pd_m1},
                        values_over={"Towers Up": 0, "Base Flare": 0.2})
    g.l(move(ground(out_sock(wk_core, "Geometry"), wH),
             g.math("MULTIPLY", W0, -0.55), 0.0, 0.0), works.inputs[0])
    # stacks on the block's north flank, grounded beside it
    for i in range(6):
        sx = g.math("MULTIPLY", wW,
                    g.rand_float(-0.4, 0.4, None,
                                 g.math("ADD", seed, 41.0 + i * 9.0)))
        shj = g.math("MULTIPLY",
                     g.math("MULTIPLY", wH, 1.6),
                     g.math("MULTIPLY", group_in(g, "Stack Height"),
                            g.rand_float(0.8, 1.15, None,
                                         g.math("ADD", seed,
                                                42.0 + i * 9.0))))
        stk = gcall(g, parts["stack"], wires={
            "Height": shj, "Radius": g.math("MULTIPLY", W0, 0.06),
            "Verts": stack_verts, "Collars": stack_collars,
            "Beacon": int_gt(beacons_eff, 0),
            "Seed": g.math("ADD", seed, 5.0 * i)})
        gated(move(out_sock(stk, "Geometry"),
                   g.math("ADD", g.math("MULTIPLY", W0, -0.55), sx),
                   g.math("MULTIPLY", wD, 0.62), 0.0),
              int_gt(group_in(g, "Stacks"), i), works)
    # grounded tank farm east of the block
    tkR = g.math("MULTIPLY",
                 g.math("MULTIPLY", W0, 0.08),
                 group_in(g, "Tank Scale"))
    tkL = g.math("MULTIPLY",
                 g.math("MULTIPLY", H0, 0.20),
                 group_in(g, "Tank Scale"))
    for i in range(4):
        tank = gcall(g, parts["tank"], wires={
            "Count": tpc_eff,
            "Radius": tkR, "Length": tkL, "Verts": tank_verts,
            "Seed": g.math("ADD", seed, 7.0 * i)})
        ty = g.math("MULTIPLY", Dp0, -0.75 + 0.55 * (i % 2))
        tx = g.math("MULTIPLY", W0, 0.85 + 0.55 * (i // 2))
        gated(move(out_sock(tank, "Geometry"), tx, ty,
                   g.math("ADD", g.math("MULTIPLY", tkL, 0.5),
                          g.math("MULTIPLY", tkR, 0.6))),
              int_gt(tclusters_eff, i), works)
    # truss rack + pipe runs bridging block -> farm
    gapL = g.math("MULTIPLY", W0, 1.35)
    rack = gcall(g, parts["truss"], wires={
        "Length": gapL, "Width": g.math("MULTIPLY", W0, 0.10),
        "Height": g.math("MULTIPLY", W0, 0.10), "Bays": truss_bays})
    gated(move(out_sock(rack, "Geometry"),
               g.math("MULTIPLY", W0, -0.1), 0.0,
               g.math("MULTIPLY", wH, 0.35)), not_l2.outputs[0], works)
    for i in range(4):
        pr = gcall(g, parts["piperun"], wires={
            "Length": g.math("MULTIPLY", gapL, 1.1),
            "Rise": g.math("MULTIPLY", wH,
                           0.55 + 0.18 * i),
            "Radius": g.math("MULTIPLY", W0, 0.018),
            "Verts": pipe_verts,
            "Seed": g.math("ADD", seed, 11.0 * i)},
            values={"Pipes": 2, "Supports": 3})
        gated(move(out_sock(pr, "Geometry"),
                   g.math("MULTIPLY", W0, -0.2),
                   g.math("MULTIPLY", wD, -0.2 + 0.16 * i), 0.0),
              int_gt(pipes_eff, i), works)

    # ============================ FORM 2: HAB SLAB =====================
    hab = g.n("GeometryNodeJoinGeometry")
    hW = g.math("MULTIPLY", W0, 1.9)
    hD = g.math("MULTIPLY", Dp0, 1.6)
    hH = g.math("MULTIPLY", H0, 0.16)
    g.l(out_sock(plinth_call(g.math("MULTIPLY", hW, 1.15),
                             g.math("MULTIPLY", hD, 1.15)),
                 "Geometry"), hab.inputs[0])
    cs = group_in(g, "Courtyard Size")
    ring = g.n("GeometryNodeJoinGeometry")
    # long slabs along X at +-Y; short slabs along Y at +-X; corners
    # interpenetrate 0.06*W (island insurance)
    longW = hW
    longD = g.math("MULTIPLY", hD,
                   g.math("MULTIPLY",
                          g.math("SUBTRACT", 1.0, cs), 0.5))
    for si, sy in enumerate((1.0, -1.0)):
        sl = core_call(longW, longD, hH, seed_off=61.0 + si * 7.0,
                       wires_over={"Levels": slab_levels,
                                   "Cols": slab_cols, "Rows": slab_cols,
                                   "Panel Density": pd_m1},
                       values_over={"Towers Up": 0, "Top Plateaus": 0,
                                    "Base Flare": 0.0,
                                    "Ledges": 2, "Ledge Depth": 0.8})
        g.l(move(ground(out_sock(sl, "Geometry"), hH), 0.0,
                 g.math("MULTIPLY",
                        g.math("MULTIPLY", hD, 0.5),
                        g.math("MULTIPLY",
                               g.math("ADD", 1.0,
                                      g.math("MULTIPLY", cs, -0.5)),
                               sy)), 0.0), ring.inputs[0])
    shortW = g.math("MULTIPLY", hW,
                    g.math("MULTIPLY",
                           g.math("SUBTRACT", 1.0, cs), 0.5))
    shortD = g.math("ADD",
                    g.math("MULTIPLY", hD, cs),
                    g.math("MULTIPLY", hW, 0.06))
    for si, sx in enumerate((1.0, -1.0)):
        ss = core_call(shortW, shortD, hH, seed_off=65.0 + si * 7.0,
                       wires_over={"Levels": slab_levels,
                                   "Cols": slab_cols, "Rows": slab_cols,
                                   "Panel Density": pd_m1},
                       values_over={"Towers Up": 0, "Top Plateaus": 0,
                                    "Base Flare": 0.0,
                                    "Ledges": 1, "Ledge Depth": 0.7})
        g.l(move(ground(out_sock(ss, "Geometry"), hH),
                 g.math("MULTIPLY",
                        g.math("MULTIPLY", hW, 0.5),
                        g.math("MULTIPLY",
                               g.math("ADD", 1.0,
                                      g.math("MULTIPLY", cs, -0.5)),
                               sx)), 0.0, 0.0), ring.inputs[0])
    # courtyard floor deck (faction deck material)
    floor = _prim(g, "cube",
                  (g.math("MULTIPLY", hW, cs),
                   g.math("MULTIPLY", hD, cs), 1.6), None, None, None)
    smf = g.n("GeometryNodeSetMaterial")
    g.l(floor, smf.inputs[0])
    g.l(mat4("deck"), in_sock(smf, "Material"))
    g.l(move(out_sock(smf, "Geometry"), 0.0, 0.0,
             g.math("ADD", 0.8, g.math("MULTIPLY", ph, 0.4))),
        ring.inputs[0])
    # single-slab variant when Courtyard is off
    solo = core_call(hW, g.math("MULTIPLY", hD, 0.85), hH,
                     seed_off=69.0,
                     wires_over={"Levels": slab_levels,
                                 "Panel Density": pd_m1},
                     values_over={"Towers Up": 0, "Base Flare": 0.0,
                                  "Ledges": 3, "Ledge Depth": 0.8})
    hsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    cy_and = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(group_in(g, "Courtyard"), cy_and.inputs[0])
    g.l(not_l2.outputs[0], cy_and.inputs[1])
    g.l(cy_and.outputs[0], in_sock(hsw, "Switch"))
    g.l(ground(out_sock(solo, "Geometry"), hH),
        in_sock(hsw, "False", "GEOMETRY"))
    g.l(out_sock(ring, "Geometry"), in_sock(hsw, "True", "GEOMETRY"))
    g.l(out_sock(hsw, "Output", "GEOMETRY"), hab.inputs[0])

    # ============================ FORM 3: SPACEPORT ====================
    port = g.n("GeometryNodeJoinGeometry")
    tspan = group_in(g, "Terminal Span")
    pW = g.math("MULTIPLY", W0, tspan)
    pD = g.math("MULTIPLY", Dp0, 1.2)
    pH = g.math("MULTIPLY", H0, 0.15)
    g.l(out_sock(plinth_call(g.math("MULTIPLY", pW, 1.3),
                             g.math("MULTIPLY", Dp0, 3.4)),
                 "Geometry"), port.inputs[0])
    hall = core_call(pW, pD, pH, seed_off=91.0,
                     wires_over={"Levels": slab_levels,
                                 "Panel Density": pd_m1},
                     values_over={"Towers Up": 0, "Corner Cut": 0.7,
                                  "Base Flare": 0.0})
    g.l(move(ground(out_sock(hall, "Geometry"), pH), 0.0,
             g.math("MULTIPLY", Dp0, -0.9), 0.0), port.inputs[0])
    # inline control tower: shaft + glazed drum cab + dome
    ctH = g.math("MULTIPLY", H0, 0.45)
    ct_x = g.math("MULTIPLY", pW, -0.38)
    ct_y = g.math("MULTIPLY", Dp0, -1.55)
    shaft = core_call(g.math("MULTIPLY", W0, 0.20),
                      g.math("MULTIPLY", Dp0, 0.20), ctH,
                      seed_off=95.0,
                      wires_over={"Levels": block_levels,
                                  "Cols": slab_cols, "Rows": slab_cols,
                                  "Panel Density": pd_m1},
                      values_over={"Style": 3, "Towers Up": 0,
                                   "Top Plateaus": 0, "Ledges": 1,
                                   "Base Flare": 0.4, "Trenches": 0,
                                   "Hangars": 0, "Accent Bands": 0})
    cab = core_call(g.math("MULTIPLY", W0, 0.30),
                    g.math("MULTIPLY", Dp0, 0.30),
                    g.math("MULTIPLY", H0, 0.06),
                    seed_off=97.0,
                    values_over={"Levels": 6, "Cols": 5, "Rows": 5,
                                 "Panel Density": 1,
                                 "Style": 4, "Towers Up": 0,
                                 "Top Plateaus": 0, "Ledges": 0,
                                 "Base Flare": 0.0, "Window Glow": 1.0,
                                 "Light Rows": 2, "Trenches": 0,
                                 "Hangars": 0})
    ctj = g.n("GeometryNodeJoinGeometry")
    g.l(ground(out_sock(shaft, "Geometry"), ctH), ctj.inputs[0])
    cabj = g.n("GeometryNodeJoinGeometry")
    g.l(move(ground(out_sock(cab, "Geometry"),
                    g.math("MULTIPLY", H0, 0.06)),
             0.0, 0.0, g.math("MULTIPLY", ctH, 0.98)), cabj.inputs[0])
    ctd = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", W0, 0.14)}, values={"Variant": 0})
    g.l(move(out_sock(ctd, "Geometry"), 0.0, 0.0,
             g.math("ADD", g.math("MULTIPLY", ctH, 0.98),
                    g.math("MULTIPLY", H0, 0.055))), cabj.inputs[0])
    cabsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(not_l2.outputs[0], in_sock(cabsw, "Switch"))
    g.l(out_sock(cabj, "Geometry"), in_sock(cabsw, "True", "GEOMETRY"))
    g.l(out_sock(cabsw, "Output", "GEOMETRY"), ctj.inputs[0])
    ctmv = move(out_sock(ctj, "Geometry"), ct_x, ct_y, 0.0)
    gated(ctmv, group_in(g, "Control Tower"), port)
    # landing pad row on the +Y apron, piers buried into the hall flank
    padp = gcall(g, parts["pad"], wires={
        "Reach": g.math("MULTIPLY", Dp0, 0.75),
        "Root": g.math("MULTIPLY", Dp0, 0.65),
        "Size": g.math("MULTIPLY",
                       g.math("MULTIPLY", W0, 0.34),
                       group_in(g, "Pad Size")),
        "Verts": pad_verts, "Lights": not_l2.outputs[0]})
    prot = g.n("GeometryNodeTransform")
    g.l(out_sock(padp, "Geometry"), prot.inputs[0])
    in_sock(prot, "Rotation").default_value = (0.0, 0.0, 1.5707963)
    for i in range(4):
        px = g.math("MULTIPLY", pW, -0.36 + 0.24 * i)
        gated(move(out_sock(prot, "Geometry"), px,
                   g.math("MULTIPLY", Dp0, -0.55),
                   g.math("MULTIPLY", ph, 0.85)),
              int_gt(pads_eff, i), port)
    # apron edge lights
    for sy in (1.0,):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", pW, 1.15),
                              g.math("MULTIPLY", W0, 0.03),
                              g.math("MULTIPLY", W0, 0.03)), None,
                  (0.0, g.math("MULTIPLY", Dp0, 1.62),
                   g.math("MULTIPLY", ph, 1.05)), mats["padlight"]),
            port.inputs[0])

    # ---- pick the form ------------------------------------------------
    fsel = g.n("GeometryNodeIndexSwitch", data_type="GEOMETRY")
    while len(fsel.index_switch_items) < 4:
        fsel.index_switch_items.new()
    g.l(group_in(g, "Form"), in_sock(fsel, "Index"))
    for i, br in enumerate((tower, works, hab, port)):
        g.l(out_sock(br, "Geometry"), in_sock(fsel, str(i)))
    formed = out_sock(fsel, "Output")

    out = g.n("GeometryNodeJoinGeometry")
    g.l(formed, out.inputs[0])

    # ---- roof fixtures: raycast onto whichever form won ---------------
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
        g.l(g.math("MULTIPLY", H0, 3.0 if down else -3.0),
            srcv.inputs[2])
        g.l(srcv.outputs[0], in_sock(rc, "Source Position"))
        in_sock(rc, "Ray Direction").default_value = \
            (0.0, 0.0, -1.0 if down else 1.0)
        g.l(g.math("MULTIPLY", H0, 6.0), in_sock(rc, "Ray Length"))
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

    # helipad (tower roofs; harmless empty on other forms)
    heli_gate = g.n("FunctionNodeBooleanMath", operation="AND")
    g.l(group_in(g, "Helipad"), heli_gate.inputs[0])
    g.l(int_eq(group_in(g, "Form"), 0), heli_gate.inputs[1])
    place_ray(g.math("MULTIPLY", W0, 0.08),
              g.math("MULTIPLY", Dp0, 0.08),
              out_sock(heli, "Geometry"), heli_gate.outputs[0],
              upright=True, sink=g.math("MULTIPLY", W0, 0.02))
    grate = gcall(g, parts["grate"], wires={
        "Length": g.math("MULTIPLY", W0, 0.20),
        "Width": g.math("MULTIPLY", W0, 0.12)}, values={"Slats": 8})
    for i, (xf, yf) in enumerate(((-0.16, 0.18), (0.16, -0.14),
                                  (-0.22, -0.16), (0.20, 0.20))):
        place_ray(g.math("MULTIPLY", W0, xf), g.math("MULTIPLY", Dp0, yf),
                  out_sock(grate, "Geometry"), int_gt(fix_cnt("Vents"), i),
                  sink=g.math("MULTIPLY", W0, 0.004))
    rad0 = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", W0, 0.12)}, values={"Variant": 0})
    rad1 = gcall(g, parts["radome"], wires={
        "Size": g.math("MULTIPLY", W0, 0.10)}, values={"Variant": 1})
    s_r1 = g.math("MULTIPLY", W0, 0.10)
    rad1j = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(rad1, "Geometry"), rad1j.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", s_r1, 0.14),
                          g.math("MULTIPLY", s_r1, 0.10),
                          g.math("MULTIPLY", s_r1, 0.20)), None,
              (g.math("MULTIPLY", s_r1, 0.10), 0.0,
               g.math("MULTIPLY", s_r1, 0.66)), mats["dark"]),
        rad1j.inputs[0])
    place_ray(g.math("MULTIPLY", W0, -0.08),
              g.math("MULTIPLY", Dp0, -0.14),
              out_sock(rad0, "Geometry"), int_gt(fix_cnt("Radomes"), 0),
              sink=g.math("MULTIPLY", W0, 0.006))
    place_ray(g.math("MULTIPLY", W0, 0.14),
              g.math("MULTIPLY", Dp0, 0.10),
              out_sock(rad1j, "Geometry"), int_gt(fix_cnt("Radomes"), 1),
              sink=g.math("MULTIPLY", W0, 0.006))
    mast = gcall(g, parts["mast"], wires={
        "Size": g.math("MULTIPLY", W0, 0.20)})
    for i, (xf, yf) in enumerate(((-0.20, 0.10), (0.10, 0.22),
                                  (0.22, -0.10))):
        place_ray(g.math("MULTIPLY", W0, xf), g.math("MULTIPLY", Dp0, yf),
                  out_sock(mast, "Geometry"),
                  int_gt(fix_cnt("Antennas"), i), upright=True,
                  sink=g.math("MULTIPLY", W0, 0.006))
    chev = gcall(g, parts["chevron"], wires={
        "Size": g.math("MULTIPLY", W0, 0.34)})
    place_ray(g.math("MULTIPLY", W0, 0.16), 0.0,
              out_sock(chev, "Geometry"), int_gt(fix_cnt("Decals"), 0),
              sink=g.math("MULTIPLY", W0, 0.004))
    hnum = gcall(g, parts["number"], wires={
        "Size": g.math("MULTIPLY", W0, 0.20),
        "Value": g.rand_float(0.0, 99.9, None,
                              g.math("ADD", seed, 77.0))})
    place_ray(g.math("MULTIPLY", W0, -0.10), 0.0,
              out_sock(hnum, "Geometry"), int_gt(fix_cnt("Decals"), 1),
              sink=g.math("MULTIPLY", W0, 0.004))
    beac = _prim(g, "cube", (g.math("MULTIPLY", W0, 0.03),
                             g.math("MULTIPLY", W0, 0.03),
                             g.math("MULTIPLY", W0, 0.03)), None, None,
                 mats["beacon"])
    for i, (xf, yf) in enumerate(((0.0, 0.0), (0.24, 0.0),
                                  (-0.24, 0.0), (0.0, 0.24))):
        place_ray(g.math("MULTIPLY", W0, xf), g.math("MULTIPLY", Dp0, yf),
                  beac, int_gt(beacons_eff, i),
                  sink=g.math("MULTIPLY", W0, -0.012))

    final = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(out, "Geometry"), final.inputs[0])
    return g.finish(out_sock(final, "Geometry"))


# ---------------------------------------------------------------- main -----

def main():
    outp = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    hg = fi_deps(DEP_WANT)
    mats = build_building_materials()
    parts = {}
    # station core trio + components, rebuilt here and renamed so both
    # kits can coexist in one asset browser (the fleet-fixture pattern)
    for key, builder, name, needs in (
            ("profile", station.build_station_profile,
             "FI_BuildingProfile", ()),
            ("core", station.build_station_core,
             "FI_BuildingCore", ("profile",)),
            ("dress", station.build_station_dress,
             "FI_BuildingDress", ("mats", "hg", "parts")),
            ("core_dressed", station.build_station_core_dressed,
             "FI_BuildingCoreDressed", ("parts",)),
            ("truss", station.build_station_truss,
             "FI_BuildingTruss", ("mats",)),
            ("tank", station.build_station_tank,
             "FI_BuildingTank", ("mats",)),
            ("pad", station.build_dock_pad, "FI_BuildingPad", ("mats",))):
        argmap = {"mats": mats, "hg": hg, "parts": parts,
                  "profile": parts.get("profile")}
        grp = builder(*[argmap[n] for n in needs])
        grp.name = name
        parts[key] = grp
    for key, builder, name in (
            ("grate", fleet.build_vent_grate, "FI_BuildingVentGrate"),
            ("radome", fleet.build_radome, "FI_BuildingRadome"),
            ("mast", fleet.build_antenna_mast, "FI_BuildingAntennaMast"),
            ("boom", fleet.build_sensor_boom, "FI_BuildingSensorBoom"),
            ("chevron", fleet.build_chevron, "FI_BuildingChevron"),
            ("number", fleet.build_hull_number, "FI_BuildingHullNumber")):
        grp = builder(mats)
        grp.name = name
        parts[key] = grp
    parts["plinth"] = build_building_plinth(mats)
    parts["stack"] = build_stack(mats)
    parts["piperun"] = build_pipe_run(mats)
    parts["building"] = build_building(mats, hg, parts)
    contract = {}
    for ng in parts.values():
        contract[ng.name] = [
            {"name": it.name, "in_out": it.in_out,
             "type": getattr(it, "socket_type", "?"),
             "identifier": it.identifier}
            for it in ng.interface.items_tree
            if it.item_type == "SOCKET"]
    with open(os.path.join(os.path.dirname(outp),
                           "building_contract.json"), "w") as f:
        json.dump(contract, f, indent=1, sort_keys=True)
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=outp, compress=True)
    print(f"build_buildingkit: OK -> {outp} ({len(parts)} groups + "
          f"{len(hg)} native deps)")


if __name__ == "__main__":
    main()
