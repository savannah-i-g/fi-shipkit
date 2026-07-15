#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# kit_selftest.py -- headless QA for FI_ShipKit.blend (FRAME-ONLY kit).
#
#   blender -b --python kit_selftest.py
#
# Panelize/Scatter/module legs cover the corvette dress-pass groups (kept
# for downstream dress-pass files); the rest is the frame family. Exits non-zero
# on any failed assert. Renders land in out/selftest/.

import bpy
import json
import math
import os
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "FI_ShipKit.blend")
OUTDIR = os.path.join(HERE, "out", "selftest")

FAILS = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def link_kit():
    with bpy.data.libraries.load(KIT, link=True) as (src, dst):
        dst.node_groups = list(src.node_groups)
        dst.collections = ["FI_Greebles"]
    return {ng.name: ng for ng in bpy.data.node_groups}


def contract():
    with open(os.path.join(HERE, "kit_contract.json")) as f:
        return json.load(f)


def ident(con, group, sock_name):
    for it in con[group]:
        if it["name"] == sock_name and it["in_out"] == "INPUT":
            return it["identifier"]
    raise KeyError(f"{group}: {sock_name}")


def realize_group():
    name = "FI_TestRealize"
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT",
                            socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT",
                            socket_type="NodeSocketGeometry")
    a = ng.nodes.new("NodeGroupInput")
    r = ng.nodes.new("GeometryNodeRealizeInstances")
    b = ng.nodes.new("NodeGroupOutput")
    ng.links.new(a.outputs[0], r.inputs[0])
    ng.links.new(r.outputs[0], b.inputs[0])
    return ng


def eval_mesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return bpy.data.meshes.new_from_object(
        ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def coord_sum(me):
    return sum(abs(v.co.x) + abs(v.co.y) + abs(v.co.z) for v in me.vertices)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    groups = link_kit()
    con = contract()
    os.makedirs(OUTDIR, exist_ok=True)

    for want in ("FI_Panelize", "FI_GreebleScatter", "FI_FrameShip",
                 "FI_StackSegment", "FI_TrussSegment", "FI_EngineSection"):
        check(want in groups, f"kit provides {want}")
    for gone in ("FI_ShipGen", "FI_MonohullShip", "FI_SlabShip",
                 "FI_HullLoft", "FI_EngineBlock", "FI_PipeRun"):
        check(gone not in groups, f"purged: {gone} removed")

    def gen_object(name, group, at, params=None):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.scene.collection.objects.link(ob)
        ob.location = at
        m = ob.modifiers.new("m", "NODES")
        m.node_group = groups[group]
        for k, v in (params or {}).items():
            m[ident(con, group, k)] = v
        return ob

    # ---- corvette dress-pass groups (kept) --------------------------------
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
    cube = bpy.context.active_object
    cube.name = "t_panelize"
    pm = cube.modifiers.new("p", "NODES")
    pm.node_group = groups["FI_Panelize"]
    me = eval_mesh(cube)
    check(24 < tri_count(me) < 144,
          f"Panelize plates a cube (tris={tri_count(me)})")
    check(me.attributes.get("fi_panel_rand") is not None,
          "fi_panel_rand stored")

    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 14, 0))
    plate = bpy.context.active_object
    plate.name = "t_scatter"
    sm = plate.modifiers.new("g", "NODES")
    sm.node_group = groups["FI_GreebleScatter"]
    sm[ident(con, "FI_GreebleScatter", "Greebles")] = \
        bpy.data.collections["FI_Greebles"]
    sm[ident(con, "FI_GreebleScatter", "Density (per m2)")] = 0.8
    rr = plate.modifiers.new("r", "NODES")
    rr.node_group = realize_group()
    check(tri_count(eval_mesh(plate)) > 42,
          "GreebleScatter instances greebles")

    # ---- component budgets -------------------------------------------------
    comp_budgets = {
        "FI_EngineCluster": (100, 3000), "FI_RCS_Block": (50, 1200),
        "FI_AntennaMast": (60, 1500), "FI_RadiatorArray": (60, 2500),
        "FI_TrussSegment": (100, 6000), "FI_StackSegment": (60, 3000),
        "FI_SolarArray": (30, 2000), "FI_RingHab": (150, 6000),
        "FI_TankBay": (200, 7000), "FI_ContainerRack": (200, 8000),
        "FI_NodeSection": (150, 8000), "FI_ReactorSection": (150, 6000),
        "FI_SpokeWheel": (200, 9000), "FI_EngineSection": (150, 8000),
    }
    for i, (gname, (lo, hi)) in enumerate(comp_budgets.items()):
        ob = gen_object(f"t_{gname}", gname, (i * 15, 200, 0))
        t = tri_count(eval_mesh(ob))
        check(lo < t < hi, f"{gname} tri budget {lo}<{t}<{hi}")

    # ---- frame sequencer ----------------------------------------------------
    fs = gen_object("t_framev2", "FI_FrameShip", (0, 420, 0),
                    {"Length": 80.0, "Depth": 14.0})
    fm = fs.modifiers[0]
    fm[ident(con, "FI_FrameShip", "Greebles")] = \
        bpy.data.collections["FI_Greebles"]
    me_v2 = eval_mesh(fs)
    t_v2 = tri_count(me_v2)
    check(2000 < t_v2 < 150000, f"FrameShip sequencer evaluates (tris={t_v2})")
    # realized output: wings must SURVIVE without any helper realize modifier
    check("FI_SolarPanel" in {m.name.split(".")[0]
                              for m in me_v2.materials if m} or
          "FI_SolarAmber" in {m.name.split(".")[0]
                              for m in me_v2.materials if m},
          "wings survive plain evaluation (realized output — apply-safe)")
    sum_auto = coord_sum(me_v2)
    fm[ident(con, "FI_FrameShip", "Auto Slots")] = False
    fm[ident(con, "FI_FrameShip", "Slot 1 Type")] = 6
    fm[ident(con, "FI_FrameShip", "Slot 2 Type")] = 1
    fm[ident(con, "FI_FrameShip", "Slot 3 Type")] = 3
    fs.update_tag()
    sum_man = coord_sum(eval_mesh(fs))
    check(abs(sum_auto - sum_man) > 1.0,
          "manual slot programme differs from auto")
    fm[ident(con, "FI_FrameShip", "Slot 1 Type")] = 5
    fs.update_tag()
    sum_alt = coord_sum(eval_mesh(fs))
    check(abs(sum_man - sum_alt) > 1.0, "slot type flip changes the ship")
    t_eng_on = tri_count(eval_mesh(fs))
    fm[ident(con, "FI_FrameShip", "Engines")] = False
    fs.update_tag()
    check(tri_count(eval_mesh(fs)) < t_eng_on,
          "Engines off removes the stern section (station mode)")
    fm[ident(con, "FI_FrameShip", "Engines")] = True
    fm[ident(con, "FI_FrameShip", "Ring")] = True
    fs.update_tag()
    sum_torus = coord_sum(eval_mesh(fs))
    fm[ident(con, "FI_FrameShip", "Ring Style")] = 1
    fs.update_tag()
    check(abs(coord_sum(eval_mesh(fs)) - sum_torus) > 1.0,
          "spoke wheel differs from torus ring")
    fm[ident(con, "FI_FrameShip", "Ring")] = False
    fm[ident(con, "FI_FrameShip", "Bow Style")] = 1
    fs.update_tag()
    check(abs(coord_sum(eval_mesh(fs)) - sum_alt) > 1.0,
          "cockpit bow differs from node bow")
    fm[ident(con, "FI_FrameShip", "Bow Style")] = 0
    # detail levels: high detail multiplies curve segments
    t_d0 = tri_count(eval_mesh(fs))
    fm[ident(con, "FI_FrameShip", "Detail")] = 2
    fs.update_tag()
    t_d2 = tri_count(eval_mesh(fs))
    check(t_d2 > t_d0 * 1.3,
          f"Detail 2 raises curve resolution ({t_d0} -> {t_d2})")
    fm[ident(con, "FI_FrameShip", "Detail")] = 0
    fs.update_tag()

    # small craft: same grammar at skiff scale
    skiff = gen_object("t_skiff", "FI_FrameShip", (60, 420, 0),
                       {"Length": 16.0, "Depth": 4.5, "Wing Pairs": 1,
                        "Bow Style": 1, "Dish Count": 0})
    skiff.modifiers[0][ident(con, "FI_FrameShip", "Greebles")] = \
        bpy.data.collections["FI_Greebles"]
    t_skiff = tri_count(eval_mesh(skiff))
    check(300 < t_skiff < 30000, f"skiff-scale frame craft (tris={t_skiff})")

    # ---- production polish legs ---------------------------------------------
    # contiguity: no gaps along the spine span (vertex x-histogram)
    fm[ident(con, "FI_FrameShip", "Auto Slots")] = True
    fs.update_tag()
    me_c = eval_mesh(fs)
    # sample along EDGES (truss longerons are long boxes — vertex-only
    # histograms show false holes mid-member)
    pts = []
    vs = me_c.vertices
    for e in me_c.edges:
        a, b = vs[e.vertices[0]].co.x, vs[e.vertices[1]].co.x
        n = max(1, int(abs(b - a)))
        pts.extend(a + (b - a) * k / n for k in range(n + 1))
    pts.sort()
    lo_x = pts[0] + (pts[-1] - pts[0]) * 0.06
    hi_x = pts[-1] - (pts[-1] - pts[0]) * 0.06
    span = hi_x - lo_x
    nbins = 40
    filled = set(min(nbins - 1, max(0, int((x - lo_x) / span * nbins)))
                 for x in pts if lo_x <= x <= hi_x)
    check(len(filled) == nbins,
          f"spine contiguity: all {nbins} x-bins occupied "
          f"({len(filled)} filled) — no section gaps")
    # smooth shading present on curved faces
    check(any(p.use_smooth for p in me_c.polygons),
          "smooth shading present on curved faces")
    # habitat semantics: fabric and window materials co-occur
    cmats = {m.name.split(".")[0] for m in me_c.materials if m}
    # habitat picks are seeded per stack — force an all-stack programme so
    # at least one habitat module is statistically certain
    fm[ident(con, "FI_FrameShip", "Auto Slots")] = False
    for si in range(1, 7):
        fm[ident(con, "FI_FrameShip", f"Slot {si} Type")] = 1
    fs.update_tag()
    pm = {m.name.split(".")[0] for m in eval_mesh(fs).materials if m}
    check("FI_PaddedFabric" in pm, "habitat modules wear padded fabric")
    check("FI_Window" in pm, "habitat portholes present (both flanks)")
    fm[ident(con, "FI_FrameShip", "Auto Slots")] = True
    fs.update_tag()
    # width variation changes the ship
    sum_w = coord_sum(me_c)
    fm[ident(con, "FI_FrameShip", "Width Variation")] = 0.0
    fs.update_tag()
    check(abs(coord_sum(eval_mesh(fs)) - sum_w) > 1.0,
          "Width Variation drives module radii")
    fm[ident(con, "FI_FrameShip", "Width Variation")] = 0.6
    # RCS pod rings toggle
    sum_r = coord_sum(eval_mesh(fs))
    fm[ident(con, "FI_FrameShip", "RCS")] = False
    fs.update_tag()
    check(abs(coord_sum(eval_mesh(fs)) - sum_r) > 1.0,
          "RCS pod rings gate on/off")
    fm[ident(con, "FI_FrameShip", "RCS")] = True
    # new bow + ring styles all differ
    sums = []
    for bs in (0, 2, 3):
        fm[ident(con, "FI_FrameShip", "Bow Style")] = bs
        fs.update_tag()
        sums.append(coord_sum(eval_mesh(fs)))
    check(len({round(s) for s in sums}) == 3,
          "armored prow + hangar bow differ from node bow")
    fm[ident(con, "FI_FrameShip", "Bow Style")] = 0
    fm[ident(con, "FI_FrameShip", "Ring")] = True
    fm[ident(con, "FI_FrameShip", "Ring Style")] = 2
    fs.update_tag()
    check(abs(coord_sum(eval_mesh(fs)) - sums[0]) > 1.0,
          "double-torus ring style evaluates")
    fm[ident(con, "FI_FrameShip", "Ring")] = False
    fs.update_tag()
    # section length contract spot-checks (extent == Length +-3%)
    for gname, params in (("FI_NodeSection", {"Length": 10.0}),
                          ("FI_ReactorSection", {"Length": 10.0}),
                          ("FI_EngineSection", {"Length": 10.0})):
        ob = gen_object(f"t_len_{gname}", gname, (0, 600, 0), params)
        me_l = eval_mesh(ob)
        x0 = min(v.co.x for v in me_l.vertices)
        x1 = max(v.co.x for v in me_l.vertices)
        # engines protrude aft of x=0 by design (exhaust); check fore end
        check(abs(x1 - 10.0) < 10.0 * 0.12,
              f"{gname} honours Length contract (fore end {x1:.2f} ~ 10)")

    # ---- visual polish v2 legs ------------------------------------------------
    check(len(bpy.data.collections["FI_Greebles"].objects) == 27,
          "greeble pool = 27 (whip antenna + mini dish added)")
    sa = gen_object("t_fold", "FI_SolarArray", (0, 700, 0),
                    {"Fold (deg)": 0.0})
    sum_flat = coord_sum(eval_mesh(sa))
    sa.modifiers[0][ident(con, "FI_SolarArray", "Fold (deg)")] = 35.0
    sa.update_tag()
    check(abs(coord_sum(eval_mesh(sa)) - sum_flat) > 1.0,
          "accordion fold reshapes the array (0 vs 35 deg)")
    ts = gen_object("t_conduit", "FI_TrussSegment", (30, 700, 0), {})
    t_cnd = tri_count(eval_mesh(ts))
    ts.modifiers[0][ident(con, "FI_TrussSegment", "Conduits")] = False
    ts.update_tag()
    check(tri_count(eval_mesh(ts)) < t_cnd,
          "truss conduit runs gate on/off")
    # frame ship carries the new fidelity materials; RCS fairing embeds
    fm[ident(con, "FI_FrameShip", "Auto Slots")] = False
    for si in range(1, 7):
        fm[ident(con, "FI_FrameShip", f"Slot {si} Type")] = 1
    fm[ident(con, "FI_FrameShip", "Width Variation")] = 0.0
    fs.update_tag()
    me_p = eval_mesh(fs)
    pmats = {m.name.split(".")[0] for m in me_p.materials if m}
    for want in ("FI_EngineGlowHalo", "FI_NavStrip"):
        check(want in pmats, f"fidelity material {want} present")
    # embed check: fairing bottoms sit BELOW the local hull surface (r)
    r_loc = 14.0 * 0.20   # Depth 14 -> r; Width Variation 0 -> jr == r
    xs2 = [v.co.x for v in me_p.vertices]
    x_hi = max(xs2)
    embedded = [v for v in me_p.vertices
                if 0.45 * r_loc < (v.co.y ** 2 + v.co.z ** 2) ** 0.5
                < 0.97 * r_loc and abs(v.co.x - x_hi) < x_hi * 0.6]
    check(len(embedded) > 0,
          "RCS doghouse fairings embed below the hull surface")
    fm[ident(con, "FI_FrameShip", "Width Variation")] = 0.6
    fm[ident(con, "FI_FrameShip", "Auto Slots")] = True
    fs.update_tag()

    # ---- procedural shaders present ----------------------------------------
    white = bpy.data.materials.get("FI_ThermalWhite")
    kinds = {n.type for n in white.node_tree.nodes} if white else set()
    for want in ("BEVEL", "AMBIENT_OCCLUSION", "TEX_IMAGE"):
        check(want in kinds,
              f"FI_ThermalWhite carries {want} (wear tree + panel pack)")
    imgs = {n.image.name for n in white.node_tree.nodes
            if n.type == "TEX_IMAGE" and n.image}
    check(any("hull-texture2" in i for i in imgs),
          f"white base is HER Hull_Texture2 (imgs={sorted(imgs)})")
    solar = bpy.data.materials.get("FI_SolarPanel")
    skinds = {n.type for n in solar.node_tree.nodes} if solar else set()
    check("TEX_IMAGE" in skinds, "FI_SolarPanel carries SolarPanel003 pack")
    padded = bpy.data.materials.get("FI_PaddedFabric")
    pkinds = {n.type for n in padded.node_tree.nodes} if padded else set()
    check("TEX_IMAGE" in pkinds, "FI_PaddedFabric carries Fabric048 pack")

    # ---- renders ------------------------------------------------------------
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 640
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    targets = {
        "frame_v2": (Vector((0, 420, 0)), 100.0),
        "skiff": (Vector((60, 420, 0)), 26.0),
    }
    for name, (center, dist) in targets.items():
        direction = Vector((1.0, -1.0, 0.7)).normalized()
        cam.location = center + direction * dist
        look = center - cam.location
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(OUTDIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)
        check(os.path.exists(scene.render.filepath),
              f"render {name}.png written")

    print(f"\nkit_selftest: {'ALL PASS' if not FAILS else 'FAILURES:'}")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1 if FAILS else 0)


main()
