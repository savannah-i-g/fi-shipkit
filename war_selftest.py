#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# war_selftest.py -- headless QA for FI_WarKit.blend.
#   blender -b --python war_selftest.py

import bpy
import json
import math
import os
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
WARKIT = os.path.join(HERE, "FI_WarKit.blend")
FRAMEKIT = os.path.join(HERE, "FI_ShipKit.blend")
OUTDIR = os.path.join(HERE, "out", "war_selftest")
FAILS = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def ident(con, group, name):
    for it in con[group]:
        if it["name"] == name and it["in_out"] == "INPUT":
            return it["identifier"]
    raise KeyError(f"{group}:{name}")


def eval_mesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return bpy.data.meshes.new_from_object(
        ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def coord_sum(me):
    # |y*z| cross-term catches shape changes that redistribute symmetric
    # mass (e.g. trapezoid sections) which plain |y| sums cancel out
    return sum(abs(v.co.x) + abs(v.co.y) + abs(v.co.z) +
               abs(v.co.y * v.co.z) for v in me.vertices)


def daylight_gaps(me, tol=0.005, cell=0.5):
    """Open edges with real daylight: farther than tol from EVERY other
    edge at any of 3 samples. Conforming T-junctions (FI face divider) and
    coincident-with-welded borders measure 0 and are fine; anything else
    is a visible hole. Returns the number of daylight edges."""
    from collections import defaultdict
    ec = defaultdict(int)
    vs = [v.co.copy() for v in me.vertices]
    for p in me.polygons:
        pv = list(p.vertices)
        for i in range(len(pv)):
            a, b = pv[i], pv[(i + 1) % len(pv)]
            ec[(min(a, b), max(a, b))] += 1
    all_segs = []
    open_idx = []
    for (a, b), n in ec.items():
        all_segs.append((vs[a], vs[b]))
        if n == 1:
            open_idx.append(len(all_segs) - 1)
    if not open_idx:
        return 0
    grid = defaultdict(list)
    for i, (pa, pb) in enumerate(all_segs):
        lo = (min(pa.x, pb.x), min(pa.y, pb.y), min(pa.z, pb.z))
        hi = (max(pa.x, pb.x), max(pa.y, pb.y), max(pa.z, pb.z))
        for cx in range(int(lo[0] // cell), int(hi[0] // cell) + 1):
            for cy in range(int(lo[1] // cell), int(hi[1] // cell) + 1):
                for cz in range(int(lo[2] // cell), int(hi[2] // cell) + 1):
                    grid[(cx, cy, cz)].append(i)

    def seg_d(p, a, b):
        ab = b - a
        ll = ab.length_squared
        if ll < 1e-18:
            return (p - a).length
        t = max(0.0, min(1.0, (p - a).dot(ab) / ll))
        return (p - a - ab * t).length

    gaps = 0
    for i in open_idx:
        pa, pb = all_segs[i]
        worst = 0.0
        for p in (pa, (pa + pb) * 0.5, pb):
            best = 1e9
            key = (int(p.x // cell), int(p.y // cell), int(p.z // cell))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for j in grid.get((key[0] + dx, key[1] + dy,
                                           key[2] + dz), ()):
                            if j != i:
                                qa, qb = all_segs[j]
                                d = seg_d(p, qa, qb)
                                if d < best:
                                    best = d
            worst = max(worst, best)
        if worst > tol:
            gaps += 1
    return gaps


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(WARKIT, link=True) as (s, d):
        d.node_groups = list(s.node_groups)
    with bpy.data.libraries.load(FRAMEKIT, link=True) as (s, d):
        d.collections = ["FI_Greebles"]
    con = json.load(open(os.path.join(HERE, "war_contract.json")))
    os.makedirs(OUTDIR, exist_ok=True)
    groups = {ng.name: ng for ng in bpy.data.node_groups}
    for want in ("FI_WarShip", "FI_WarHull", "FI_PDCTurret", "FI_VLSPod",
                 "FI_FinMast", "FI_LinearDrive", "FI_WarProfile"):
        check(want in groups, f"warkit provides {want}")

    def gen(name, group, at, params=None):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.scene.collection.objects.link(ob)
        ob.location = at
        m = ob.modifiers.new("m", "NODES")
        m.node_group = groups[group]
        for k, v in (params or {}).items():
            m[ident(con, group, k)] = v
        return ob

    # component budgets
    for gname, lo, hi in (("FI_PDCTurret", 40, 3000),
                          ("FI_VLSPod", 40, 4000),
                          ("FI_FinMast", 10, 500),
                          ("FI_LinearDrive", 40, 4000)):
        ob = gen(f"t_{gname}", gname, (0, -40, 0))
        t = tri_count(eval_mesh(ob))
        check(lo < t < hi, f"{gname} budget {lo}<{t}<{hi}")
    # drive types all differ
    drv = bpy.data.objects["t_FI_LinearDrive"]
    dsums = []
    for ty in (0, 1, 2):
        drv.modifiers[0][ident(con, "FI_LinearDrive", "Type")] = ty
        drv.update_tag()
        dsums.append(round(coord_sum(eval_mesh(drv))))
    check(len(set(dsums)) == 3, f"three distinct drive types ({dsums})")

    # hull massing: symmetric base (Asymmetry 0), guardrails, archetypes
    hull = gen("t_hull", "FI_WarHull", (0, 40, 0),
               {"Seed": 3, "Asymmetry": 0.0})
    hme = eval_mesh(hull)
    t_h = tri_count(hme)
    check(50 < t_h < 20000, f"WarHull massing evaluates (tris={t_h})")
    ysum = sum(v.co.y for v in hme.vertices)
    yext = max(abs(v.co.y) for v in hme.vertices)
    check(abs(ysum) < yext * len(hme.vertices) * 0.02,
          f"WarHull base is Y-symmetric at Asymmetry 0 ({ysum:.2f})")
    ext = [max(v.co[i] for v in hme.vertices) -
           min(v.co[i] for v in hme.vertices) for i in range(3)]
    check(ext[0] < 46.5 and ext[1] < 13.5 and ext[2] < 12.5,
          f"WarHull proportions hold (ext={[f'{e:.1f}' for e in ext]})")
    hm = hull.modifiers[0]
    hm[ident(con, "FI_WarHull", "Asymmetry")] = 1.0
    hull.update_tag()
    me_asym = eval_mesh(hull)
    ysum2 = sum(v.co.y for v in me_asym.vertices)
    check(abs(ysum2) > abs(ysum) + 0.5,
          f"Asymmetry breaks the mirror ({ysum:.1f} -> {ysum2:.1f})")
    hm[ident(con, "FI_WarHull", "Asymmetry")] = 0.5
    s_a = coord_sum(eval_mesh(hull))
    hm[ident(con, "FI_WarHull", "Seed")] = 9
    hull.update_tag()
    check(abs(coord_sum(eval_mesh(hull)) - s_a) > 1.0,
          "Seed reshapes the hull massing")
    sils = []
    for s in (0, 1, 2):
        hm[ident(con, "FI_WarHull", "Silhouette")] = s
        hull.update_tag()
        sils.append(round(coord_sum(eval_mesh(hull))))
    check(len(set(sils)) == 3,
          f"wedge/dagger/hammer archetypes all differ ({sils})")
    hm[ident(con, "FI_WarHull", "Silhouette")] = 0

    # full warship: corvette vs destroyer vs factions
    ship = gen("t_ship", "FI_WarShip", (0, 120, 0), {"Seed": 1})
    ship.modifiers[0][ident(con, "FI_WarShip", "Greebles")] = \
        bpy.data.collections["FI_Greebles"]
    sme = eval_mesh(ship)
    t_cv = tri_count(sme)
    check(2000 < t_cv < 60000, f"corvette evaluates (tris={t_cv})")
    mset = {m.name.split(".")[0] for m in sme.materials if m}
    check("FI_War_MCR_Hull" in mset,
          f"MCR hull material (mats={sorted(mset)[:6]})")
    check("FI_War_MCR_Line" in mset, "chine light-lines present (signature)")
    check("FI_War_MCR_Drive" in mset, "faction drive glow present")
    sm = ship.modifiers[0]
    sm[ident(con, "FI_WarShip", "Faction")] = 1
    ship.update_tag()
    mset1 = {m.name.split(".")[0] for m in eval_mesh(ship).materials if m}
    check("FI_War_UNN_Hull" in mset1, "UNN faction switches hull set")
    sm[ident(con, "FI_WarShip", "Faction")] = 2
    ship.update_tag()
    mset2 = {m.name.split(".")[0] for m in eval_mesh(ship).materials if m}
    check("FI_War_BEL_Hull" in mset2, "BEL faction switches hull set")
    sm[ident(con, "FI_WarShip", "Faction")] = 0
    sm[ident(con, "FI_WarShip", "Class")] = 1
    ship.update_tag()
    me_dd = eval_mesh(ship)
    t_dd = tri_count(me_dd)
    ext_dd = max(v.co.x for v in me_dd.vertices) - \
        min(v.co.x for v in me_dd.vertices)
    check(t_dd < 120000, f"destroyer within budget (tris={t_dd})")
    check(ext_dd > 90, f"destroyer is destroyer-sized (L={ext_dd:.0f} m)")
    sm[ident(con, "FI_WarShip", "Class")] = 0
    # turret count drives geometry
    sm[ident(con, "FI_WarShip", "Turrets")] = 0
    sm[ident(con, "FI_WarShip", "VLS Pods")] = 0
    ship.update_tag()
    t_bare = tri_count(eval_mesh(ship))
    check(t_bare < t_cv, f"hardpoints gate off ({t_cv} -> {t_bare})")
    sm[ident(con, "FI_WarShip", "Turrets")] = 4
    sm[ident(con, "FI_WarShip", "VLS Pods")] = 2
    ship.update_tag()

    # ---- deep-customization sweep: every knob must reshape the ship -------
    sm[ident(con, "FI_WarShip", "Class")] = 0
    ship.update_tag()
    base_sum = coord_sum(eval_mesh(ship))
    knobs = (
        ("Section=3", (("Section", 3),)),
        ("Section=1+Exponent", (("Section", 1), ("Section Exponent", 1.8))),
        ("Side Profile", (("Side Profile", 1),)),
        ("Step Strength", (("Step Strength", 1.8),)),
        ("Step Count", (("Step Count", 4),)),
        ("Nose Frac", (("Nose Frac", 0.7),)),
        ("Sub Panels", (("Sub Panels", 0.4),)),
        ("Bend", (("Bend", 0.6),)),
        ("Blend", (("Blend", 0.5),)),
        ("Dorsal Taper", (("Dorsal Taper", 0.6),)),
        ("Hump Height", (("Hump Height", 0.5),)),
        ("Detail Extrusions", (("Detail Extrusions", 5),)),
        ("Visor off", (("Visor", False),)),
        ("Trench", (("Trench", 0.8),)),
        ("Armor Plates", (("Armor Plates", 1.0),)),
        ("Panel Density", (("Panel Density", 4),)),
        ("Light Lines", (("Light Lines", 0),)),
        ("Length Mult", (("Length Mult", 1.4),)),
    )
    moved = 0
    for label, pairs in knobs:
        saved = []
        for name, val in pairs:
            keyid = ident(con, "FI_WarShip", name)
            saved.append((keyid, sm.get(keyid, None)))
            sm[keyid] = val
        ship.update_tag()
        s = coord_sum(eval_mesh(ship))
        if abs(s - base_sum) > 0.5:
            moved += 1
        else:
            print("  KNOB-DEAD:", label)
        for keyid, old_v in saved:
            if old_v is None:
                del sm[keyid]
            else:
                sm[keyid] = old_v
        ship.update_tag()
    check(moved == len(knobs),
          f"deep-customization: {moved}/{len(knobs)} knobs reshape the ship")
    mset_v = {m.name.split(".")[0] for m in eval_mesh(ship).materials if m}
    check("FI_War_Glass" in mset_v, "canopy visor glass present by default")
    gl_used = any(me2.materials[p.material_index] and
                  me2.materials[p.material_index].name.split(".")[0]
                  == "FI_War_Glass"
                  for me2 in (eval_mesh(ship),) for p in me2.polygons)
    check(gl_used, "visor glass is on actual faces (not just a slot)")

    # ---- WATERTIGHT: no open edge with daylight behind it -----------------
    # (her 2026-07-10 screenshots: torn drive apertures + panel slits)
    wt_configs = (
        ("her-settings", {"Seed": 1, "Class": 0, "Section": 2,
                          "Step Count": 4, "Nose Frac": 0.05, "Bend": 0.42,
                          "Hump Position": 0.23, "Hump Length": 0.11,
                          "Hump Height": 0.07, "Detail Extrusions": 8,
                          "Visor": True, "Trench": 1.0,
                          "Armor Plates": 1.0, "Panel Density": 1,
                          "Retro Thrusters": True,
                          "Manoeuvring Ports": True}),
        ("stress corvette", {"Seed": 7, "Class": 0, "Panel Density": 2,
                             "Sub Panels": 0.5, "Detail Extrusions": 8,
                             "Trench": 1.0, "Armor Plates": 1.0,
                             "Bend": 0.42, "Retro Thrusters": True,
                             "Manoeuvring Ports": True}),
        ("stress destroyer", {"Seed": 4, "Class": 1, "Panel Density": 2,
                              "Sub Panels": 0.4, "Drive Type": 2,
                              "Trench": 0.5, "Armor Plates": 0.5}),
    )
    for wname, wp in wt_configs:
        saved = []
        for k, v in wp.items():
            kid = ident(con, "FI_WarShip", k)
            saved.append((kid, sm.get(kid, None)))
            sm[kid] = v
        ship.update_tag()
        ng = daylight_gaps(eval_mesh(ship))
        check(ng == 0, f"watertight at {wname} (daylight edges={ng})")
        for kid, old_v in saved:
            if old_v is None:
                del sm[kid]
            else:
                sm[kid] = old_v
        ship.update_tag()

    # renders
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 700
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("s", "SUN"))
    sun.rotation_euler = (math.radians(55), 0, math.radians(30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("c"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    for name, ctr, dist in (("war_hull", Vector((0, 40, 0)), 65.0),
                            ("war_corvette", Vector((0, 120, 0)), 70.0)):
        d = Vector((-0.8, -1.0, 0.45)).normalized()
        cam.location = ctr + d * dist
        cam.rotation_euler = (ctr - cam.location).to_track_quat(
            "-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(OUTDIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)
        check(os.path.exists(scene.render.filepath), f"render {name}")

    print(f"\nwar_selftest: {'ALL PASS' if not FAILS else 'FAILURES:'}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1 if FAILS else 0)


main()
