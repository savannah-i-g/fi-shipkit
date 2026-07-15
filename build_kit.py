#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# build_kit.py -- regenerate FI_ShipKit.blend from scratch (idempotent).
#
#   blender -b --python build_kit.py -- [--out FI_ShipKit.blend]
#
# Builds: FI_Panelize, FI_GreebleScatter, FI_EngineCluster, FI_RCS_Block,
# FI_AntennaMast, FI_RadiatorArray node groups; the FI_Greebles collection
# (24 bmesh-built items, <=200 tris each, origin at hull-contact face,
# +Z out of the hull, +X along ship fore-aft); FI_* materials.
#
# SOCKET CONTRACT: group/socket names and order are FROZEN -- additive
# evolution only; a breaking change ships as a new group name. The contract
# is dumped to kit_contract.json on every build; git diff is the check.

import bpy
import bmesh
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fi_gn_lib import (TAU, G, gcall, group_in, in_sock, out_sock,  # noqa
                       _prim, _shader_wear, _base_brick, _base_flat,
                       _base_panels, mat, build_engine_cluster)



def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "FI_ShipKit.blend")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    return out


# ------------------------------------------------------------ node utils ---

# ------------------------------------------------------------- materials ---

def build_materials():
    return {
        "metal": mat("FI_KitMetal", (0.34, 0.36, 0.38), 0.55, 0.8),
        "dark": mat("FI_KitDark", (0.16, 0.17, 0.18), 0.7, 0.6),
        "engine": mat("FI_Engine", (0.22, 0.23, 0.25), 0.4, 0.9),
        "glow": mat("FI_EngineGlow", (0.05, 0.05, 0.06), 0.5, 0.0,
                    emissive=(0.25, 0.55, 1.0), estrength=6.0),
        "radiator": mat("FI_Radiator", (0.12, 0.12, 0.13), 0.8, 0.3,
                        emissive=(1.0, 0.35, 0.08), estrength=2.0),
        "hull": mat("FI_HullMetal", (0.52, 0.54, 0.57), 0.5, 0.65),
        "glass": glass_mat(),
        # frame-ship (ISS lineage) palette
        "white": mat("FI_ThermalWhite", (0.78, 0.78, 0.76), 0.8, 0.05),
        "gold": mat("FI_MLIGold", (0.82, 0.62, 0.22), 0.35, 1.0),
        "solar": mat("FI_SolarPanel", (0.04, 0.07, 0.16), 0.25, 0.4),
        "amber": mat("FI_SolarAmber", (0.55, 0.30, 0.08), 0.3, 0.5),
        "truss": mat("FI_TrussMetal", (0.42, 0.42, 0.44), 0.7, 0.6),
        "red": mat("FI_AccentRed", (0.55, 0.08, 0.07), 0.5, 0.3),
        "blue": mat("FI_AccentBlue", (0.08, 0.16, 0.42), 0.5, 0.3),
        "padded": mat("FI_PaddedFabric", (0.74, 0.74, 0.72), 0.85, 0.0),
        "glowhalo": mat("FI_EngineGlowHalo", (0.04, 0.05, 0.07), 0.5, 0.0,
                        emissive=(0.12, 0.28, 0.6), estrength=1.6),
        "navstrip": mat("FI_NavStrip", (0.06, 0.06, 0.05), 0.3, 0.0,
                        emissive=(1.0, 0.85, 0.55), estrength=2.5),
        "window": mat("FI_Window", (0.05, 0.06, 0.08), 0.2, 0.0,
                      emissive=(0.95, 0.75, 0.45), estrength=1.6),
        "navred": mat("FI_NavRed", (0.3, 0.02, 0.02), 0.4, 0.0,
                      emissive=(1.0, 0.05, 0.05), estrength=5.0),
        "navgreen": mat("FI_NavGreen", (0.02, 0.3, 0.05), 0.4, 0.0,
                        emissive=(0.1, 1.0, 0.2), estrength=5.0),
    }


def glass_mat():
    m = bpy.data.materials.get("FI_Glass") or bpy.data.materials.new("FI_Glass")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.08, 0.12, 0.16, 1.0)
    b.inputs["Roughness"].default_value = 0.1
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Alpha"].default_value = 0.55  # opacity<1 -> engine glass pass
    m.blend_method = "BLEND"
    m.diffuse_color = (0.08, 0.12, 0.16, 0.55)
    m.asset_mark()
    return m


# ---------------------------------------------- procedural shaders ---------
# Savannah's Hull_Generator_HD method, systematized (TEXTURE_DESIGN.md):
# brick panel grid + musgrave breakup for the base, bevel-normal edge mask
# driving a WEAR layer, AO-driven grime, micro noise bump. Bevel + AO are
# Cycles-only: the viewport shows base colours, bakes carry the detail.

def build_procedural_shaders(mats):
    _shader_wear(mats["white"],
                 lambda nt: _base_panels(nt, "hull-texture2",
                                         (1.0, 1.0, 0.97), 0.30, lift=0.25),
                 wear=0.45, grime=0.30, rough=0.75, metal=0.05)
    _shader_wear(mats["truss"], lambda nt: _base_flat(nt, (0.42, 0.42, 0.44)),
                 wear=0.8, grime=0.55, rough=0.65, metal=0.6)
    _shader_wear(mats["hull"], lambda nt: _base_panels(
                     nt, "hull-texture2", (1.0, 1.0, 1.0), 0.30),
                 wear=0.5, grime=0.35, rough=0.5, metal=0.65)
    _shader_wear(mats["gold"], lambda nt: _base_flat(nt, (0.82, 0.62, 0.22)),
                 wear=0.25, grime=0.2, rough=0.32, metal=1.0,
                 bump_scale=18.0, bump_str=0.35)  # MLI foil crinkle
    # worn paint: accents reveal thermal white underneath
    for key, rgb in (("red", (0.55, 0.08, 0.07)),
                     ("blue", (0.08, 0.16, 0.42))):
        _shader_wear(mats[key], lambda nt, c=rgb: _base_flat(nt, c),
                     wear=0.7, grime=0.3, wear_col=(0.78, 0.78, 0.76),
                     rough=0.5, metal=0.0, wear_metal=0.05)
    # solar wings: her SolarPanel003 pack; amber = warm-tinted variant
    for key, tint in (("solar", (1.0, 1.0, 1.0)),
                      ("amber", (1.6, 0.95, 0.45))):
        _shader_wear(mats[key],
                     lambda nt, tt=tint: _base_panels(
                         nt, "solarpanel003", tt, 0.9),
                     wear=0.08, grime=0.08, rough=0.25, metal=0.3,
                     bump_str=0.02)
    # padded thermal-blanket fabric (Fabric048) for pressurised modules
    _shader_wear(mats["padded"],
                 lambda nt: _base_panels(nt, "fabric048",
                                         (0.95, 0.95, 0.92), 0.8),
                 wear=0.15, grime=0.5, rough=0.85, metal=0.0,
                 wear_metal=0.1)


# ------------------------------------------------------------ FI_Panelize --

def build_panelize():
    g = G("FI_Panelize")
    g.sock_in("Geometry", "NodeSocketGeometry")
    g.sock_in("Mask", "NodeSocketFloat", 1.0, 0.0, 1.0)
    g.sock_in("Panel Angle (deg)", "NodeSocketFloat", 20.0, 1.0, 89.0)
    g.sock_in("Gap Ratio", "NodeSocketFloat", 0.97, 0.80, 1.0)
    g.sock_in("Groove Depth", "NodeSocketFloat", 0.06, 0.0, 0.5)
    g.sock_in("Plate Height Min", "NodeSocketFloat", 0.0, 0.0, 0.5)
    g.sock_in("Plate Height Max", "NodeSocketFloat", 0.05, 0.0, 0.5)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # ADDITIVE (2026-07-10 shipgen): extra edge-domain seam selection, OR'd
    # with the facet-angle split — lets generators cut long strakes.
    g.sock_in("Seam Selection", "NodeSocketBool", False)

    # mask > 0.5 -> masked region M / remainder R
    cmp = g.n("FunctionNodeCompare", data_type="FLOAT",
              operation="GREATER_THAN")
    g.l(group_in(g, "Mask"), cmp.inputs[0])
    cmp.inputs[1].default_value = 0.5
    sep = g.n("GeometryNodeSeparateGeometry", domain="FACE")
    g.l(group_in(g, "Geometry"), sep.inputs[0])
    g.l(out_sock(cmp, "Result"), in_sock(sep, "Selection"))
    m_geo = out_sock(sep, "Selection")
    r_geo = out_sock(sep, "Inverted")

    # groove floor: masked copy pushed inward, tagged fi_panel_rand = -1
    nrm = g.n("GeometryNodeInputNormal")
    scale = g.n("ShaderNodeVectorMath", operation="SCALE")
    g.l(out_sock(nrm, "Normal"), scale.inputs[0])
    neg = g.math("MULTIPLY", group_in(g, "Groove Depth"), -1.0)
    g.l(neg, scale.inputs[3])  # SCALE factor socket
    setpos = g.n("GeometryNodeSetPosition")
    g.l(m_geo, setpos.inputs[0])
    g.l(scale.outputs[0], in_sock(setpos, "Offset"))
    floor_tag = g.n("GeometryNodeStoreNamedAttribute",
                    data_type="FLOAT", domain="FACE")
    g.l(out_sock(setpos, "Geometry"), floor_tag.inputs[0])
    in_sock(floor_tag, "Name").default_value = "fi_panel_rand"
    in_sock(floor_tag, "Value", "VALUE").default_value = -1.0
    floor_geo = out_sock(floor_tag, "Geometry")

    # plates: split by facet angle -> islands -> shrink -> raise
    angle_rad = g.math("RADIANS", group_in(g, "Panel Angle (deg)"))
    eang = g.n("GeometryNodeInputMeshEdgeAngle")
    acmp = g.n("FunctionNodeCompare", data_type="FLOAT",
               operation="GREATER_THAN")
    g.l(out_sock(eang, "Unsigned Angle"), acmp.inputs[0])
    g.l(angle_rad, acmp.inputs[1])
    split_sel = g.n("FunctionNodeBooleanMath", operation="OR")
    g.l(out_sock(acmp, "Result"), split_sel.inputs[0])
    g.l(group_in(g, "Seam Selection"), split_sel.inputs[1])
    split = g.n("GeometryNodeSplitEdges")
    g.l(m_geo, split.inputs[0])
    g.l(split_sel.outputs[0], in_sock(split, "Selection"))

    isl = g.n("GeometryNodeInputMeshIsland")
    isl_idx = out_sock(isl, "Island Index")

    shrink = g.n("GeometryNodeScaleElements", domain="FACE")
    g.l(out_sock(split, "Mesh"), shrink.inputs[0])
    g.l(group_in(g, "Gap Ratio"), in_sock(shrink, "Scale"))

    # per-plate random BEFORE extrude so new faces inherit it
    prand = g.rand_float(0.0, 1.0, isl_idx,
                         g.math("ADD", group_in(g, "Seed"), 1.0))
    ptag = g.n("GeometryNodeStoreNamedAttribute",
               data_type="FLOAT", domain="FACE")
    g.l(out_sock(shrink, "Geometry"), ptag.inputs[0])
    in_sock(ptag, "Name").default_value = "fi_panel_rand"
    g.l(prand, in_sock(ptag, "Value", "VALUE"))

    hrand = g.rand_float(group_in(g, "Plate Height Min"),
                         group_in(g, "Plate Height Max"),
                         isl_idx, group_in(g, "Seed"))
    ext = g.n("GeometryNodeExtrudeMesh", mode="FACES")
    g.l(out_sock(ptag, "Geometry"), ext.inputs[0])
    g.l(hrand, in_sock(ext, "Offset Scale"))
    in_sock(ext, "Individual").default_value = False

    join = g.n("GeometryNodeJoinGeometry")
    # join order: remainder, floor, plates (all into the multi-socket)
    g.l(out_sock(ext, "Mesh"), join.inputs[0])
    g.l(floor_geo, join.inputs[0])
    g.l(r_geo, join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


# ------------------------------------------------------ FI_GreebleScatter --

def build_greeble_scatter():
    g = G("FI_GreebleScatter")
    g.sock_in("Geometry", "NodeSocketGeometry")
    g.sock_in("Greebles", "NodeSocketCollection")
    g.sock_in("Mask", "NodeSocketFloat", 1.0, 0.0, 1.0)
    g.sock_in("Density (per m2)", "NodeSocketFloat", 0.15, 0.001, 20.0)
    g.sock_in("Greeble Count", "NodeSocketInt", 27, 1, 256)
    g.sock_in("Scale Min", "NodeSocketFloat", 0.7, 0.05, 10.0)
    g.sock_in("Scale Max", "NodeSocketFloat", 1.3, 0.05, 10.0)
    g.sock_in("Align Fore-Aft", "NodeSocketBool", True)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")

    cmp = g.n("FunctionNodeCompare", data_type="FLOAT",
              operation="GREATER_THAN")
    g.l(group_in(g, "Mask"), cmp.inputs[0])
    cmp.inputs[1].default_value = 0.5

    # poisson spacing ~ 0.55 / sqrt(density)
    dmin = g.math("DIVIDE", 0.55,
                  g.math("SQRT", group_in(g, "Density (per m2)")))
    dist = g.n("GeometryNodeDistributePointsOnFaces",
               distribute_method="POISSON")
    g.l(group_in(g, "Geometry"), dist.inputs[0])
    g.l(out_sock(cmp, "Result"), in_sock(dist, "Selection"))
    g.l(dmin, in_sock(dist, "Distance Min"))
    g.l(group_in(g, "Density (per m2)"), in_sock(dist, "Density Max"))
    g.l(group_in(g, "Seed"), in_sock(dist, "Seed"))

    # orient: node Rotation output aligns +Z to the normal; then swing local X
    # toward ship +X so conduits/hatches read fore-aft
    align = g.n("FunctionNodeAlignEulerToVector", axis="X", pivot_axis="Z")
    g.l(out_sock(dist, "Rotation"), in_sock(align, "Rotation"))
    fact = g.n("ShaderNodeMath", operation="MULTIPLY")
    g.l(group_in(g, "Align Fore-Aft"), fact.inputs[0])
    fact.inputs[1].default_value = 1.0
    g.l(fact.outputs[0], in_sock(align, "Factor"))
    in_sock(align, "Vector").default_value = (1.0, 0.0, 0.0)

    cinfo = g.n("GeometryNodeCollectionInfo", transform_space="ORIGINAL")
    g.l(group_in(g, "Greebles"), in_sock(cinfo, "Collection"))
    in_sock(cinfo, "Separate Children").default_value = True
    in_sock(cinfo, "Reset Children").default_value = True

    pick_id = g.n("GeometryNodeInputID")
    pick_raw = g.rand_float(0.0, 4096.0, out_sock(pick_id, "ID"),
                            g.math("ADD", group_in(g, "Seed"), 3.0))
    pick = g.math("FLOORED_MODULO", pick_raw, group_in(g, "Greeble Count"))

    inst = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(dist, "Points"), inst.inputs[0])
    g.l(cinfo.outputs[0], in_sock(inst, "Instance"))
    in_sock(inst, "Pick Instance").default_value = True
    g.l(pick, in_sock(inst, "Instance Index"))
    g.l(out_sock(align, "Rotation"), in_sock(inst, "Rotation"))

    # 90-degree twist snap about local Z
    quarter = g.rand_float(0.0, 3.999, out_sock(pick_id, "ID"),
                           g.math("ADD", group_in(g, "Seed"), 7.0))
    twist = g.math("MULTIPLY", g.math("FLOOR", quarter), math.pi / 2.0)
    tvec = g.n("ShaderNodeCombineXYZ")
    g.l(twist, tvec.inputs[2])
    rot = g.n("GeometryNodeRotateInstances")
    g.l(out_sock(inst, "Instances"), rot.inputs[0])
    g.l(tvec.outputs[0], in_sock(rot, "Rotation"))
    in_sock(rot, "Local Space").default_value = True

    srand = g.rand_float(group_in(g, "Scale Min"), group_in(g, "Scale Max"),
                         out_sock(pick_id, "ID"),
                         g.math("ADD", group_in(g, "Seed"), 13.0))
    svec = g.n("ShaderNodeCombineXYZ")
    for i in range(3):
        g.l(srand, svec.inputs[i])
    scl = g.n("GeometryNodeScaleInstances")
    g.l(out_sock(rot, "Instances"), scl.inputs[0])
    g.l(svec.outputs[0], in_sock(scl, "Scale"))

    join = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(scl, "Instances"), join.inputs[0])
    g.l(group_in(g, "Geometry"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


# ------------------------------------------------- parametric modules ------



def build_rcs_block(mats):
    g = G("FI_RCS_Block")
    g.sock_in("Size", "NodeSocketFloat", 0.6, 0.1, 5.0)
    g.sock_in("Nozzle Length", "NodeSocketFloat", 0.28, 0.05, 2.0)
    g.sock_out("Geometry", "NodeSocketGeometry")

    base = g.n("GeometryNodeMeshCube")
    bsize = g.n("ShaderNodeCombineXYZ")
    g.l(group_in(g, "Size"), bsize.inputs[0])
    g.l(group_in(g, "Size"), bsize.inputs[1])
    g.l(g.math("MULTIPLY", group_in(g, "Size"), 0.4), bsize.inputs[2])
    g.l(bsize.outputs[0], in_sock(base, "Size"))
    base_t = g.n("GeometryNodeTransform")
    g.l(out_sock(base, "Mesh"), base_t.inputs[0])
    bz = g.math("MULTIPLY", group_in(g, "Size"), 0.2)
    bpos = g.n("ShaderNodeCombineXYZ")
    g.l(bz, bpos.inputs[2])
    g.l(bpos.outputs[0], in_sock(base_t, "Translation"))
    base_m = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(base_t, "Geometry"), base_m.inputs[0])
    in_sock(base_m, "Material").default_value = mats["metal"]

    join = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(base_m, "Geometry"), join.inputs[0])
    # 4 nozzles: +X -X +Y -Y, canted 40 deg up from the plane
    for i, yaw in enumerate((0.0, math.pi, math.pi / 2, -math.pi / 2)):
        noz = g.n("GeometryNodeMeshCone")
        in_sock(noz, "Vertices").default_value = 8
        g.l(g.math("MULTIPLY", group_in(g, "Size"), 0.16),
            in_sock(noz, "Radius Top"))
        g.l(g.math("MULTIPLY", group_in(g, "Size"), 0.09),
            in_sock(noz, "Radius Bottom"))
        g.l(group_in(g, "Nozzle Length"), in_sock(noz, "Depth"))
        t = g.n("GeometryNodeTransform")
        g.l(out_sock(noz, "Mesh"), t.inputs[0])
        # cone axis +Z; pitch outward then yaw around Z
        in_sock(t, "Rotation").default_value = (0.0, math.radians(50), yaw)
        off = g.n("ShaderNodeCombineXYZ")
        r = g.math("MULTIPLY", group_in(g, "Size"), 0.38)
        ox = g.math("MULTIPLY", r, math.cos(yaw))
        oy = g.math("MULTIPLY", r, math.sin(yaw))
        g.l(ox, off.inputs[0])
        g.l(oy, off.inputs[1])
        g.l(g.math("MULTIPLY", group_in(g, "Size"), 0.45), off.inputs[2])
        g.l(off.outputs[0], in_sock(t, "Translation"))
        m = g.n("GeometryNodeSetMaterial")
        g.l(out_sock(t, "Geometry"), m.inputs[0])
        in_sock(m, "Material").default_value = mats["dark"]
        g.l(out_sock(m, "Geometry"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_antenna_mast(mats):
    g = G("FI_AntennaMast")
    g.sock_in("Height", "NodeSocketFloat", 4.0, 0.3, 40.0)
    g.sock_in("Base Radius", "NodeSocketFloat", 0.18, 0.02, 2.0)
    g.sock_in("Dish", "NodeSocketBool", True)
    g.sock_out("Geometry", "NodeSocketGeometry")

    join = g.n("GeometryNodeJoinGeometry")
    # three stacked, tapering segments (h * 0.45 / 0.35 / 0.20)
    fractions = ((0.45, 1.0, 0.0), (0.35, 0.62, 0.45), (0.20, 0.30, 0.80))
    for frac, rmul, zfrac in fractions:
        seg = g.n("GeometryNodeMeshCylinder")
        in_sock(seg, "Vertices").default_value = 8
        g.l(g.math("MULTIPLY", group_in(g, "Base Radius"), rmul),
            in_sock(seg, "Radius"))
        h = g.math("MULTIPLY", group_in(g, "Height"), frac)
        g.l(h, in_sock(seg, "Depth"))
        t = g.n("GeometryNodeTransform")
        g.l(out_sock(seg, "Mesh"), t.inputs[0])
        z = g.math("ADD",
                   g.math("MULTIPLY", group_in(g, "Height"), zfrac),
                   g.math("MULTIPLY", h, 0.5))
        zv = g.n("ShaderNodeCombineXYZ")
        g.l(z, zv.inputs[2])
        g.l(zv.outputs[0], in_sock(t, "Translation"))
        m = g.n("GeometryNodeSetMaterial")
        g.l(out_sock(t, "Geometry"), m.inputs[0])
        in_sock(m, "Material").default_value = mats["metal"]
        g.l(out_sock(m, "Geometry"), join.inputs[0])

    # dish support arm (the dish floated without it — 2026-07-10 review)
    arm = g.n("GeometryNodeMeshCylinder")
    in_sock(arm, "Vertices").default_value = 6
    g.l(g.math("MULTIPLY", group_in(g, "Base Radius"), 0.5),
        in_sock(arm, "Radius"))
    g.l(g.math("MULTIPLY", group_in(g, "Base Radius"), 3.0),
        in_sock(arm, "Depth"))
    at = g.n("GeometryNodeTransform")
    g.l(out_sock(arm, "Mesh"), at.inputs[0])
    in_sock(at, "Rotation").default_value = (0.0, math.pi / 2.0, 0.0)
    av = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", group_in(g, "Base Radius"), 1.2), av.inputs[0])
    g.l(g.math("MULTIPLY", group_in(g, "Height"), 0.66), av.inputs[2])
    g.l(av.outputs[0], in_sock(at, "Translation"))
    am = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(at, "Geometry"), am.inputs[0])
    in_sock(am, "Material").default_value = mats["metal"]
    g.l(out_sock(am, "Geometry"), join.inputs[0])
    # dish: shallow cone at 2/3 height, facing forward (+X)
    dish = g.n("GeometryNodeMeshCone")
    in_sock(dish, "Vertices").default_value = 12
    g.l(g.math("MULTIPLY", group_in(g, "Height"), 0.16),
        in_sock(dish, "Radius Bottom"))
    in_sock(dish, "Radius Top").default_value = 0.01
    g.l(g.math("MULTIPLY", group_in(g, "Height"), 0.07),
        in_sock(dish, "Depth"))
    dt = g.n("GeometryNodeTransform")
    g.l(out_sock(dish, "Mesh"), dt.inputs[0])
    in_sock(dt, "Rotation").default_value = (0.0, math.pi / 2.0, 0.0)
    dz = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", group_in(g, "Base Radius"), 2.2), dz.inputs[0])
    g.l(g.math("MULTIPLY", group_in(g, "Height"), 0.66), dz.inputs[2])
    g.l(dz.outputs[0], in_sock(dt, "Translation"))
    dm = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(dt, "Geometry"), dm.inputs[0])
    in_sock(dm, "Material").default_value = mats["dark"]
    # gate the dish on the bool via a switch (typed lookups: the Switch node
    # carries hidden socket pairs for every data type)
    sw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    # Blender 5.0: Switch node has a single 'Switch' bool input
    g.l(group_in(g, "Dish"), in_sock(sw, "Switch"))
    g.l(out_sock(dm, "Geometry"), in_sock(sw, "True", "GEOMETRY"))
    g.l(out_sock(sw, "Output", "GEOMETRY"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_radiator_array(mats):
    g = G("FI_RadiatorArray")
    g.sock_in("Fin Count", "NodeSocketInt", 6, 1, 40)
    g.sock_in("Fin Length", "NodeSocketFloat", 3.0, 0.2, 30.0)
    g.sock_in("Fin Height", "NodeSocketFloat", 1.2, 0.1, 20.0)
    g.sock_in("Pitch", "NodeSocketFloat", 0.55, 0.1, 5.0)
    g.sock_out("Geometry", "NodeSocketGeometry")

    line = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Fin Count"), in_sock(line, "Count"))
    ovec = g.n("ShaderNodeCombineXYZ")
    g.l(group_in(g, "Pitch"), ovec.inputs[0])
    g.l(ovec.outputs[0], in_sock(line, "Offset"))

    fin = g.n("GeometryNodeMeshCube")
    fsize = g.n("ShaderNodeCombineXYZ")
    fsize.inputs[0].default_value = 0.06
    g.l(group_in(g, "Fin Length"), fsize.inputs[1])
    g.l(group_in(g, "Fin Height"), fsize.inputs[2])
    g.l(fsize.outputs[0], in_sock(fin, "Size"))
    fin_t = g.n("GeometryNodeTransform")
    g.l(out_sock(fin, "Mesh"), fin_t.inputs[0])
    fz = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", group_in(g, "Fin Height"), 0.5), fz.inputs[2])
    g.l(fz.outputs[0], in_sock(fin_t, "Translation"))
    fm = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(fin_t, "Geometry"), fm.inputs[0])
    in_sock(fm, "Material").default_value = mats["radiator"]

    inst = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(line, "Mesh"), inst.inputs[0])
    g.l(out_sock(fm, "Geometry"), in_sock(inst, "Instance"))

    # spine along the fin row
    spine = g.n("GeometryNodeMeshCylinder")
    in_sock(spine, "Vertices").default_value = 8
    in_sock(spine, "Radius").default_value = 0.12
    slen = g.math("MULTIPLY", group_in(g, "Fin Count"),
                  group_in(g, "Pitch"))
    g.l(slen, in_sock(spine, "Depth"))
    st = g.n("GeometryNodeTransform")
    g.l(out_sock(spine, "Mesh"), st.inputs[0])
    in_sock(st, "Rotation").default_value = (0.0, math.pi / 2.0, 0.0)
    sp = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", slen, 0.5), sp.inputs[0])
    g.l(sp.outputs[0], in_sock(st, "Translation"))
    sm = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(st, "Geometry"), sm.inputs[0])
    in_sock(sm, "Material").default_value = mats["metal"]

    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(inst, "Instances"), real.inputs[0])
    join = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(real, "Geometry"), join.inputs[0])
    g.l(out_sock(sm, "Geometry"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


# ------------------------------------------- frame/slab components ---------
# Shared vocabulary for the ISS-lineage ("frame") and UNSC/Caldari ("slab")
# ship families. Every component: +X = ship fore-aft, metres, own materials.

def build_truss_segment(mats):
    """Open box truss: 4 longerons, ring frames, alternating diagonals.
    Runs 0..Bays*Bay Length along +X (origin at the fore end)."""
    g = G("FI_TrussSegment")
    g.sock_in("Bays", "NodeSocketInt", 6, 1, 40)
    g.sock_in("Bay Length", "NodeSocketFloat", 4.0, 0.5, 20.0)
    g.sock_in("Side", "NodeSocketFloat", 3.0, 0.3, 30.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Conduits", "NodeSocketBool", True)
    BAYS, BL, S = (group_in(g, "Bays"), group_in(g, "Bay Length"),
                   group_in(g, "Side"))
    total = g.math("MULTIPLY", BAYS, BL)
    half = g.math("DIVIDE", S, 2.0)
    neg_half = g.math("MULTIPLY", half, -1.0)
    lt = g.math("MAXIMUM", g.math("MULTIPLY", S, 0.055), 0.08)
    join = g.n("GeometryNodeJoinGeometry")
    for sy in (half, neg_half):
        for sz in (half, neg_half):
            g.l(_prim(g, "cube", (total, lt, lt), None,
                      (g.math("DIVIDE", total, 2.0), sy, sz),
                      mats["truss"]), join.inputs[0])
    # ring frame instanced on bay boundaries
    ring = g.n("GeometryNodeJoinGeometry")
    for tr, dims in (((0, 0, half), (lt, S, lt)),
                     ((0, 0, neg_half), (lt, S, lt)),
                     ((0, half, 0), (lt, lt, S)),
                     ((0, neg_half, 0), (lt, lt, S))):
        g.l(_prim(g, "cube", dims, None, tr, mats["truss"]), ring.inputs[0])
    line = g.n("GeometryNodeMeshLine", mode="OFFSET")
    cnt = g.math("ADD", BAYS, 1.0)
    g.l(cnt, in_sock(line, "Count"))
    ov = g.n("ShaderNodeCombineXYZ")
    g.l(BL, ov.inputs[0])
    g.l(ov.outputs[0], in_sock(line, "Offset"))
    ri = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(line, "Mesh"), ri.inputs[0])
    g.l(out_sock(ring, "Geometry"), in_sock(ri, "Instance"))
    g.l(out_sock(ri, "Instances"), join.inputs[0])
    # diagonals, alternating, on the +/-Z faces
    hyp = g.math("SQRT", g.math("ADD", g.math("MULTIPLY", BL, BL),
                                g.math("MULTIPLY", S, S)))
    ang = g.math("ARCTAN2", S, BL)
    dline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(BAYS, in_sock(dline, "Count"))
    dv = g.n("ShaderNodeCombineXYZ")
    g.l(BL, dv.inputs[0])
    g.l(dv.outputs[0], in_sock(dline, "Offset"))
    doff = g.n("GeometryNodeTransform")
    g.l(out_sock(dline, "Mesh"), doff.inputs[0])
    dov = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("DIVIDE", BL, 2.0), dov.inputs[0])
    g.l(dov.outputs[0], in_sock(doff, "Translation"))
    dpts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(doff, "Geometry"), dpts.inputs[0])
    idx = g.n("GeometryNodeInputIndex")
    alt = g.math("SUBTRACT",
                 g.math("MULTIPLY",
                        g.math("FLOORED_MODULO", out_sock(idx, "Index"), 2.0),
                        2.0), 1.0)
    for zsgn, asgn in ((half, 1.0), (neg_half, -1.0)):
        diag = _prim(g, "cube", (hyp, lt, lt), None, (0, 0, 0),
                     mats["truss"])
        di = g.n("GeometryNodeInstanceOnPoints")
        g.l(out_sock(dpts, "Points"), di.inputs[0])
        g.l(diag, in_sock(di, "Instance"))
        rv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", g.math("MULTIPLY", ang, alt), asgn),
            rv.inputs[2])
        g.l(rv.outputs[0], in_sock(di, "Rotation"))
        dt = g.n("GeometryNodeTranslateInstances")
        g.l(out_sock(di, "Instances"), dt.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        g.l(zsgn, tv.inputs[2])
        g.l(tv.outputs[0], in_sock(dt, "Translation"))
        g.l(out_sock(dt, "Instances"), join.inputs[0])
    # conduit runs threaded through the cage (visual polish v2)
    cnd = g.n("GeometryNodeJoinGeometry")
    for fy, fz in ((0.32, 0.40), (-0.40, 0.30), (0.10, -0.40)):
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", S, 0.05), total),
                  (0, math.pi / 2, 0),
                  (g.math("DIVIDE", total, 2.0),
                   g.math("MULTIPLY", S, fy), g.math("MULTIPLY", S, fz)),
                  mats["dark"], verts=6), cnd.inputs[0])
    jline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(BAYS, in_sock(jline, "Count"))
    jv = g.n("ShaderNodeCombineXYZ")
    g.l(BL, jv.inputs[0])
    g.l(jv.outputs[0], in_sock(jline, "Offset"))
    joff = g.n("GeometryNodeTransform")
    g.l(out_sock(jline, "Mesh"), joff.inputs[0])
    jov = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("DIVIDE", BL, 2.0), jov.inputs[0])
    g.l(g.math("MULTIPLY", S, 0.32), jov.inputs[1])
    g.l(g.math("MULTIPLY", S, 0.40), jov.inputs[2])
    g.l(jov.outputs[0], in_sock(joff, "Translation"))
    jpts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(joff, "Geometry"), jpts.inputs[0])
    jbox = _prim(g, "cube", (g.math("MULTIPLY", S, 0.12),
                             g.math("MULTIPLY", S, 0.10),
                             g.math("MULTIPLY", S, 0.10)), None, None,
                 mats["metal"])
    ji = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(jpts, "Points"), ji.inputs[0])
    g.l(jbox, in_sock(ji, "Instance"))
    g.l(out_sock(ji, "Instances"), cnd.inputs[0])
    csw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Conduits"), in_sock(csw2, "Switch"))
    g.l(out_sock(cnd, "Geometry"), in_sock(csw2, "True", "GEOMETRY"))
    g.l(out_sock(csw2, "Output", "GEOMETRY"), join.inputs[0])
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(join, "Geometry"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


def build_stack_segment(mats):
    """Pressurised monocoque segment: white cylinder, ring frames, optional
    livery band (0 none / 1 red / 2 blue). Runs 0..Length along +X."""
    g = G("FI_StackSegment")
    g.sock_in("Radius", "NodeSocketFloat", 2.2, 0.2, 30.0)
    g.sock_in("Length", "NodeSocketFloat", 7.0, 0.5, 60.0)
    g.sock_in("Rings", "NodeSocketInt", 2, 0, 8)
    g.sock_in("Band", "NodeSocketInt", 0, 0, 2)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # ADDITIVE (frame wave): richer pressurised-module features
    g.sock_in("End Caps", "NodeSocketBool", False)
    g.sock_in("Windows", "NodeSocketBool", False)
    g.sock_in("Gold", "NodeSocketBool", False)
    g.sock_in("RCS", "NodeSocketBool", False)
    g.sock_in("Segments", "NodeSocketInt", 14, 6, 48)
    g.sock_in("Fabric", "NodeSocketBool", False)
    g.sock_in("Cap Style", "NodeSocketInt", 0, 0, 2)
    R, LN = group_in(g, "Radius"), group_in(g, "Length")
    SEG = group_in(g, "Segments")
    mid = g.math("DIVIDE", LN, 2.0)
    join = g.n("GeometryNodeJoinGeometry")
    hull_msw = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(group_in(g, "Gold"), hull_msw.inputs[0])
    in_sock(hull_msw, "False", "MATERIAL").default_value = mats["white"]
    in_sock(hull_msw, "True", "MATERIAL").default_value = mats["gold"]
    fab_msw = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(group_in(g, "Fabric"), fab_msw.inputs[0])
    g.l(out_sock(hull_msw, "Output", "MATERIAL"),
        in_sock(fab_msw, "False", "MATERIAL"))
    in_sock(fab_msw, "True", "MATERIAL").default_value = mats["padded"]
    hull_geo = _prim(g, "cyl", (R, LN), (0, math.pi / 2, 0), (mid, 0, 0),
                     None, verts=SEG)
    hm = g.n("GeometryNodeSetMaterial")
    g.l(hull_geo, hm.inputs[0])
    g.l(out_sock(fab_msw, "Output", "MATERIAL"), in_sock(hm, "Material"))
    g.l(out_sock(hm, "Geometry"), join.inputs[0])

    # end caps: 0 dome / 1 flat bulkhead / 2 conical taper (per style)
    def cap_variant(x_v, outward_sign):
        dome = _prim(g, "sphere", (g.math("MULTIPLY", R, 0.92),), None,
                     (x_v, 0, 0), mats["white"], verts=SEG)
        bulk = _prim(g, "cyl", (g.math("MULTIPLY", R, 1.05),
                                g.math("MULTIPLY", R, 0.15)),
                     (0, math.pi / 2, 0), (x_v, 0, 0), mats["truss"],
                     verts=SEG)
        taper = _prim(g, "cone", (g.math("MULTIPLY", R, 0.55), R,
                                  g.math("MULTIPLY", R, 0.6)),
                      (0, outward_sign * math.pi / 2, 0), (x_v, 0, 0),
                      mats["white"], verts=SEG)
        c1 = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(group_in(g, "Cap Style"), in_sock(c1, "A", "INT"))
        in_sock(c1, "B", "INT").default_value = 1
        s1 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(out_sock(c1, "Result"), in_sock(s1, "Switch"))
        g.l(dome, in_sock(s1, "False", "GEOMETRY"))
        g.l(bulk, in_sock(s1, "True", "GEOMETRY"))
        c2 = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(group_in(g, "Cap Style"), in_sock(c2, "A", "INT"))
        in_sock(c2, "B", "INT").default_value = 2
        s2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(out_sock(c2, "Result"), in_sock(s2, "Switch"))
        g.l(out_sock(s1, "Output", "GEOMETRY"),
            in_sock(s2, "False", "GEOMETRY"))
        g.l(taper, in_sock(s2, "True", "GEOMETRY"))
        return out_sock(s2, "Output", "GEOMETRY")
    caps = g.n("GeometryNodeJoinGeometry")
    g.l(cap_variant(0.0, -1.0), caps.inputs[0])
    g.l(cap_variant(LN, 1.0), caps.inputs[0])
    csw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "End Caps"), in_sock(csw, "Switch"))
    g.l(out_sock(caps, "Geometry"), in_sock(csw, "True", "GEOMETRY"))
    g.l(out_sock(csw, "Output", "GEOMETRY"), join.inputs[0])

    # realistic portholes: BOTH flanks, deck line (z=+0.30R), inset glass
    # with a frame ring; count follows module length
    wins = g.n("GeometryNodeJoinGeometry")
    n_win = g.math("MINIMUM", g.math("FLOOR", g.math("DIVIDE", LN, 1.1)),
                   6.0)
    wy = g.math("MULTIPLY", R, 0.954)   # cos(asin(0.30)) on the shell
    wz = g.math("MULTIPLY", R, 0.30)
    pr = g.math("MAXIMUM", g.math("MULTIPLY", R, 0.075), 0.09)
    for i in range(6):
        gate = g.math("LESS_THAN", i + 0.5, n_win)
        px = g.math("MULTIPLY", LN, 0.15 + i * 0.14)
        pair = g.n("GeometryNodeJoinGeometry")
        for sgn in (1.0, -1.0):
            yv = g.math("MULTIPLY", wy, sgn)
            pair_in = _prim(g, "cyl", (pr, g.math("MULTIPLY", R, 0.30)),
                            (math.pi / 2, 0, 0), (px, yv, wz),
                            mats["window"], verts=10)
            g.l(pair_in, pair.inputs[0])
            g.l(_prim(g, "cyl", (g.math("MULTIPLY", pr, 1.4),
                                 g.math("MULTIPLY", R, 0.10)),
                      (math.pi / 2, 0, 0),
                      (px, g.math("MULTIPLY", yv, 1.02), wz),
                      mats["truss"], verts=10), pair.inputs[0])
        gsw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(gate, in_sock(gsw2, "Switch"))
        g.l(out_sock(pair, "Geometry"), in_sock(gsw2, "True", "GEOMETRY"))
        g.l(out_sock(gsw2, "Output", "GEOMETRY"), wins.inputs[0])
    wsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Windows"), in_sock(wsw, "Switch"))
    g.l(out_sock(wins, "Geometry"), in_sock(wsw, "True", "GEOMETRY"))
    g.l(out_sock(wsw, "Output", "GEOMETRY"), join.inputs[0])

    # 4 RCS quad blocks around the fore end
    rcsj = g.n("GeometryNodeJoinGeometry")
    for ang in (0.785, 2.356, 3.927, 5.498):
        yv = g.math("MULTIPLY", R, 0.98 * math.cos(ang))
        zv = g.math("MULTIPLY", R, 0.98 * math.sin(ang))
        g.l(_prim(g, "cube", (0.5, 0.32, 0.32), None,
                  (g.math("MULTIPLY", LN, 0.10), yv, zv),
                  mats["dark"]), rcsj.inputs[0])
    rsw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "RCS"), in_sock(rsw2, "Switch"))
    g.l(out_sock(rcsj, "Geometry"), in_sock(rsw2, "True", "GEOMETRY"))
    g.l(out_sock(rsw2, "Output", "GEOMETRY"), join.inputs[0])
    # ring frames
    rline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Rings"), in_sock(rline, "Count"))
    spacing = g.math("DIVIDE", LN, g.math("ADD", group_in(g, "Rings"), 1.0))
    rv = g.n("ShaderNodeCombineXYZ")
    g.l(spacing, rv.inputs[0])
    g.l(rv.outputs[0], in_sock(rline, "Offset"))
    roff = g.n("GeometryNodeTransform")
    g.l(out_sock(rline, "Mesh"), roff.inputs[0])
    rov = g.n("ShaderNodeCombineXYZ")
    g.l(spacing, rov.inputs[0])
    g.l(rov.outputs[0], in_sock(roff, "Translation"))
    rpts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(roff, "Geometry"), rpts.inputs[0])
    frame = _prim(g, "cyl", (g.math("MULTIPLY", R, 1.05), 0.35),
                  (0, math.pi / 2, 0), None, mats["truss"], verts=SEG)
    fi = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(rpts, "Points"), fi.inputs[0])
    g.l(frame, in_sock(fi, "Instance"))
    g.l(out_sock(fi, "Instances"), join.inputs[0])
    # livery band
    band_geo = _prim(g, "cyl", (g.math("MULTIPLY", R, 1.02), 0.9),
                     (0, math.pi / 2, 0),
                     (g.math("MULTIPLY", LN, 0.78), 0, 0), None, verts=SEG)
    msw = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    is_blue = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
    g.l(group_in(g, "Band"), in_sock(is_blue, "A", "INT"))
    in_sock(is_blue, "B", "INT").default_value = 2
    g.l(out_sock(is_blue, "Result"), msw.inputs[0])
    in_sock(msw, "False", "MATERIAL").default_value = mats["red"]
    in_sock(msw, "True", "MATERIAL").default_value = mats["blue"]
    bm = g.n("GeometryNodeSetMaterial")
    g.l(band_geo, bm.inputs[0])
    g.l(out_sock(msw, "Output", "MATERIAL"), in_sock(bm, "Material"))
    has_band = g.n("FunctionNodeCompare", data_type="INT",
                   operation="GREATER_THAN")
    g.l(group_in(g, "Band"), in_sock(has_band, "A", "INT"))
    in_sock(has_band, "B", "INT").default_value = 0
    bsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(out_sock(has_band, "Result"), in_sock(bsw, "Switch"))
    g.l(out_sock(bm, "Geometry"), in_sock(bsw, "True", "GEOMETRY"))
    g.l(out_sock(bsw, "Output", "GEOMETRY"), join.inputs[0])
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(join, "Geometry"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


def build_tank_cluster(mats):
    g = G("FI_TankCluster")
    g.sock_in("Count", "NodeSocketInt", 2, 1, 8)
    g.sock_in("Radius", "NodeSocketFloat", 1.6, 0.2, 12.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    R = group_in(g, "Radius")
    pitch = g.math("MULTIPLY", R, 2.3)
    line = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Count"), in_sock(line, "Count"))
    ov = g.n("ShaderNodeCombineXYZ")
    g.l(pitch, ov.inputs[0])
    g.l(ov.outputs[0], in_sock(line, "Offset"))
    tank = _prim(g, "sphere", (R,), None, None, mats["gold"], verts=12)
    ti = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(line, "Mesh"), ti.inputs[0])
    g.l(tank, in_sock(ti, "Instance"))
    join = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(ti, "Instances"), join.inputs[0])
    rod_len = g.math("MULTIPLY", pitch, group_in(g, "Count"))
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.12), rod_len),
              (0, math.pi / 2, 0),
              (g.math("MULTIPLY", rod_len, 0.4), 0, 0),
              mats["truss"], verts=6), join.inputs[0])
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(join, "Geometry"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


def build_solar_array(mats):
    """Panel wing along +Y. Amber flips the ISS-copper look; Radiator flips
    to the glowing thermal-wing material (wins over Amber)."""
    g = G("FI_SolarArray")
    g.sock_in("Panels", "NodeSocketInt", 4, 1, 12)
    g.sock_in("Panel Length", "NodeSocketFloat", 3.2, 0.5, 20.0)
    g.sock_in("Panel Width", "NodeSocketFloat", 2.2, 0.3, 12.0)
    g.sock_in("Amber", "NodeSocketBool", False)
    g.sock_in("Radiator", "NodeSocketBool", False)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # ADDITIVE (visual polish v2): accordion fold + hinge hardware
    g.sock_in("Fold (deg)", "NodeSocketFloat", 22.0, 0.0, 70.0)
    g.sock_in("Hinges", "NodeSocketBool", True)
    PN, PL, PW = (group_in(g, "Panels"), group_in(g, "Panel Length"),
                  group_in(g, "Panel Width"))
    foldr = g.math("RADIANS", group_in(g, "Fold (deg)"))
    cosf = g.math("COSINE", foldr)
    sinf = g.math("SINE", foldr)
    # TRUE zig-zag: hinges alternate between z=0 and z=PL*sin(fold); every
    # panel CENTER sits at the same z=(PL/2)sin(fold); only tilt alternates.
    # First hinge is at the array root, on the boom line ("the middle").
    pitch = g.math("ADD", g.math("MULTIPLY", PL, cosf), 0.02)
    rise = g.math("MULTIPLY", PL, sinf)
    boom_len = g.math("ADD", g.math("MULTIPLY", pitch, PN), 1.2)
    join = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (0.12, boom_len), (math.pi / 2, 0, 0),
              (0, g.math("MULTIPLY", boom_len, 0.5), 0),
              mats["truss"], verts=8), join.inputs[0])
    m1 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(group_in(g, "Amber"), m1.inputs[0])
    in_sock(m1, "False", "MATERIAL").default_value = mats["solar"]
    in_sock(m1, "True", "MATERIAL").default_value = mats["amber"]
    m2 = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    g.l(group_in(g, "Radiator"), m2.inputs[0])
    g.l(out_sock(m1, "Output", "MATERIAL"), in_sock(m2, "False", "MATERIAL"))
    in_sock(m2, "True", "MATERIAL").default_value = mats["radiator"]
    panel = _prim(g, "cube", (PW, PL, 0.07), None, None, None)
    pm = g.n("GeometryNodeSetMaterial")
    g.l(panel, pm.inputs[0])
    g.l(out_sock(m2, "Output", "MATERIAL"), in_sock(pm, "Material"))
    pline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(PN, in_sock(pline, "Count"))
    pv = g.n("ShaderNodeCombineXYZ")
    g.l(pitch, pv.inputs[1])
    g.l(pv.outputs[0], in_sock(pline, "Offset"))
    poff = g.n("GeometryNodeTransform")
    g.l(out_sock(pline, "Mesh"), poff.inputs[0])
    pov = g.n("ShaderNodeCombineXYZ")
    # first panel centre = root hinge (y=0.55, boom level) + half pitch
    g.l(g.math("ADD", 0.55, g.math("MULTIPLY", pitch, 0.5)), pov.inputs[1])
    g.l(g.math("MULTIPLY", rise, 0.5), pov.inputs[2])   # constant centre z
    g.l(pov.outputs[0], in_sock(poff, "Translation"))
    ppts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(poff, "Geometry"), ppts.inputs[0])
    idx = g.n("GeometryNodeInputIndex")
    alt = g.math("SUBTRACT", g.math("MULTIPLY",
          g.math("FLOORED_MODULO", out_sock(idx, "Index"), 2.0), 2.0), 1.0)
    prot = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", g.math("MULTIPLY", alt, foldr), -1.0),
        prot.inputs[0])
    pi = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(ppts, "Points"), pi.inputs[0])
    g.l(out_sock(pm, "Geometry"), in_sock(pi, "Instance"))
    g.l(prot.outputs[0], in_sock(pi, "Rotation"))
    g.l(out_sock(pi, "Instances"), join.inputs[0])
    # hinge rods FOLLOW the zig-zag: alternate z between 0 and rise
    hline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(g.math("ADD", PN, 1.0), in_sock(hline, "Count"))
    hv = g.n("ShaderNodeCombineXYZ")
    g.l(pitch, hv.inputs[1])
    g.l(hv.outputs[0], in_sock(hline, "Offset"))
    hoff = g.n("GeometryNodeTransform")
    g.l(out_sock(hline, "Mesh"), hoff.inputs[0])
    hov = g.n("ShaderNodeCombineXYZ")
    hov.inputs[1].default_value = 0.55
    g.l(hov.outputs[0], in_sock(hoff, "Translation"))
    hpts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(hoff, "Geometry"), hpts.inputs[0])
    hidx = g.n("GeometryNodeInputIndex")
    hz = g.math("MULTIPLY",
                g.math("FLOORED_MODULO", out_sock(hidx, "Index"), 2.0),
                rise)
    hzv = g.n("ShaderNodeCombineXYZ")
    g.l(hz, hzv.inputs[2])
    hset = g.n("GeometryNodeSetPosition")
    g.l(out_sock(hpts, "Points"), hset.inputs[0])
    g.l(hzv.outputs[0], in_sock(hset, "Offset"))
    rod = _prim(g, "cyl", (0.05, g.math("MULTIPLY", PW, 1.04)),
                (0, math.pi / 2, 0), None, mats["truss"], verts=8)
    hi_ = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(hset, "Geometry"), hi_.inputs[0])
    g.l(rod, in_sock(hi_, "Instance"))
    hsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Hinges"), in_sock(hsw, "Switch"))
    g.l(out_sock(hi_, "Instances"), in_sock(hsw, "True", "GEOMETRY"))
    g.l(out_sock(hsw, "Output", "GEOMETRY"), join.inputs[0])
    # blanket box at the root + tension wires at mid zig-zag height
    g.l(_prim(g, "cube", (g.math("MULTIPLY", PW, 0.92), 0.6, 0.42),
              None, (0.0, 0.22, 0.0), mats["truss"]), join.inputs[0])
    for zs in (0.1, -0.1):
        wz = g.math("ADD", g.math("MULTIPLY", rise, 0.5), zs)
        g.l(_prim(g, "cyl", (0.02, g.math("MULTIPLY", boom_len, 0.96)),
                  (math.pi / 2, 0, 0),
                  (0.0, g.math("MULTIPLY", boom_len, 0.5), wz),
                  mats["dark"], verts=6), join.inputs[0])
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(join, "Geometry"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


def build_ring_hab(mats):
    """Wheel habitat: N tangent segments + spokes + hub, in the YZ plane."""
    g = G("FI_RingHab")
    g.sock_in("Radius", "NodeSocketFloat", 9.0, 1.0, 80.0)
    g.sock_in("Segments", "NodeSocketInt", 8, 4, 24)
    g.sock_in("Tube Radius", "NodeSocketFloat", 1.1, 0.2, 8.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Tube Verts", "NodeSocketInt", 10, 6, 48)
    R, SEG, TR = (group_in(g, "Radius"), group_in(g, "Segments"),
                  group_in(g, "Tube Radius"))
    TV = group_in(g, "Tube Verts")
    join = g.n("GeometryNodeJoinGeometry")
    pts = g.n("GeometryNodePoints")
    g.l(SEG, in_sock(pts, "Count"))
    idx = g.n("GeometryNodeInputIndex")
    theta = g.math("MULTIPLY",
                   g.math("DIVIDE", out_sock(idx, "Index"), SEG), TAU)
    py = g.math("MULTIPLY", g.math("COSINE", theta), R)
    pz = g.math("MULTIPLY", g.math("SINE", theta), R)
    pv = g.n("ShaderNodeCombineXYZ")
    g.l(py, pv.inputs[1])
    g.l(pz, pv.inputs[2])
    g.l(pv.outputs[0], in_sock(pts, "Position"))
    chord = g.math("MULTIPLY",
                   g.math("MULTIPLY", R, 2.0),
                   g.math("SINE", g.math("DIVIDE", math.pi, SEG)))
    seg = _prim(g, "cyl", (TR, g.math("MULTIPLY", chord, 1.08)), None, None,
                mats["padded"], verts=TV)
    si = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(pts, "Points"), si.inputs[0])
    g.l(seg, in_sock(si, "Instance"))
    rv = g.n("ShaderNodeCombineXYZ")
    g.l(theta, rv.inputs[0])
    g.l(rv.outputs[0], in_sock(si, "Rotation"))
    g.l(out_sock(si, "Instances"), join.inputs[0])
    for th in (0.0, math.pi / 2):
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", TR, 0.25),
                             g.math("MULTIPLY", R, 2.0)),
                  (th, 0, 0), None, mats["truss"], verts=6), join.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", TR, 1.3), 2.2),
              (0, math.pi / 2, 0), None, mats["white"], verts=10),
        join.inputs[0])
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(join, "Geometry"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


def build_docking_node(mats):
    g = G("FI_DockingNode")
    g.sock_in("Size", "NodeSocketFloat", 1.6, 0.3, 10.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    S = group_in(g, "Size")
    join = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (S, S, S), None, None, mats["white"]),
        join.inputs[0])
    stub_r = g.math("MULTIPLY", S, 0.28)
    stub_l = g.math("MULTIPLY", S, 0.45)
    off = g.math("MULTIPLY", S, 0.62)
    noff = g.math("MULTIPLY", off, -1.0)
    tip = g.math("MULTIPLY", S, 0.84)
    ntip = g.math("MULTIPLY", tip, -1.0)
    for rot, tr, tt in (((0, math.pi / 2, 0), (off, 0, 0), (tip, 0, 0)),
                        ((0, math.pi / 2, 0), (noff, 0, 0), (ntip, 0, 0)),
                        ((math.pi / 2, 0, 0), (0, off, 0), (0, tip, 0)),
                        ((math.pi / 2, 0, 0), (0, noff, 0), (0, ntip, 0)),
                        ((0, 0, 0), (0, 0, off), (0, 0, tip)),
                        ((0, 0, 0), (0, 0, noff), (0, 0, ntip))):
        g.l(_prim(g, "cyl", (stub_r, stub_l), rot, tr, mats["truss"],
                  verts=8), join.inputs[0])
        # APAS-style petal flange at the port lip
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", stub_r, 1.45),
                             g.math("MULTIPLY", S, 0.05)), rot, tt,
                  mats["metal"], verts=8), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_dish_antenna(mats):
    g = G("FI_DishAntenna")
    g.sock_in("Dish Radius", "NodeSocketFloat", 1.4, 0.2, 10.0)
    g.sock_in("Boom", "NodeSocketFloat", 1.2, 0.0, 12.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    R, BM = group_in(g, "Dish Radius"), group_in(g, "Boom")
    join = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (0.08, BM), (0, math.pi / 2, 0),
              (g.math("MULTIPLY", BM, 0.5), 0, 0), mats["truss"], verts=6),
        join.inputs[0])
    g.l(_prim(g, "cone", (0.02, R, g.math("MULTIPLY", R, 0.4)),
              (0, -math.pi / 2, 0), (BM, 0, 0), mats["white"], verts=14),
        join.inputs[0])
    g.l(_prim(g, "cyl", (0.04, g.math("MULTIPLY", R, 0.5)),
              (0, math.pi / 2, 0),
              (g.math("ADD", BM, g.math("MULTIPLY", R, 0.3)), 0, 0),
              mats["dark"], verts=6), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


# --------------------------------------------- frame spine sections --------
# Every section: origin at the FORE end, geometry extends +X for its length.
# Standard inputs (Unit = bay unit, Radius = module radius, Seed).

def build_tank_bay(mats, kit):
    g = G("FI_TankBay")
    g.sock_in("Unit", "NodeSocketFloat", 4.0, 0.3, 40.0)
    g.sock_in("Radius", "NodeSocketFloat", 2.2, 0.2, 30.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Segments", "NodeSocketInt", 12, 6, 48)
    U, R = group_in(g, "Unit"), group_in(g, "Radius")
    SEG = group_in(g, "Segments")
    join = g.n("GeometryNodeJoinGeometry")
    truss = gcall(g, kit["truss"], wires={
        "Bay Length": U, "Side": g.math("MULTIPLY", R, 2.1)},
        values={"Bays": 3})
    g.l(out_sock(truss, "Geometry"), join.inputs[0])
    jit = g.rand_float(-0.2, 0.2, None, g.math("ADD", group_in(g, "Seed"),
                                               61.0))
    for fx, rmul in ((0.8, 0.85), (2.2, 0.85)):
        x = g.math("MULTIPLY", U, g.math("ADD", fx, jit))
        g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, rmul),), None,
                  (x, 0, 0), mats["gold"], verts=SEG), join.inputs[0])
    g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, 0.45),), None,
              (g.math("MULTIPLY", U, 1.5), 0,
               g.math("MULTIPLY", R, -0.9)), mats["gold"], verts=SEG),
        join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_container_rack(mats, kit):
    g = G("FI_ContainerRack")
    g.sock_in("Unit", "NodeSocketFloat", 4.0, 0.3, 40.0)
    g.sock_in("Radius", "NodeSocketFloat", 2.2, 0.2, 30.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    U, R = group_in(g, "Unit"), group_in(g, "Radius")
    join = g.n("GeometryNodeJoinGeometry")
    truss = gcall(g, kit["truss"], wires={
        "Bay Length": U, "Side": g.math("MULTIPLY", R, 2.1)},
        values={"Bays": 3})
    g.l(out_sock(truss, "Geometry"), join.inputs[0])
    for col in (0.5, 1.5, 2.5):
        for zf in (0.52, -0.52):
            g.l(_prim(g, "cube",
                      (g.math("MULTIPLY", U, 0.82),
                       g.math("MULTIPLY", R, 1.45),
                       g.math("MULTIPLY", R, 0.92)), None,
                      (g.math("MULTIPLY", U, col), 0,
                       g.math("MULTIPLY", R, zf)),
                      mats["dark"]), join.inputs[0])
    # one seeded accent container (cargo livery)
    acc_col = g.math("ADD", 0.5, g.math("FLOOR",
              g.rand_float(0.0, 2.99, None,
                           g.math("ADD", group_in(g, "Seed"), 67.0))))
    msw = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    pick = g.math("GREATER_THAN",
                  g.rand_float(0.0, 1.0, None,
                               g.math("ADD", group_in(g, "Seed"), 68.0)),
                  0.5)
    g.l(pick, msw.inputs[0])
    in_sock(msw, "False", "MATERIAL").default_value = mats["red"]
    in_sock(msw, "True", "MATERIAL").default_value = mats["blue"]
    acc = _prim(g, "cube", (g.math("MULTIPLY", U, 0.82),
                            g.math("MULTIPLY", R, 1.45),
                            g.math("MULTIPLY", R, 0.92)), None,
                (g.math("MULTIPLY", U, acc_col), 0, 0.0), None)
    accm = g.n("GeometryNodeSetMaterial")
    g.l(acc, accm.inputs[0])
    g.l(out_sock(msw, "Output", "MATERIAL"), in_sock(accm, "Material"))
    g.l(out_sock(accm, "Geometry"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_node_section(mats, kit):
    """Docking node + up to 4 radial stub modules + cupola + docked craft."""
    g = G("FI_NodeSection")
    g.sock_in("Radius", "NodeSocketFloat", 2.2, 0.2, 30.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Radial Count", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Docked Craft", "NodeSocketBool", False)
    g.sock_in("Cupola", "NodeSocketBool", True)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # length contract (production polish): section spans EXACTLY [0, Length]
    g.sock_in("Length", "NodeSocketFloat", 4.0, 0.5, 60.0)
    R = group_in(g, "Radius")
    LEN = group_in(g, "Length")
    cx = g.math("MULTIPLY", LEN, 0.5)  # node centre
    join = g.n("GeometryNodeJoinGeometry")
    # connector corridor tubes reach both boundaries — no gaps possible
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.45), LEN),
              (0, math.pi / 2, 0), (cx, 0, 0), mats["hull"], verts=10),
        join.inputs[0])
    node = gcall(g, kit["docknode"], wires={
        "Size": g.math("MULTIPLY", R, 1.5)})
    nmv = g.n("GeometryNodeTransform")
    g.l(out_sock(node, "Geometry"), nmv.inputs[0])
    ntv = g.n("ShaderNodeCombineXYZ")
    g.l(cx, ntv.inputs[0])
    g.l(ntv.outputs[0], in_sock(nmv, "Translation"))
    g.l(out_sock(nmv, "Geometry"), join.inputs[0])
    # radial stub modules at 90 deg spacing, gated by Radial Count
    for i in range(4):
        ang = i * math.pi / 2.0
        stub = g.n("GeometryNodeJoinGeometry")
        yv = g.math("MULTIPLY", R, 1.6 * math.cos(ang))
        zv = g.math("MULTIPLY", R, 1.6 * math.sin(ang))
        rot = (math.pi / 2.0 if i % 2 == 0 else 0.0, 0.0, 0.0) \
            if i in (0, 2) else (math.pi / 2.0, 0.0, 0.0)
        rot = (math.pi / 2.0, 0.0, 0.0) if i in (0, 2) else (0.0, 0.0, 0.0)
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.55),
                             g.math("MULTIPLY", R, 1.7)),
                  rot, (cx, yv, zv), mats["padded"], verts=10),
            stub.inputs[0])
        g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, 0.50),), None,
                  (cx, g.math("MULTIPLY", yv, 1.55),
                   g.math("MULTIPLY", zv, 1.55)),
                  mats["white"], verts=10), stub.inputs[0])
        gate = g.n("FunctionNodeCompare", data_type="INT",
                   operation="GREATER_THAN")
        g.l(group_in(g, "Radial Count"), in_sock(gate, "A", "INT"))
        in_sock(gate, "B", "INT").default_value = i
        ssw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(out_sock(gate, "Result"), in_sock(ssw, "Switch"))
        g.l(out_sock(stub, "Geometry"), in_sock(ssw, "True", "GEOMETRY"))
        g.l(out_sock(ssw, "Output", "GEOMETRY"), join.inputs[0])
    # cupola: glass dome + base ring + crossed frame ribs (multi-pane read)
    cup_join = g.n("GeometryNodeJoinGeometry")
    cup_x = g.math("MULTIPLY", R, 0.55)
    cup_z = g.math("MULTIPLY", R, 1.45)
    g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, 0.45),), None,
              (cup_x, 0, cup_z), mats["glass"], verts=10),
        cup_join.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.48),
                         g.math("MULTIPLY", R, 0.10)), None,
              (cup_x, 0, cup_z), mats["truss"], verts=12),
        cup_join.inputs[0])
    for rib_rot in (0.0, math.pi / 2.0):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", R, 0.95), 0.045, 0.05),
                  (0.0, 0.0, rib_rot),
                  (cup_x, 0, g.math("ADD", cup_z,
                                    g.math("MULTIPLY", R, 0.30))),
                  mats["truss"]), cup_join.inputs[0])
    cusw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Cupola"), in_sock(cusw, "Switch"))
    g.l(out_sock(cup_join, "Geometry"), in_sock(cusw, "True", "GEOMETRY"))
    g.l(out_sock(cusw, "Output", "GEOMETRY"), join.inputs[0])
    # docked crew capsule below (-Z port)
    dc = g.n("GeometryNodeJoinGeometry")
    dz = g.math("MULTIPLY", R, -2.6)
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.42),
                         g.math("MULTIPLY", R, 1.1)),
              (0, math.pi / 2, 0), (cx, 0, dz), mats["padded"], verts=10),
        dc.inputs[0])
    g.l(_prim(g, "cone", (0.02, g.math("MULTIPLY", R, 0.40),
                          g.math("MULTIPLY", R, 0.5)),
              (0, math.pi / 2, 0),
              (g.math("ADD", cx, g.math("MULTIPLY", R, 0.8)), 0, dz),
              mats["gold"], verts=10), dc.inputs[0])
    dcsw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "Docked Craft"), in_sock(dcsw, "Switch"))
    g.l(out_sock(dc, "Geometry"), in_sock(dcsw, "True", "GEOMETRY"))
    g.l(out_sock(dcsw, "Output", "GEOMETRY"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_reactor_section(mats, kit):
    """Shadow shield + reactor drum + radial fin radiators + gold cap."""
    g = G("FI_ReactorSection")
    g.sock_in("Unit", "NodeSocketFloat", 4.0, 0.3, 40.0)
    g.sock_in("Radius", "NodeSocketFloat", 2.2, 0.2, 30.0)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # length contract; shield now on the FORE (crew) side, x = Length
    g.sock_in("Length", "NodeSocketFloat", 8.0, 0.5, 60.0)
    R = group_in(g, "Radius")
    LEN = group_in(g, "Length")
    join = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.40), LEN),
              (0, math.pi / 2, 0), (g.math("MULTIPLY", LEN, 0.5), 0, 0),
              mats["dark"], verts=10), join.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 2.0),
                         g.math("MULTIPLY", LEN, 0.06)),
              (0, math.pi / 2, 0), (g.math("MULTIPLY", LEN, 0.93), 0, 0),
              mats["truss"], verts=14), join.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 0.85),
                         g.math("MULTIPLY", LEN, 0.60)),
              (0, math.pi / 2, 0), (g.math("MULTIPLY", LEN, 0.45), 0, 0),
              mats["dark"], verts=12), join.inputs[0])
    for i in range(8):
        ang = i * math.pi / 4.0
        fin = _prim(g, "cube",
                    (g.math("MULTIPLY", LEN, 0.50), 0.06,
                     g.math("MULTIPLY", R, 1.3)), None, None,
                    mats["radiator"])
        ft = g.n("GeometryNodeTransform")
        g.l(fin, ft.inputs[0])
        in_sock(ft, "Rotation").default_value = (ang, 0.0, 0.0)
        fv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", LEN, 0.45), fv.inputs[0])
        g.l(g.math("MULTIPLY", R, -1.35 * math.sin(ang)), fv.inputs[1])
        g.l(g.math("MULTIPLY", R, 1.35 * math.cos(ang)), fv.inputs[2])
        g.l(fv.outputs[0], in_sock(ft, "Translation"))
        g.l(out_sock(ft, "Geometry"), join.inputs[0])
    g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, 0.6),), None,
              (g.math("MULTIPLY", LEN, 0.08), 0, 0), mats["gold"],
              verts=10), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_spoke_wheel(mats, kit):
    """Hermes-style wheel: hub + radial arms + tangent hab capsules."""
    g = G("FI_SpokeWheel")
    g.sock_in("Radius", "NodeSocketFloat", 8.0, 1.0, 80.0)
    g.sock_in("Arms", "NodeSocketInt", 4, 2, 8)
    g.sock_in("Capsule Radius", "NodeSocketFloat", 1.0, 0.2, 8.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Capsule Verts", "NodeSocketInt", 12, 6, 48)
    R, N, CR = (group_in(g, "Radius"), group_in(g, "Arms"),
                group_in(g, "Capsule Radius"))
    CV = group_in(g, "Capsule Verts")
    join = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", CR, 1.2),
                         g.math("MULTIPLY", CR, 1.8)),
              (0, math.pi / 2, 0), None, mats["white"], verts=12),
        join.inputs[0])
    pts = g.n("GeometryNodePoints")
    g.l(N, in_sock(pts, "Count"))
    idx = g.n("GeometryNodeInputIndex")
    theta = g.math("MULTIPLY", g.math("DIVIDE", out_sock(idx, "Index"), N),
                   TAU)
    py = g.math("MULTIPLY", g.math("COSINE", theta), R)
    pz = g.math("MULTIPLY", g.math("SINE", theta), R)
    pv = g.n("ShaderNodeCombineXYZ")
    g.l(py, pv.inputs[1])
    g.l(pz, pv.inputs[2])
    g.l(pv.outputs[0], in_sock(pts, "Position"))
    rotv = g.n("ShaderNodeCombineXYZ")
    g.l(theta, rotv.inputs[0])
    # arm: from hub to capsule, instanced at half radius
    arm = _prim(g, "cyl", (g.math("MULTIPLY", CR, 0.22), R), None, None,
                mats["truss"], verts=8)
    apts = g.n("GeometryNodePoints")
    g.l(N, in_sock(apts, "Count"))
    apv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", py, 0.5), apv.inputs[1])
    g.l(g.math("MULTIPLY", pz, 0.5), apv.inputs[2])
    g.l(apv.outputs[0], in_sock(apts, "Position"))
    ai = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(apts, "Points"), ai.inputs[0])
    g.l(arm, in_sock(ai, "Instance"))
    g.l(rotv.outputs[0], in_sock(ai, "Rotation"))
    g.l(out_sock(ai, "Instances"), join.inputs[0])
    # capsule: cylinder + dome ends, tangent
    cap = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cyl", (CR, g.math("MULTIPLY", CR, 3.0)), None, None,
              mats["padded"], verts=CV), cap.inputs[0])
    for sgn in (1.5, -1.5):
        g.l(_prim(g, "sphere", (g.math("MULTIPLY", CR, 0.95),), None,
                  (0, 0, g.math("MULTIPLY", CR, sgn)), mats["white"],
                  verts=CV), cap.inputs[0])
    ci = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(pts, "Points"), ci.inputs[0])
    g.l(out_sock(cap, "Geometry"), in_sock(ci, "Instance"))
    g.l(rotv.outputs[0], in_sock(ci, "Rotation"))
    g.l(out_sock(ci, "Instances"), join.inputs[0])
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(join, "Geometry"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


def build_engine_section(mats, kit):
    """Stern assembly: taper struts, shadow disc, tanks, engine cluster.
    Runs 0..2*Unit along +X; exhaust exits the x=0 end (-X)."""
    g = G("FI_EngineSection")
    g.sock_in("Unit", "NodeSocketFloat", 4.0, 0.3, 40.0)
    g.sock_in("Radius", "NodeSocketFloat", 2.2, 0.2, 30.0)
    g.sock_in("Count", "NodeSocketInt", 3, 1, 9)
    g.sock_in("Type", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    g.sock_in("Segments", "NodeSocketInt", 12, 6, 48)
    g.sock_in("Length", "NodeSocketFloat", 8.0, 0.5, 60.0)
    R = group_in(g, "Radius")
    LEN = group_in(g, "Length")
    join = g.n("GeometryNodeJoinGeometry")
    # GN Mesh Cone spans [0, depth] from its base — NOT centred
    g.l(_prim(g, "cone", (g.math("MULTIPLY", R, 1.15),
                          g.math("MULTIPLY", R, 0.62),
                          g.math("MULTIPLY", LEN, 0.45)),
              (0, math.pi / 2, 0), (g.math("MULTIPLY", LEN, 0.50), 0, 0),
              mats["truss"], verts=10), join.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 1.8),
                         g.math("MULTIPLY", LEN, 0.05)),
              (0, math.pi / 2, 0), (g.math("MULTIPLY", LEN, 0.94), 0, 0),
              mats["truss"], verts=14), join.inputs[0])
    for sgn in (1.0, -1.0):
        g.l(_prim(g, "sphere", (g.math("MULTIPLY", R, 0.55),), None,
                  (g.math("MULTIPLY", LEN, 0.58),
                   g.math("MULTIPLY", R, 0.85 * sgn), 0),
                  mats["gold"], verts=10), join.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", R, 1.45),
                         g.math("MULTIPLY", LEN, 0.015)),
              (0, math.pi / 2, 0), (g.math("MULTIPLY", LEN, 0.47), 0, 0),
              mats["dark"], verts=14), join.inputs[0])
    eng = gcall(g, kit["engine"], wires={
        "Count": group_in(g, "Count"),
        "Ring Radius": g.math("MULTIPLY", R, 0.7),
        "Bell Radius": g.math("MULTIPLY", R, 0.48),
        "Bell Length": g.math("MULTIPLY", LEN, 0.42),
        "Type": group_in(g, "Type"),
        "Segments": group_in(g, "Segments")})
    emv = g.n("GeometryNodeTransform")
    g.l(out_sock(eng, "Geometry"), emv.inputs[0])
    etv = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", LEN, 0.25), etv.inputs[0])
    g.l(etv.outputs[0], in_sock(emv, "Translation"))
    g.l(out_sock(emv, "Geometry"), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


# ----------------------------------------------- whole-ship generator ------

def build_coupler(mats, kit):
    """Inter-section collar: frustum from R Aft (x=0) to R Fore (x=Length),
    rim rings + 4 clamp lugs. Placed across every section boundary — the
    joints read deliberate and radius steps get proper adapters."""
    g = G("FI_Coupler")
    g.sock_in("R Fore", "NodeSocketFloat", 2.2, 0.05, 30.0)
    g.sock_in("R Aft", "NodeSocketFloat", 2.2, 0.05, 30.0)
    g.sock_in("Length", "NodeSocketFloat", 1.4, 0.1, 20.0)
    g.sock_in("Segments", "NodeSocketInt", 14, 6, 48)
    g.sock_out("Geometry", "NodeSocketGeometry")
    RF, RA, LEN = (group_in(g, "R Fore"), group_in(g, "R Aft"),
                   group_in(g, "Length"))
    join = g.n("GeometryNodeJoinGeometry")
    cone = g.n("GeometryNodeMeshCone")
    g.l(group_in(g, "Segments"), in_sock(cone, "Vertices"))
    g.l(RF, in_sock(cone, "Radius Top", "VALUE"))
    g.l(RA, in_sock(cone, "Radius Bottom", "VALUE"))
    g.l(LEN, in_sock(cone, "Depth", "VALUE"))
    ct = g.n("GeometryNodeTransform")
    g.l(out_sock(cone, "Mesh"), ct.inputs[0])
    in_sock(ct, "Rotation").default_value = (0.0, math.pi / 2.0, 0.0)
    # GN cone spans [0, depth] after the +90 Y rotation — already in place
    sm = g.n("GeometryNodeSetShadeSmooth")
    g.l(out_sock(ct, "Geometry"), sm.inputs[0])
    in_sock(sm, "Shade Smooth").default_value = True
    cm = g.n("GeometryNodeSetMaterial")
    g.l(out_sock(sm, "Mesh"), cm.inputs[0])
    in_sock(cm, "Material").default_value = mats["truss"]
    g.l(out_sock(cm, "Geometry"), join.inputs[0])
    for rad, fx in ((RA, 0.06), (RF, 0.94)):
        g.l(_prim(g, "cyl", (g.math("MULTIPLY", rad, 1.04),
                             g.math("MULTIPLY", LEN, 0.10)),
                  (0, math.pi / 2, 0),
                  (g.math("MULTIPLY", LEN, fx), 0, 0),
                  mats["truss"], verts=group_in(g, "Segments")),
            join.inputs[0])
    rmax = g.math("MAXIMUM", RF, RA)
    for ang in (0.785, 2.356, 3.927, 5.498):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", LEN, 0.7), 0.22, 0.14),
                  (ang, 0.0, 0.0),
                  (g.math("MULTIPLY", LEN, 0.5),
                   g.math("MULTIPLY", rmax, -0.98 * math.sin(ang)),
                   g.math("MULTIPLY", rmax, 0.98 * math.cos(ang))),
                  mats["dark"]), join.inputs[0])
    return g.finish(out_sock(join, "Geometry"))


def build_frame_ship(mats, kit):
    """Frame-family SEQUENCER (FRAME_DESIGN.md): a bow, six spine SLOTS each
    holding a section type (0 skip / 1 stack / 2 truss / 3 tank bay / 4 node
    / 5 container rack / 6 reactor), and a gated stern engine section.
    Slot types are seeded (Auto Slots) or hand-picked. Ship-level features:
    ring hab (torus or spoke wheel), wing rows, dishes, nav lights, windows,
    gold wrap, docked craft, cockpit bow for small craft."""
    g = G("FI_FrameShip")
    # ---- frozen v1 socket order ----
    g.sock_in("Seed", "NodeSocketInt", 0)
    g.sock_in("Length", "NodeSocketFloat", 70.0, 8.0, 2000.0)
    g.sock_in("Depth", "NodeSocketFloat", 12.0, 1.0, 200.0)
    g.sock_in("Wing Pairs", "NodeSocketInt", 3, 0, 8)
    g.sock_in("Ring", "NodeSocketBool", False)
    g.sock_in("Engine Count", "NodeSocketInt", 3, 1, 9)
    g.sock_in("Engine Type", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Greebles", "NodeSocketCollection")
    g.sock_in("Greeble Density", "NodeSocketFloat", 0.05, 0.0, 5.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # ---- frame wave (ADDITIVE) ----
    g.sock_in("Auto Slots", "NodeSocketBool", True)
    for i in range(6):
        g.sock_in(f"Slot {i + 1} Type", "NodeSocketInt", 0, 0, 6)
    g.sock_in("Ring Style", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Ring Position", "NodeSocketFloat", 0.45, 0.05, 0.95)
    g.sock_in("Wing Position", "NodeSocketFloat", 0.35, 0.05, 0.95)
    g.sock_in("Engines", "NodeSocketBool", True)
    g.sock_in("Windows", "NodeSocketBool", True)
    g.sock_in("Gold Fraction", "NodeSocketFloat", 0.30, 0.0, 1.0)
    g.sock_in("Docked Craft", "NodeSocketBool", False)
    g.sock_in("Radial Count", "NodeSocketInt", 2, 0, 4)
    g.sock_in("Dish Count", "NodeSocketInt", 1, 0, 3)
    g.sock_in("Bow Style", "NodeSocketInt", 0, 0, 3)
    g.sock_in("Detail", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Width Variation", "NodeSocketFloat", 0.6, 0.0, 1.0)
    g.sock_in("RCS", "NodeSocketBool", True)
    g.sock_in("Wing Fold (deg)", "NodeSocketFloat", 22.0, 0.0, 70.0)

    L, D, seed = (group_in(g, "Length"), group_in(g, "Depth"),
                  group_in(g, "Seed"))
    unit = g.math("DIVIDE", L, 16.0)
    r = g.math("MULTIPLY", D, 0.20)

    def isw(cond, off_sock, on_sock):
        n = g.n("GeometryNodeSwitch", input_type="INT")
        g.l(cond, n.inputs[0])
        g.l(off_sock, in_sock(n, "False", "INT"))
        g.l(on_sock, in_sock(n, "True", "INT"))
        return out_sock(n, "Output", "INT")

    def fsw(cond, off, on):
        n = g.n("GeometryNodeSwitch", input_type="FLOAT")
        g.l(cond, n.inputs[0])
        for nm, v in (("False", off), ("True", on)):
            s = in_sock(n, nm, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, s)
            else:
                s.default_value = v
        return out_sock(n, "Output", "VALUE")

    def gsw(cond, off_geo, on_geo):
        n = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
        g.l(cond, in_sock(n, "Switch"))
        if off_geo is not None:
            g.l(off_geo, in_sock(n, "False", "GEOMETRY"))
        g.l(on_geo, in_sock(n, "True", "GEOMETRY"))
        return out_sock(n, "Output", "GEOMETRY")

    def int_eq(a_sock, b_val):
        n = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
        g.l(a_sock, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b_val
        return out_sock(n, "Result")

    def int_gt(a_sock, b_val):
        n = g.n("FunctionNodeCompare", data_type="INT",
                operation="GREATER_THAN")
        g.l(a_sock, in_sock(n, "A", "INT"))
        in_sock(n, "B", "INT").default_value = b_val
        return out_sock(n, "Result")

    # detail level -> curve segment counts (low poly stays the default)
    det = group_in(g, "Detail")
    d1, d2 = int_gt(det, 0), int_gt(det, 1)
    seg_cyl = fsw(d1, 14.0, fsw(d2, 20.0, 28.0))
    seg_sph = fsw(d1, 10.0, fsw(d2, 14.0, 20.0))
    seg_bell = fsw(d1, 12.0, fsw(d2, 18.0, 24.0))

    # ---- slot types + lengths ----------------------------------------------
    LEN_MULT = {1: 3.0, 2: 3.0, 3: 3.0, 4: 1.4, 5: 3.0, 6: 2.0}
    types, lens = [], []
    for i in range(6):
        auto_t = g.math("ADD", g.math("FLOOR",
                 g.rand_float(0.0, 5.99, None,
                              g.math("ADD", seed, 70.0 + i))), 1.0)
        t_i = isw(group_in(g, "Auto Slots"),
                  group_in(g, f"Slot {i + 1} Type"), auto_t)
        ln = None
        for t, m in LEN_MULT.items():
            src = g.math("MULTIPLY", unit, m)
            ln = fsw(int_eq(t_i, t), ln if ln is not None else 0.0, src)
        types.append(t_i)
        lens.append(ln)

    _bl = g.math("MULTIPLY", r, 2.6)
    _bl = fsw(int_eq(group_in(g, "Bow Style"), 1), _bl,
              g.math("MULTIPLY", r, 2.4))
    _bl = fsw(int_eq(group_in(g, "Bow Style"), 2), _bl,
              g.math("MULTIPLY", r, 2.2))
    bow_len = fsw(int_eq(group_in(g, "Bow Style"), 3), _bl,
                  g.math("MULTIPLY", r, 2.0))
    stern_len = fsw(group_in(g, "Engines"),
                    g.math("MULTIPLY", r, 0.4),
                    g.math("MULTIPLY", unit, 2.0))
    total = bow_len
    for ln in lens:
        total = g.math("ADD", total, ln)
    total = g.math("ADD", total, stern_len)
    half = g.math("DIVIDE", total, 2.0)

    out = g.n("GeometryNodeJoinGeometry")
    white_join = g.n("GeometryNodeJoinGeometry")  # scatter stream

    def place_at(geo, x_sock, extra=None):
        mv = g.n("GeometryNodeTransform")
        g.l(geo, mv.inputs[0])
        tv = g.n("ShaderNodeCombineXYZ")
        g.l(x_sock, tv.inputs[0])
        if extra:
            if extra[1] is not None:
                g.l(extra[1], tv.inputs[1]) if hasattr(extra[1], "is_linked") \
                    else None
            if extra[2] is not None and hasattr(extra[2], "is_linked"):
                g.l(extra[2], tv.inputs[2])
        g.l(tv.outputs[0], in_sock(mv, "Translation"))
        return out_sock(mv, "Geometry")

    # ---- slots ---------------------------------------------------------------
    cum = bow_len
    bxs = [g.math("SUBTRACT", half, bow_len)]   # boundary x's, bow -> stern
    jrs = [g.math("MULTIPLY", r, 0.80)]         # joint radius per boundary side
    for i in range(6):
        cum = g.math("ADD", cum, lens[i])
        origin = g.math("SUBTRACT", half, cum)
        bxs.append(g.math("SUBTRACT", half, cum))
        # per-stack width variation (adapts via couplers)
        rmul_i = g.math("ADD", 1.0, g.math("MULTIPLY",
                 g.math("SUBTRACT",
                        g.rand_float(0.0, 1.0, None,
                                     g.math("ADD", seed, 160.0 + i)), 0.4),
                 g.math("MULTIPLY", 0.35,
                        group_in(g, "Width Variation"))))
        r_i = g.math("MULTIPLY", r, rmul_i)
        slot_seed = g.math("ADD", seed, float(100 + i * 7))
        gold_i = g.math("LESS_THAN",
                        g.rand_float(0.0, 1.0, None,
                                     g.math("ADD", seed, 90.0 + i)),
                        group_in(g, "Gold Fraction"))
        band_i = g.math("FLOOR", g.rand_float(0.0, 2.99, None,
                        g.math("ADD", seed, 11.0 + i)))
        rcs_i = g.math("GREATER_THAN",
                       g.rand_float(0.0, 1.0, None,
                                    g.math("ADD", seed, 130.0 + i)), 0.5)
        # habitat bundle: manned modules get fabric skin AND portholes
        hab_raw = g.math("LESS_THAN",
                         g.rand_float(0.0, 1.0, None,
                                      g.math("ADD", seed, 150.0 + i)), 0.35)
        not_gold = g.n("FunctionNodeBooleanMath", operation="NOT")
        g.l(gold_i, not_gold.inputs[0])
        hab_i = g.n("FunctionNodeBooleanMath", operation="AND")
        g.l(hab_raw, hab_i.inputs[0])
        g.l(not_gold.outputs[0], hab_i.inputs[1])
        win_i = g.n("FunctionNodeBooleanMath", operation="AND")
        g.l(hab_i.outputs[0], win_i.inputs[0])
        g.l(group_in(g, "Windows"), win_i.inputs[1])
        rings_i = g.math("ADD", 1.0, g.math("FLOOR",
                  g.rand_float(0.0, 3.99, None,
                               g.math("ADD", seed, 170.0 + i))))
        cap_i = g.math("FLOOR", g.rand_float(0.0, 2.99, None,
                       g.math("ADD", seed, 180.0 + i)))
        stack = gcall(g, kit["stack"], wires={
            "Radius": r_i, "Length": lens[i], "Band": band_i,
            "Windows": win_i.outputs[0], "Gold": gold_i,
            "Segments": seg_cyl, "Rings": rings_i,
            "Fabric": hab_i.outputs[0], "End Caps": hab_i.outputs[0],
            "Cap Style": cap_i})
        truss = gcall(g, kit["truss"], wires={
            "Bay Length": unit, "Side": g.math("MULTIPLY", r, 2.1)},
            values={"Bays": 3})
        tankb = gcall(g, kit["tankbay"], wires={
            "Unit": unit, "Radius": r, "Seed": slot_seed,
            "Segments": seg_sph})
        nodes = gcall(g, kit["nodesec"], wires={
            "Radius": r, "Seed": slot_seed, "Length": lens[i],
            "Radial Count": group_in(g, "Radial Count")},
            values={"Docked Craft": False, "Cupola": True})
        rack = gcall(g, kit["rack"], wires={
            "Unit": unit, "Radius": r, "Seed": slot_seed})
        reactor = gcall(g, kit["reactor"], wires={
            "Unit": unit, "Radius": r, "Seed": slot_seed,
            "Length": lens[i]})
        geo = None
        for t, section in ((1, stack), (2, truss), (3, tankb),
                           (4, nodes), (5, rack), (6, reactor)):
            geo = gsw(int_eq(types[i], t), geo,
                      out_sock(section, "Geometry"))
        placed = place_at(geo, origin)
        # stacks feed the greeble-scatter stream; others go straight out
        is_stack = int_eq(types[i], 1)
        jrs.append(fsw(is_stack, g.math("MULTIPLY", r, 0.85), r_i))
        g.l(gsw(is_stack, None, placed), white_join.inputs[0])
        inv = g.n("FunctionNodeBooleanMath", operation="NOT")
        g.l(is_stack, inv.inputs[0])
        g.l(gsw(inv.outputs[0], None, placed), out.inputs[0])

    # ---- couplers across every boundary + the stern joint -------------------
    jrs.append(g.math("MULTIPLY", r, 0.70))     # stern side
    clen = g.math("MULTIPLY", unit, 0.35)
    for k, bx in enumerate(bxs):
        cpl = gcall(g, kit["coupler"], wires={
            "R Fore": jrs[k], "R Aft": jrs[k + 1], "Length": clen,
            "Segments": seg_cyl})
        g.l(place_at(out_sock(cpl, "Geometry"),
                     g.math("SUBTRACT", bx,
                            g.math("MULTIPLY", clen, 0.5))), out.inputs[0])

    # ---- central spine: the keel everything meets ---------------------------
    spine_len = g.math("MULTIPLY", total, 0.94)
    spine = _prim(g, "cyl", (g.math("MULTIPLY", r, 0.30), spine_len),
                  (0, math.pi / 2, 0),
                  (g.math("MULTIPLY", total, -0.02), 0, 0),
                  mats["hull"], verts=8)
    g.l(spine, out.inputs[0])
    # running-light strips along the spine (top + bottom), warm emissive
    n_strip = g.math("MAXIMUM", 3.0, g.math("DIVIDE", L, 8.0))
    s_pitch = g.math("DIVIDE", g.math("MULTIPLY", spine_len, 0.9), n_strip)
    for zf in (0.34, -0.34):
        sline = g.n("GeometryNodeMeshLine", mode="OFFSET")
        g.l(n_strip, in_sock(sline, "Count"))
        sv = g.n("ShaderNodeCombineXYZ")
        g.l(s_pitch, sv.inputs[0])
        g.l(sv.outputs[0], in_sock(sline, "Offset"))
        smove = g.n("GeometryNodeTransform")
        g.l(out_sock(sline, "Mesh"), smove.inputs[0])
        stv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("MULTIPLY", spine_len, -0.45), stv.inputs[0])
        g.l(g.math("MULTIPLY", r, zf), stv.inputs[2])
        g.l(stv.outputs[0], in_sock(smove, "Translation"))
        spts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
        g.l(out_sock(smove, "Geometry"), spts.inputs[0])
        strip = _prim(g, "cube", (0.6, 0.12, 0.07), None, None,
                      mats["navstrip"])
        si_ = g.n("GeometryNodeInstanceOnPoints")
        g.l(out_sock(spts, "Points"), si_.inputs[0])
        g.l(strip, in_sock(si_, "Instance"))
        g.l(out_sock(si_, "Instances"), out.inputs[0])
    # anti-collision beacon above the bow — stem ROOTED in the bow body
    # (starts at 0.6r, inside every bow style's geometry)
    bx_b = g.math("SUBTRACT", half, g.math("MULTIPLY", bow_len, 0.5))
    g.l(_prim(g, "cyl", (0.05, g.math("MULTIPLY", r, 1.6)), None,
              (bx_b, 0, g.math("MULTIPLY", r, 1.4)), mats["truss"],
              verts=6), out.inputs[0])
    g.l(_prim(g, "sphere", (0.16,), None,
              (bx_b, 0, g.math("MULTIPLY", r, 2.25)), mats["navred"],
              verts=8), out.inputs[0])
    # registry pennant plates on the fore flanks (seeded fleet colour)
    pen_msw = g.n("GeometryNodeSwitch", input_type="MATERIAL")
    pen_pick = g.math("GREATER_THAN",
                      g.rand_float(0.0, 1.0, None,
                                   g.math("ADD", seed, 200.0)), 0.5)
    g.l(pen_pick, pen_msw.inputs[0])
    in_sock(pen_msw, "False", "MATERIAL").default_value = mats["red"]
    in_sock(pen_msw, "True", "MATERIAL").default_value = mats["blue"]
    # pennants ride the bow COUPLER collar — a surface every ship has
    pen_r = g.math("MAXIMUM", jrs[0], jrs[1])
    for sgn in (1.0, -1.0):
        pen = _prim(g, "cube", (g.math("MULTIPLY", unit, 0.30), 0.06,
                                g.math("MULTIPLY", r, 0.42)), None,
                    (bxs[0],
                     g.math("MULTIPLY", pen_r, 1.02 * sgn), 0.0), None)
        pm_ = g.n("GeometryNodeSetMaterial")
        g.l(pen, pm_.inputs[0])
        g.l(out_sock(pen_msw, "Output", "MATERIAL"),
            in_sock(pm_, "Material"))
        g.l(out_sock(pm_, "Geometry"), out.inputs[0])

    # ---- bow: node+dishes (0) or cockpit capsule (1) ------------------------
    bow0 = g.n("GeometryNodeJoinGeometry")
    nsec = gcall(g, kit["nodesec"], wires={
        "Radius": g.math("MULTIPLY", r, 0.85), "Seed": seed,
        "Length": bow_len,
        "Radial Count": group_in(g, "Radial Count"),
        "Docked Craft": group_in(g, "Docked Craft")},
        values={"Cupola": True})
    g.l(place_at(out_sock(nsec, "Geometry"),
                 g.math("SUBTRACT", half, bow_len)), bow0.inputs[0])
    for di, (ry, rz) in enumerate(((0.0, 0.0), (0.35, 0.5), (-0.3, -0.6))):
        dish = gcall(g, kit["dish"], wires={
            "Dish Radius": g.math("MULTIPLY", r, 0.55),
            "Boom": g.math("MULTIPLY", r, 0.5)})
        dmv = g.n("GeometryNodeTransform")
        g.l(out_sock(dish, "Geometry"), dmv.inputs[0])
        in_sock(dmv, "Rotation").default_value = (0.0, ry, rz)
        dtv = g.n("ShaderNodeCombineXYZ")
        g.l(g.math("SUBTRACT", half, g.math("MULTIPLY", r, 0.4)),
            dtv.inputs[0])
        g.l(g.math("MULTIPLY", r, 0.9 * (di - 1)), dtv.inputs[1])
        g.l(dtv.outputs[0], in_sock(dmv, "Translation"))
        gate = g.n("FunctionNodeCompare", data_type="INT",
                   operation="GREATER_THAN")
        g.l(group_in(g, "Dish Count"), in_sock(gate, "A", "INT"))
        in_sock(gate, "B", "INT").default_value = di
        g.l(gsw(out_sock(gate, "Result"), None,
                out_sock(dmv, "Geometry")), bow0.inputs[0])
    bow1 = g.n("GeometryNodeJoinGeometry")
    cx = g.math("SUBTRACT", half, g.math("MULTIPLY", r, 1.3))
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", r, 0.95),
                         g.math("MULTIPLY", r, 1.9)),
              (0, math.pi / 2, 0), (cx, 0, 0), mats["padded"],
              verts=seg_cyl), bow1.inputs[0])
    g.l(_prim(g, "sphere", (g.math("MULTIPLY", r, 0.90),), None,
              (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 0.35)),
               0, 0), mats["white"], verts=seg_sph), bow1.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", r, 0.97),
                         g.math("MULTIPLY", r, 0.45)),
              (0, math.pi / 2, 0),
              (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 0.75)),
               0, 0), mats["glass"], verts=seg_cyl), bow1.inputs[0])
    # bow 2: armored prow — blunt cone cap + sensor ring + viewport slits
    bow2 = g.n("GeometryNodeJoinGeometry")
    prow = _prim(g, "cone", (g.math("MULTIPLY", r, 0.25),
                             g.math("MULTIPLY", r, 1.15),
                             g.math("MULTIPLY", r, 2.2)),
                 (0, math.pi / 2, 0),
                 (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 2.2)),
                  0, 0), mats["hull"], verts=seg_cyl)
    g.l(prow, bow2.inputs[0])
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", r, 1.18),
                         g.math("MULTIPLY", r, 0.28)),
              (0, math.pi / 2, 0),
              (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 1.9)),
               0, 0), mats["truss"], verts=seg_cyl), bow2.inputs[0])
    for ang in (0.6, 2.54, 3.74, 5.68):
        g.l(_prim(g, "cube", (0.5, 0.28, 0.12), (ang, 0.0, 0.0),
                  (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 1.0)),
                   g.math("MULTIPLY", r, -0.72 * math.sin(ang)),
                   g.math("MULTIPLY", r, 0.72 * math.cos(ang))),
                  mats["window"]), bow2.inputs[0])
    # bow 3: hangar bay — door frame, dark inset mouth, interior glow strip
    bow3 = g.n("GeometryNodeJoinGeometry")
    g.l(_prim(g, "cube", (g.math("MULTIPLY", r, 2.0),
                          g.math("MULTIPLY", r, 2.2),
                          g.math("MULTIPLY", r, 1.8)),
              None, (g.math("SUBTRACT", half, r), 0, 0),
              mats["hull"]), bow3.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", r, 0.4),
                          g.math("MULTIPLY", r, 1.7),
                          g.math("MULTIPLY", r, 1.3)),
              None, (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 0.12)),
                     0, 0), mats["dark"]), bow3.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", r, 0.1),
                          g.math("MULTIPLY", r, 1.5),
                          g.math("MULTIPLY", r, 0.10)),
              None, (g.math("SUBTRACT", half, g.math("MULTIPLY", r, 0.16)),
                     0, g.math("MULTIPLY", r, -0.55)),
              mats["glow"]), bow3.inputs[0])
    for sgn in (1.0, -1.0):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", r, 0.25),
                              g.math("MULTIPLY", r, 0.22),
                              g.math("MULTIPLY", r, 1.9)),
                  None, (g.math("SUBTRACT", half,
                                g.math("MULTIPLY", r, 0.2)),
                         g.math("MULTIPLY", r, 1.0 * sgn), 0),
                  mats["truss"]), bow3.inputs[0])
    sel = gsw(int_eq(group_in(g, "Bow Style"), 1),
              out_sock(bow0, "Geometry"), out_sock(bow1, "Geometry"))
    sel = gsw(int_eq(group_in(g, "Bow Style"), 2), sel,
              out_sock(bow2, "Geometry"))
    sel = gsw(int_eq(group_in(g, "Bow Style"), 3), sel,
              out_sock(bow3, "Geometry"))
    g.l(sel, out.inputs[0])

    # ---- stern ---------------------------------------------------------------
    esec = gcall(g, kit["engsec"], wires={
        "Unit": unit, "Radius": r, "Count": group_in(g, "Engine Count"),
        "Type": group_in(g, "Engine Type"), "Seed": seed,
        "Segments": seg_bell, "Length": stern_len})
    eplaced = place_at(out_sock(esec, "Geometry"),
                       g.math("MULTIPLY", half, -1.0))
    g.l(gsw(group_in(g, "Engines"), None, eplaced), out.inputs[0])

    # ---- ring hab: torus (0) or spoke wheel (1) ------------------------------
    x_ring = g.math("SUBTRACT", half,
                    g.math("MULTIPLY", group_in(g, "Ring Position"), total))
    ringt = gcall(g, kit["ringhab"], wires={
        "Radius": g.math("MULTIPLY", r, 2.8),
        "Tube Radius": g.math("MULTIPLY", r, 0.5),
        "Tube Verts": seg_cyl})
    wheel = gcall(g, kit["wheel"], wires={
        "Radius": g.math("MULTIPLY", r, 3.4),
        "Capsule Radius": g.math("MULTIPLY", r, 1.05),
        "Capsule Verts": seg_cyl}, values={"Arms": 4})
    dbl_ring = g.n("GeometryNodeJoinGeometry")
    for xoff_f in (-0.65, 0.65):
        rt2 = gcall(g, kit["ringhab"], wires={
            "Radius": g.math("MULTIPLY", r, 2.8),
            "Tube Radius": g.math("MULTIPLY", r, 0.45),
            "Tube Verts": seg_cyl})
        g.l(place_at(out_sock(rt2, "Geometry"),
                     g.math("MULTIPLY", unit, xoff_f)), dbl_ring.inputs[0])
    for bang in (0.785, 2.356, 3.927, 5.498):
        g.l(_prim(g, "cube", (g.math("MULTIPLY", unit, 1.5), 0.25, 0.25),
                  (bang, 0.0, 0.0),
                  (0, g.math("MULTIPLY", r, -2.8 * math.sin(bang)),
                   g.math("MULTIPLY", r, 2.8 * math.cos(bang))),
                  mats["truss"]), dbl_ring.inputs[0])
    ring_geo = gsw(int_eq(group_in(g, "Ring Style"), 1),
                   out_sock(ringt, "Geometry"), out_sock(wheel, "Geometry"))
    ring_geo = gsw(int_eq(group_in(g, "Ring Style"), 2), ring_geo,
                   out_sock(dbl_ring, "Geometry"))
    g.l(gsw(group_in(g, "Ring"), None, place_at(ring_geo, x_ring)),
        out.inputs[0])

    # ---- wings + nav lights + radiators --------------------------------------
    amber = g.math("GREATER_THAN",
                   g.rand_float(0.0, 1.0, None,
                                g.math("ADD", seed, 23.0)), 0.5)
    wing = gcall(g, kit["solar"], wires={
        "Panel Length": g.math("MULTIPLY", r, 1.5),
        "Panel Width": g.math("MULTIPLY", r, 1.1),
        "Amber": amber,
        "Fold (deg)": group_in(g, "Wing Fold (deg)")}, values={"Panels": 4})
    wflip = g.n("GeometryNodeTransform")
    g.l(out_sock(wing, "Geometry"), wflip.inputs[0])
    in_sock(wflip, "Rotation").default_value = (math.pi, 0.0, 0.0)
    dbl = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(wing, "Geometry"), dbl.inputs[0])
    g.l(out_sock(wflip, "Geometry"), dbl.inputs[0])
    x_wing = g.math("SUBTRACT", half,
                    g.math("MULTIPLY", group_in(g, "Wing Position"), total))
    wline = g.n("GeometryNodeMeshLine", mode="OFFSET")
    g.l(group_in(g, "Wing Pairs"), in_sock(wline, "Count"))
    wov = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY", unit, -1.8), wov.inputs[0])
    g.l(wov.outputs[0], in_sock(wline, "Offset"))
    woff = g.n("GeometryNodeTransform")
    g.l(out_sock(wline, "Mesh"), woff.inputs[0])
    wotv = g.n("ShaderNodeCombineXYZ")
    g.l(x_wing, wotv.inputs[0])
    g.l(wotv.outputs[0], in_sock(woff, "Translation"))
    wpts = g.n("GeometryNodeMeshToPoints", mode="VERTICES")
    g.l(out_sock(woff, "Geometry"), wpts.inputs[0])
    widx = g.n("GeometryNodeInputIndex")
    wrot = g.n("ShaderNodeCombineXYZ")
    g.l(g.math("MULTIPLY",
               g.math("FLOORED_MODULO", out_sock(widx, "Index"), 2.0),
               math.pi / 2.0), wrot.inputs[0])
    wi = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(wpts, "Points"), wi.inputs[0])
    g.l(out_sock(dbl, "Geometry"), in_sock(wi, "Instance"))
    g.l(wrot.outputs[0], in_sock(wi, "Rotation"))
    g.l(out_sock(wi, "Instances"), out.inputs[0])
    boom = g.math("ADD", g.math("MULTIPLY",
                  g.math("ADD", g.math("MULTIPLY", r, 1.5), 0.3), 4.0), 1.0)
    tip = g.math("ADD", boom, 0.4)
    g.l(_prim(g, "cube", (0.3, 0.3, 0.3), None, (x_wing, tip, 0),
              mats["navred"]), out.inputs[0])
    g.l(_prim(g, "cube", (0.3, 0.3, 0.3), None,
              (x_wing, g.math("MULTIPLY", tip, -1.0), 0),
              mats["navgreen"]), out.inputs[0])
    # wing mount: panels meet structure at the centreline
    g.l(_prim(g, "cyl", (g.math("MULTIPLY", r, 0.36),
                         g.math("MULTIPLY", unit, 0.6)),
              (0, math.pi / 2, 0), (x_wing, 0, 0), mats["truss"],
              verts=10), out.inputs[0])
    g.l(_prim(g, "cube", (g.math("MULTIPLY", r, 0.55),
                          g.math("MULTIPLY", r, 0.55),
                          g.math("MULTIPLY", r, 0.55)),
              None, (x_wing, 0, 0), mats["hull"]), out.inputs[0])

    # realistic RCS: quad pod rings at maximum moment arms (bow + stern).
    # Mount radius = the LOCAL joint radius socket (width variation aware),
    # each pod on an embedded doghouse fairing + scorch ring — no floating.
    rcs_join = g.n("GeometryNodeJoinGeometry")
    pod_sz = g.math("MULTIPLY", r, 0.55)
    for ring_x, jr_local in (
            (g.math("SUBTRACT", bxs[0], g.math("MULTIPLY", unit, 0.5)),
             jrs[1]),
            (g.math("ADD", bxs[6], g.math("MULTIPLY", unit, 0.5)),
             jrs[6])):
        d_fair = g.math("SUBTRACT", jr_local, g.math("MULTIPLY", r, 0.045))
        d_pod = g.math("ADD", jr_local, g.math("MULTIPLY", r, 0.03))
        d_scorch = g.math("ADD", jr_local, g.math("MULTIPLY", r, 0.012))
        for ang_deg in (45.0, 135.0, 225.0, 315.0):
            ang = math.radians(ang_deg)
            rot = (ang - math.pi / 2.0, 0.0, 0.0)

            def radial(dist, x_s=ring_x, a=ang):
                v = g.n("ShaderNodeCombineXYZ")
                g.l(x_s, v.inputs[0])
                g.l(g.math("MULTIPLY", dist, math.cos(a)), v.inputs[1])
                g.l(g.math("MULTIPLY", dist, math.sin(a)), v.inputs[2])
                return v.outputs[0]

            fair = _prim(g, "cube",
                         (g.math("MULTIPLY", pod_sz, 1.15),
                          g.math("MULTIPLY", pod_sz, 1.15),
                          g.math("MULTIPLY", r, 0.15)), rot, None,
                         mats["hull"])
            fmv = g.n("GeometryNodeTransform")
            g.l(fair, fmv.inputs[0])
            g.l(radial(d_fair), in_sock(fmv, "Translation"))
            g.l(out_sock(fmv, "Geometry"), rcs_join.inputs[0])
            scorch = _prim(g, "cyl",
                           (g.math("MULTIPLY", pod_sz, 1.05), 0.04),
                           rot, None, mats["dark"], verts=12)
            smv = g.n("GeometryNodeTransform")
            g.l(scorch, smv.inputs[0])
            g.l(radial(d_scorch), in_sock(smv, "Translation"))
            g.l(out_sock(smv, "Geometry"), rcs_join.inputs[0])
            pod = gcall(g, kit["rcs"], wires={"Size": pod_sz})
            pmv = g.n("GeometryNodeTransform")
            g.l(out_sock(pod, "Geometry"), pmv.inputs[0])
            in_sock(pmv, "Rotation").default_value = rot
            g.l(radial(d_pod), in_sock(pmv, "Translation"))
            g.l(out_sock(pmv, "Geometry"), rcs_join.inputs[0])
    rcs_sw = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(group_in(g, "RCS"), in_sock(rcs_sw, "Switch"))
    g.l(out_sock(rcs_join, "Geometry"), in_sock(rcs_sw, "True", "GEOMETRY"))
    g.l(out_sock(rcs_sw, "Output", "GEOMETRY"), out.inputs[0])

    rad = gcall(g, kit["solar"], wires={
        "Panel Length": g.math("MULTIPLY", r, 0.8),
        "Panel Width": g.math("MULTIPLY", r, 0.6),
        "Fold (deg)": g.math("MULTIPLY", group_in(g, "Wing Fold (deg)"),
                             0.4)},
        values={"Panels": 3, "Radiator": True})
    rflip = g.n("GeometryNodeTransform")
    g.l(out_sock(rad, "Geometry"), rflip.inputs[0])
    in_sock(rflip, "Rotation").default_value = (math.pi, 0.0, 0.0)
    x_rad = g.math("ADD", g.math("MULTIPLY", half, -1.0),
                   g.math("MULTIPLY", unit, 3.6))
    g.l(place_at(out_sock(rad, "Geometry"), x_rad), out.inputs[0])
    g.l(place_at(out_sock(rflip, "Geometry"), x_rad), out.inputs[0])

    # ---- greebles on pressurised skins ---------------------------------------
    white_sel = g.n("GeometryNodeMaterialSelection")
    in_sock(white_sel, "Material").default_value = mats["white"]
    scat = gcall(g, kit["scatter"], wires={
        "Geometry": out_sock(white_join, "Geometry"),
        "Mask": out_sock(white_sel, "Selection"),
        "Greebles": group_in(g, "Greebles"),
        "Density (per m2)": group_in(g, "Greeble Density"),
        "Seed": seed}, values={"Scale Min": 0.5, "Scale Max": 1.0})
    g.l(out_sock(scat, "Geometry"), out.inputs[0])
    # realize at the ship output: applying a GN modifier DISCARDS instances
    # (wings/greebles vanished on apply, 2026-07-10)
    final = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(out, "Geometry"), final.inputs[0])
    return g.finish(out_sock(final, "Geometry"))


# --------------------------------------------------------------- greebles --

def bm_box(bm, sx, sy, sz, at=(0, 0, 0), mat_i=0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    verts = r["verts"]
    bmesh.ops.scale(bm, verts=verts, vec=(sx, sy, sz))
    bmesh.ops.translate(bm, verts=verts, vec=at)
    for f in bm.faces:
        if f.material_index == 0 and all(v in verts for v in f.verts):
            f.material_index = mat_i
    return verts


def bm_cyl(bm, r1, depth, at=(0, 0, 0), segs=8, axis="Z", mat_i=0):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                                radius1=r1, radius2=r1, depth=depth)
    verts = res["verts"]
    if axis == "X":
        bmesh.ops.rotate(bm, verts=verts,
                         matrix=__import__("mathutils").Matrix.Rotation(
                             math.pi / 2, 3, "Y"))
    elif axis == "Y":
        bmesh.ops.rotate(bm, verts=verts,
                         matrix=__import__("mathutils").Matrix.Rotation(
                             math.pi / 2, 3, "X"))
    bmesh.ops.translate(bm, verts=verts, vec=at)
    for f in bm.faces:
        if f.material_index == 0 and all(v in verts for v in f.verts):
            f.material_index = mat_i
    return verts


def greeble_defs():
    """name -> builder(bm). Convention: sits on z=0 plane, +Z out of hull,
    +X fore-aft, footprint ~0.4-1.2 m."""
    d = {}

    def hatch_round(bm):
        bm_cyl(bm, 0.35, 0.08, (0, 0, 0.04), segs=12)
        bm_cyl(bm, 0.10, 0.06, (0.2, 0, 0.10), segs=6, mat_i=1)
    d["hatch_round"] = hatch_round

    def hatch_square(bm):
        bm_box(bm, 0.7, 0.7, 0.08, (0, 0, 0.04))
        bm_box(bm, 0.1, 0.25, 0.05, (0.25, 0, 0.10), mat_i=1)
    d["hatch_square"] = hatch_square

    def hatch_rect(bm):
        bm_box(bm, 1.1, 0.6, 0.07, (0, 0, 0.035))
        bm_box(bm, 0.08, 0.08, 0.06, (0.4, 0.2, 0.10), mat_i=1)
        bm_box(bm, 0.08, 0.08, 0.06, (0.4, -0.2, 0.10), mat_i=1)
    d["hatch_rect"] = hatch_rect

    def vent_louvre_s(bm):
        bm_box(bm, 0.5, 0.35, 0.06, (0, 0, 0.03))
        for i in range(3):
            bm_box(bm, 0.4, 0.06, 0.05, (0, -0.1 + i * 0.1, 0.085), mat_i=1)
    d["vent_louvre_s"] = vent_louvre_s

    def vent_louvre_m(bm):
        bm_box(bm, 0.9, 0.55, 0.07, (0, 0, 0.035))
        for i in range(4):
            bm_box(bm, 0.75, 0.07, 0.05, (0, -0.18 + i * 0.12, 0.10), mat_i=1)
    d["vent_louvre_m"] = vent_louvre_m

    def vent_grill(bm):
        bm_box(bm, 0.6, 0.6, 0.05, (0, 0, 0.025))
        for i in range(4):
            bm_box(bm, 0.06, 0.5, 0.04, (-0.2 + i * 0.13, 0, 0.07), mat_i=1)
    d["vent_grill"] = vent_grill

    def vent_round(bm):
        bm_cyl(bm, 0.28, 0.10, (0, 0, 0.05), segs=10)
        bm_cyl(bm, 0.20, 0.06, (0, 0, 0.12), segs=10, mat_i=1)
    d["vent_round"] = vent_round

    def conduit_straight(bm):
        bm_cyl(bm, 0.07, 1.2, (0, 0, 0.10), segs=6, axis="X")
        bm_box(bm, 0.12, 0.18, 0.10, (-0.45, 0, 0.05), mat_i=1)
        bm_box(bm, 0.12, 0.18, 0.10, (0.45, 0, 0.05), mat_i=1)
    d["conduit_straight"] = conduit_straight

    def conduit_L(bm):
        bm_cyl(bm, 0.07, 0.8, (-0.15, 0, 0.10), segs=6, axis="X")
        bm_cyl(bm, 0.07, 0.55, (0.25, 0.2, 0.10), segs=6, axis="Y")
        bm_box(bm, 0.16, 0.16, 0.14, (0.25, 0, 0.08), mat_i=1)
    d["conduit_L"] = conduit_L

    def conduit_T(bm):
        bm_cyl(bm, 0.07, 1.1, (0, 0, 0.10), segs=6, axis="X")
        bm_cyl(bm, 0.06, 0.5, (0, 0.28, 0.10), segs=6, axis="Y")
        bm_box(bm, 0.16, 0.16, 0.14, (0, 0, 0.08), mat_i=1)
    d["conduit_T"] = conduit_T

    def jbox_s(bm):
        bm_box(bm, 0.3, 0.22, 0.18, (0, 0, 0.09))
    d["jbox_s"] = jbox_s

    def jbox_m(bm):
        bm_box(bm, 0.5, 0.4, 0.28, (0, 0, 0.14))
        bm_box(bm, 0.34, 0.28, 0.05, (0, 0, 0.30), mat_i=1)
    d["jbox_m"] = jbox_m

    def jbox_flat(bm):
        bm_box(bm, 0.8, 0.5, 0.12, (0, 0, 0.06))
        bm_cyl(bm, 0.05, 0.10, (0.3, 0.15, 0.16), segs=6, mat_i=1)
    d["jbox_flat"] = jbox_flat

    def jbox_tall(bm):
        bm_box(bm, 0.35, 0.35, 0.6, (0, 0, 0.30))
        bm_box(bm, 0.4, 0.1, 0.08, (0, 0.18, 0.45), mat_i=1)
    d["jbox_tall"] = jbox_tall

    def sensor_dome_s(bm):
        bm_cyl(bm, 0.22, 0.10, (0, 0, 0.05), segs=10)
        r = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=4,
                                      radius=0.16)
        bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.14))
        for f in bm.faces:
            if all(v in r["verts"] for v in f.verts):
                f.material_index = 1
    d["sensor_dome_s"] = sensor_dome_s

    def sensor_dome_m(bm):
        bm_cyl(bm, 0.35, 0.12, (0, 0, 0.06), segs=12)
        r = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=5,
                                      radius=0.26)
        bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.2))
        for f in bm.faces:
            if all(v in r["verts"] for v in f.verts):
                f.material_index = 1
    d["sensor_dome_m"] = sensor_dome_m

    def rail_short(bm):
        for x in (-0.25, 0.25):
            bm_cyl(bm, 0.03, 0.22, (x, 0, 0.11), segs=6)
        bm_cyl(bm, 0.03, 0.7, (0, 0, 0.22), segs=6, axis="X", mat_i=1)
    d["rail_short"] = rail_short

    def rail_long(bm):
        for x in (-0.55, 0.0, 0.55):
            bm_cyl(bm, 0.03, 0.22, (x, 0, 0.11), segs=6)
        bm_cyl(bm, 0.03, 1.3, (0, 0, 0.22), segs=6, axis="X", mat_i=1)
    d["rail_long"] = rail_long

    def flange_s(bm):
        bm_cyl(bm, 0.20, 0.08, (0, 0, 0.04), segs=8)
        bm_cyl(bm, 0.12, 0.16, (0, 0, 0.12), segs=8, mat_i=1)
    d["flange_s"] = flange_s

    def flange_m(bm):
        bm_cyl(bm, 0.30, 0.10, (0, 0, 0.05), segs=10)
        bm_cyl(bm, 0.18, 0.22, (0, 0, 0.16), segs=10, mat_i=1)
    d["flange_m"] = flange_m

    def panel_recess_s(bm):
        bm_box(bm, 0.55, 0.55, 0.04, (0, 0, 0.02))
        bm_box(bm, 0.4, 0.4, 0.03, (0, 0, 0.045), mat_i=1)
    d["panel_recess_s"] = panel_recess_s

    def panel_recess_m(bm):
        bm_box(bm, 1.0, 0.7, 0.05, (0, 0, 0.025))
        bm_box(bm, 0.8, 0.5, 0.04, (0, 0, 0.055), mat_i=1)
    d["panel_recess_m"] = panel_recess_m

    def panel_raised(bm):
        bm_box(bm, 0.8, 0.8, 0.10, (0, 0, 0.05))
        bm_box(bm, 0.6, 0.15, 0.06, (0, 0.2, 0.13), mat_i=1)
    d["panel_raised"] = panel_raised

    def cable_drum(bm):
        bm_cyl(bm, 0.28, 0.18, (0, 0, 0.14), segs=10, axis="Y")
        bm_box(bm, 0.5, 0.3, 0.06, (0, 0, 0.03), mat_i=1)
    d["cable_drum"] = cable_drum

    def whip_antenna(bm):
        bm_cyl(bm, 0.10, 0.06, (0, 0, 0.03), segs=6)
        bm_cyl(bm, 0.02, 1.05, (0, 0, 0.55), segs=4, mat_i=1)
        r = bmesh.ops.create_uvsphere(bm, u_segments=6, v_segments=3,
                                      radius=0.05)
        bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 1.1))
        for f in bm.faces:
            if all(v in r["verts"] for v in f.verts):
                f.material_index = 1
    d["whip_antenna"] = whip_antenna

    def mini_dish(bm):
        bm_cyl(bm, 0.05, 0.35, (0, 0, 0.17), segs=6)
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=10,
                                    radius1=0.24, radius2=0.02, depth=0.12)
        bmesh.ops.rotate(bm, verts=res["verts"],
                         matrix=__import__("mathutils").Matrix.Rotation(
                             math.pi / 4, 3, "Y"))
        bmesh.ops.translate(bm, verts=res["verts"], vec=(0.08, 0, 0.42))
        for f in bm.faces:
            if all(v in res["verts"] for v in f.verts):
                f.material_index = 1
    d["mini_dish"] = mini_dish

    def ball_turret(bm):
        bm_cyl(bm, 0.30, 0.10, (0, 0, 0.05), segs=10)
        r = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=5,
                                      radius=0.24)
        bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.22))
        for f in bm.faces:
            if all(v in r["verts"] for v in f.verts):
                f.material_index = 1
        bm_cyl(bm, 0.035, 0.55, (0.35, 0.08, 0.28), segs=6, axis="X",
               mat_i=1)
        bm_cyl(bm, 0.035, 0.55, (0.35, -0.08, 0.28), segs=6, axis="X",
               mat_i=1)
    d["ball_turret"] = ball_turret

    return d


def build_greebles(mats):
    coll = bpy.data.collections.new("FI_Greebles")
    bpy.context.scene.collection.children.link(coll)
    defs = greeble_defs()
    for i, (name, fn) in enumerate(sorted(defs.items())):
        bm = bmesh.new()
        fn(bm)
        me = bpy.data.meshes.new(f"FI_{name}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats["metal"])
        me.materials.append(mats["dark"])
        ob = bpy.data.objects.new(f"FI_{name}", me)
        # park them on a grid far from the origin (asset browsing only)
        ob.location = ((i % 6) * 2.0, 100.0 + (i // 6) * 2.0, 0.0)
        coll.objects.link(ob)
    coll.asset_mark()
    return coll


# ------------------------------------------------------------------ main ---

def main():
    out = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = build_materials()
    build_procedural_shaders(mats)
    build_greebles(mats)
    # Frame-only kit (2026-07-10 purge). Panelize/Scatter/RCS/mast/radiator
    # stay: downstream working files link them for hand dress passes.
    kit = {
        "panelize": build_panelize(),
        "scatter": build_greeble_scatter(),
        "engine": build_engine_cluster(mats),
        "rcs": build_rcs_block(mats),
        "mast": build_antenna_mast(mats),
        "radiator": build_radiator_array(mats),
        "truss": build_truss_segment(mats),
        "stack": build_stack_segment(mats),
        "tank": build_tank_cluster(mats),
        "solar": build_solar_array(mats),
        "ringhab": build_ring_hab(mats),
        "docknode": build_docking_node(mats),
        "dish": build_dish_antenna(mats),
    }
    kit["coupler"] = build_coupler(mats, kit)
    kit["tankbay"] = build_tank_bay(mats, kit)
    kit["rack"] = build_container_rack(mats, kit)
    kit["nodesec"] = build_node_section(mats, kit)
    kit["reactor"] = build_reactor_section(mats, kit)
    kit["wheel"] = build_spoke_wheel(mats, kit)
    kit["engsec"] = build_engine_section(mats, kit)
    kit["frame"] = build_frame_ship(mats, kit)
    groups = list(kit.values())

    # dump the frozen socket contract next to the blend
    contract = {}
    for ng in groups:
        contract[ng.name] = [
            {"name": it.name, "in_out": it.in_out,
             "type": getattr(it, "socket_type", "?"),
             "identifier": it.identifier}
            for it in ng.interface.items_tree
        ]
    cpath = os.path.join(os.path.dirname(out), "kit_contract.json")
    with open(cpath, "w") as f:
        json.dump(contract, f, indent=1, sort_keys=True)

    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    tris = sum(len(o.data.polygons) for o in bpy.data.objects
               if o.type == "MESH")
    print(f"build_kit: OK -> {out}")
    print(f"build_kit: {len(groups)} node groups, "
          f"{len(bpy.data.collections['FI_Greebles'].objects)} greebles "
          f"({tris} polys total), contract -> {cpath}")


main()
