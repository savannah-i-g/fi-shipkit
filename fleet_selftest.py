#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# fleet_selftest.py -- headless QA for FI_FleetKit.blend.
#   blender -b --python fleet_selftest.py

import bpy
import json
import math
import os
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
FLEETKIT = os.path.join(HERE, "FI_FleetKit.blend")
OUTDIR = os.path.join(HERE, "out", "fleet_selftest")
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
    # mass, which plain |y| sums cancel out
    return sum(abs(v.co.x) + abs(v.co.y) + abs(v.co.z) +
               abs(v.co.y * v.co.z) for v in me.vertices)


def daylight_gaps(me, tol=0.005, cell=0.5):
    """Open edges with real daylight (> tol from EVERY other edge at 3
    samples). Conforming T-junctions and coincident islands measure 0."""
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
    with bpy.data.libraries.load(FLEETKIT, link=True) as (s, d):
        d.node_groups = list(s.node_groups)
    con = json.load(open(os.path.join(HERE, "fleet_contract.json")))
    os.makedirs(OUTDIR, exist_ok=True)
    groups = {ng.name: ng for ng in bpy.data.node_groups}
    for want in ("FI_FleetShip", "FI_FleetHull", "FI_FleetProfile",
                 "FI_VentGrate", "FI_Radome", "FI_AntennaMast",
                 "FI_Sponson", "FI_SensorBoom", "FI_Chevron",
                 "FI_HullNumber"):
        check(want in groups, f"fleetkit provides {want}")

    def gen(name, group, at, params=None):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.scene.collection.objects.link(ob)
        ob.location = at
        m = ob.modifiers.new("m", "NODES")
        m.node_group = groups[group]
        for k, v in (params or {}).items():
            m[ident(con, group, k)] = v
        return ob

    # ---- component budgets -------------------------------------------------
    for gname, lo, hi in (("FI_FleetFin", 20, 600),
                          ("FI_FleetProng", 20, 700),
                          ("FI_FleetNacelle", 40, 1500),
                          ("FI_VentGrate", 40, 2500),
                          ("FI_Radome", 40, 3000),
                          ("FI_AntennaMast", 30, 1200),
                          ("FI_Sponson", 30, 1500),
                          ("FI_SensorBoom", 20, 600),
                          ("FI_Chevron", 20, 300),
                          ("FI_HullNumber", 20, 800)):
        ob = gen(f"t_{gname}", gname, (0, -60, 0))
        t = tri_count(eval_mesh(ob))
        check(lo < t < hi, f"{gname} budget {lo}<{t}<{hi}")
    rad = bpy.data.objects["t_FI_Radome"]
    rsums = []
    for var in (0, 1):
        rad.modifiers[0][ident(con, "FI_Radome", "Variant")] = var
        rad.update_tag()
        rsums.append(round(coord_sum(eval_mesh(rad))))
    check(len(set(rsums)) == 2, f"radome dome/dish variants differ ({rsums})")
    num = bpy.data.objects["t_FI_HullNumber"]
    nsums2 = set()
    for v in (8, 13, 47):
        num.modifiers[0][ident(con, "FI_HullNumber", "Value")] = v
        num.update_tag()
        nsums2.add(round(coord_sum(eval_mesh(num))))
    check(len(nsums2) == 3, f"hull-number digits respond to Value ({nsums2})")

    # ---- hull: slab proportions, symmetry, plateau monotonicity ----------
    hull = gen("t_hull", "FI_FleetHull", (0, 200, 0),
               {"Seed": 3, "Towers": 0})
    hme = eval_mesh(hull)
    t_h = tri_count(hme)
    check(100 < t_h < 20000, f"FleetHull evaluates (tris={t_h})")
    ext = [max(v.co[i] for v in hme.vertices) -
           min(v.co[i] for v in hme.vertices) for i in range(3)]
    check(ext[1] > 1.8 * ext[2],
          f"slab proportions: beam >> depth "
          f"(ext={[f'{e:.1f}' for e in ext]})")
    ysum = sum(v.co.y for v in hme.vertices)
    yext = max(abs(v.co.y) for v in hme.vertices)
    check(abs(ysum) < yext * len(hme.vertices) * 0.02,
          f"hull is Y-symmetric by construction ({ysum:.2f})")
    hm = hull.modifiers[0]
    zmaxes = []
    for np_ in (0, 1, 2):
        hm[ident(con, "FI_FleetHull", "Plateaus")] = np_
        hull.update_tag()
        zmaxes.append(max(v.co.z for v in eval_mesh(hull).vertices))
    check(zmaxes[0] < zmaxes[1] < zmaxes[2],
          f"plateau levels stack monotonically ({[f'{z:.2f}' for z in zmaxes]})")
    hm[ident(con, "FI_FleetHull", "Plateaus")] = 2
    s_a = coord_sum(eval_mesh(hull))
    hm[ident(con, "FI_FleetHull", "Seed")] = 9
    hull.update_tag()
    check(abs(coord_sum(eval_mesh(hull)) - s_a) > 1.0,
          "Seed reshapes the hull")

    # ---- ship: evaluates, budgets, factions, watertight -------------------
    ship = gen("t_ship", "FI_FleetShip", (0, 0, 0), {"Seed": 1})
    sme = eval_mesh(ship)
    t_fr = tri_count(sme)
    check(500 < t_fr < 60000, f"frigate evaluates (tris={t_fr})")
    mset = {m.name.split(".")[0] for m in sme.materials if m}
    check("FI_Fleet_NAV_Hull" in mset,
          f"NAV hull material (mats={sorted(mset)[:6]})")
    dw_used = any(sme.materials[p.material_index] and
                  sme.materials[p.material_index].name.split(".")[0]
                  == "FI_Fleet_NAV_Deck" for p in sme.polygons)
    check(dw_used, "charcoal deck wells on actual faces")
    dr_used = any(sme.materials[p.material_index] and
                  sme.materials[p.material_index].name.split(".")[0]
                  == "FI_Fleet_NAV_Drive" for p in sme.polygons)
    check(dr_used, "drive glow on actual faces")
    sm = ship.modifiers[0]
    for fi, key in ((1, "OXR"), (2, "NYX")):
        sm[ident(con, "FI_FleetShip", "Faction")] = fi
        ship.update_tag()
        mset_f = {m.name.split(".")[0]
                  for m in eval_mesh(ship).materials if m}
        check(f"FI_Fleet_{key}_Hull" in mset_f,
              f"{key} faction switches hull set")
    sm[ident(con, "FI_FleetShip", "Faction")] = 0
    sm[ident(con, "FI_FleetShip", "Class")] = 1
    ship.update_tag()
    me_cr = eval_mesh(ship)
    t_cr = tri_count(me_cr)
    ext_cr = max(v.co.x for v in me_cr.vertices) - \
        min(v.co.x for v in me_cr.vertices)
    check(t_cr < 120000, f"cruiser within budget (tris={t_cr})")
    check(ext_cr > 200, f"cruiser is cruiser-sized (L={ext_cr:.0f} m)")
    sm[ident(con, "FI_FleetShip", "Class")] = 0
    ship.update_tag()

    # nozzle count drives geometry
    nsums = []
    for nn in (1, 2, 3):
        sm[ident(con, "FI_FleetShip", "Nozzles")] = nn
        ship.update_tag()
        nsums.append(round(coord_sum(eval_mesh(ship))))
    check(len(set(nsums)) == 3, f"nozzle counts 1/2/3 differ ({nsums})")
    sm[ident(con, "FI_FleetShip", "Nozzles")] = 2

    # nose archetypes: all six differ
    nsty = []
    for s in range(6):
        sm[ident(con, "FI_FleetShip", "Nose Style")] = s
        ship.update_tag()
        nsty.append(round(coord_sum(eval_mesh(ship))))
    check(len(set(nsty)) == 6,
          f"six nose archetypes all differ ({nsty})")
    sm[ident(con, "FI_FleetShip", "Nose Style")] = 0
    ship.update_tag()

    # stern archetypes: all four differ
    ssty = []
    for s in range(4):
        sm[ident(con, "FI_FleetShip", "Stern Style")] = s
        ship.update_tag()
        ssty.append(round(coord_sum(eval_mesh(ship))))
    check(len(set(ssty)) == 4,
          f"four stern archetypes all differ ({ssty})")
    sm[ident(con, "FI_FleetShip", "Stern Style")] = 0
    ship.update_tag()

    # GOLDEN mono regression: geometry must only move when a deliberate
    # change ships (values re-baked 2026-07-15 for the native FI face
    # divider -- same statistics, different cut-fraction stream)
    s_g = coord_sum(eval_mesh(ship))
    check(abs(s_g - 1090990.5) < 1090990.5 * 2e-3,
          f"golden mono frigate (coord_sum={s_g:.1f} vs 1090990.5)")
    sm[ident(con, "FI_FleetShip", "Class")] = 1
    ship.update_tag()
    s_g2 = coord_sum(eval_mesh(ship))
    check(abs(s_g2 - 2525657.0) < 2525657.0 * 2e-3,
          f"golden mono cruiser (coord_sum={s_g2:.1f} vs 2525657.0)")
    sm[ident(con, "FI_FleetShip", "Class")] = 0
    ship.update_tag()

    # hull forms all differ + catamaran budget
    fsty = []
    for fv in (0, 1, 2):
        sm[ident(con, "FI_FleetShip", "Hull Form")] = fv
        ship.update_tag()
        fsty.append(round(coord_sum(eval_mesh(ship))))
    check(len(set(fsty)) == 3,
          f"hull forms mono/catamaran/asymmetric differ ({fsty})")
    sm[ident(con, "FI_FleetShip", "Hull Form")] = 1
    ship.update_tag()
    t_cat = tri_count(eval_mesh(ship))
    check(t_cat < 120000, f"catamaran frigate within budget ({t_cat})")
    sm[ident(con, "FI_FleetShip", "Hull Form")] = 0
    ship.update_tag()

    # towers and prow-pod counts all differ
    tsty = []
    for tv in (0, 1, 2):
        sm[ident(con, "FI_FleetShip", "Towers")] = tv
        ship.update_tag()
        tsty.append(round(coord_sum(eval_mesh(ship))))
    check(len(set(tsty)) == 3, f"tower counts 0/1/2 differ ({tsty})")
    sm[ident(con, "FI_FleetShip", "Towers")] = 1
    psty = []
    for pv in (0, 2, 3):
        sm[ident(con, "FI_FleetShip", "Prow Pods")] = pv
        ship.update_tag()
        psty.append(round(coord_sum(eval_mesh(ship))))
    check(len(set(psty)) == 3, f"prow pods 0/fork/trident differ ({psty})")
    sm[ident(con, "FI_FleetShip", "Prow Pods")] = 0
    ship.update_tag()

    # ---- knob sweep: every knob must reshape the ship --------------------
    ship.update_tag()
    base_sum = coord_sum(eval_mesh(ship))
    knobs = (
        ("Plateaus", (("Plateaus", 0),)),
        ("Plateau Height", (("Plateau Height", 1.0),)),
        ("Plateau Width", (("Plateau Width", 0.35),)),
        ("Chine", (("Chine", 1.0),)),
        ("Chine Slope", (("Chine Slope", 2.2),)),
        ("Bow Wedge", (("Bow Wedge", 0.42),)),
        ("Stern Block", (("Stern Block", 0.32),)),
        ("Keel", (("Keel", 0.0),)),
        ("Length Mult", (("Length Mult", 1.4),)),
        ("Beam Mult", (("Beam Mult", 1.4),)),
        ("Depth Mult", (("Depth Mult", 1.5),)),
        ("Panel Density", (("Panel Density", 4),)),
        ("Patchwork", (("Patchwork", 0.02),)),
        ("Accent Fields", (("Accent Fields", 0),)),
        ("Blisters", (("Blisters", 1.0),)),
        ("Accent Bands", (("Accent Bands", 0),)),
        ("Dorsal Stripe", (("Dorsal Stripe", True),)),
        ("Vents", (("Vents", 0),)),
        ("Radomes", (("Radomes", 0),)),
        ("Antennas", (("Antennas", 0),)),
        ("Sponsons", (("Sponsons", 3),)),
        ("Booms", (("Booms", False),)),
        ("Decals", (("Decals", 0),)),
        ("Thrusters", (("Thrusters", True),)),
        ("Nose Style", (("Nose Style", 3),)),
        ("Nose Taper", (("Nose Taper", 2.0),)),
        ("Nose Tip", (("Nose Tip", 0.2),)),
        ("Mass Bias", (("Mass Bias", 0.8),)),
        ("Waist", (("Waist", 0.7), ("Waist Position", 0.35))),
        ("Saddle", (("Saddle", 0.8),)),
        ("Stern Style", (("Stern Style", 1),)),
        ("Stern Taper", (("Stern Style", 1), ("Stern Taper", 2.0))),
        ("Stern Tip", (("Stern Style", 1), ("Stern Tip", 0.3))),
        ("Stern Rake", (("Stern Rake", 0.25),)),
        ("Deck Crown", (("Deck Crown", 0.6),)),
        ("Keel Crown", (("Keel Crown", 0.6),)),
        ("Chine 2", (("Chine 2", 0.8),)),
        ("Chine 2 Slope", (("Chine 2", 0.8), ("Chine 2 Slope", 2.8))),
        ("Towers", (("Towers", 0),)),
        ("Tower Height", (("Tower Height", 1.8),)),
        ("Tower Levels", (("Tower Levels", 1),)),
        ("Tower Width", (("Tower Width", 1.5),)),
        ("Tower Rake", (("Tower Rake", 0.9),)),
        ("Dorsal Fins", (("Dorsal Fins", 2),)),
        ("Ventral Fins", (("Ventral Fins", 1),)),
        ("Fin Size", (("Dorsal Fins", 2), ("Fin Size", 1.5),)),
        ("Prow Pods", (("Prow Pods", 2),)),
        ("Prow Pod Length", (("Prow Pods", 2), ("Prow Pod Length", 1.6))),
        ("Nacelles", (("Nacelles", 1),)),
        ("Nacelle Position", (("Nacelles", 1), ("Nacelle Position", 0.6))),
        ("Nacelle Standoff", (("Nacelles", 1), ("Nacelle Standoff", 0.4))),
        ("Nacelle Scale", (("Nacelles", 1), ("Nacelle Scale", 1.5))),
        ("Bow Mouth", (("Bow Mouth", 0.8),)),
        ("Overbite", (("Overbite", 0.8),)),
        ("Hangars", (("Hangars", 1),)),
        ("Hangar Size", (("Hangars", 1), ("Hangar Size", 1.5))),
        ("Deck Trench", (("Deck Trench", 0.8),)),
        ("Hull Form", (("Hull Form", 1),)),
        ("Hull Spacing", (("Hull Form", 1), ("Hull Spacing", 1.05))),
        ("Module Scale", (("Hull Form", 2), ("Module Scale", 0.6))),
        ("Bridge Blocks", (("Hull Form", 1), ("Bridge Blocks", 3))),
    )
    moved = 0
    for label, pairs in knobs:
        saved = []
        for name, val in pairs:
            keyid = ident(con, "FI_FleetShip", name)
            saved.append((keyid, sm.get(keyid, None)))
            sm[keyid] = val
        ship.update_tag()
        sv = coord_sum(eval_mesh(ship))
        if abs(sv - base_sum) > 0.5:
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
          f"knob sweep: {moved}/{len(knobs)} knobs reshape the ship")

    # ---- patchwork attrs live on the evaluated mesh ------------------------
    me_pw = eval_mesh(ship)
    tattr = me_pw.attributes.get("fi_tint")
    check(tattr is not None and tattr.domain == "FACE",
          "fi_tint face attribute present")
    if tattr is not None:
        vals = {round(d.value, 3) for d in tattr.data}
        check(len(vals) >= 8,
              f"fi_tint carries panel variety ({len(vals)} values)")
    aattr = me_pw.attributes.get("fi_accent")
    n_acc = sum(1 for d in aattr.data if d.value) if aattr else 0
    check(n_acc > 10, f"fi_accent marks accent fields ({n_acc} faces)")

    # ---- shader-only knobs live through ATTRIBUTES (no geometry) ----------
    def attr_sum(me2, name):
        a = me2.attributes.get(name)
        if a is None:
            return -1.0
        return sum(float(d.value) for d in a.data)

    l6 = attr_sum(me_pw, "fi_light")
    check(l6 > 1.0, f"fi_light band mask populated (sum={l6:.1f})")
    sm[ident(con, "FI_FleetShip", "Light Rows")] = 0
    ship.update_tag()
    l0 = attr_sum(eval_mesh(ship), "fi_light")
    check(l0 < l6 * 0.05,
          f"Light Rows gates the emission mask ({l6:.1f} -> {l0:.1f})")
    sm[ident(con, "FI_FleetShip", "Light Rows")] = 4
    sm[ident(con, "FI_FleetShip", "Window Glow")] = 0.0
    ship.update_tag()
    g0 = attr_sum(eval_mesh(ship), "fi_glowpanel")
    sm[ident(con, "FI_FleetShip", "Window Glow")] = 1.0
    ship.update_tag()
    g1 = attr_sum(eval_mesh(ship), "fi_glowpanel")
    check(g1 > g0 + 3, f"Window Glow scales lit panels ({g0:.0f} -> {g1:.0f})")
    sm[ident(con, "FI_FleetShip", "Window Glow")] = 0.4
    sm[ident(con, "FI_FleetShip", "Hue Jitter")] = 0.0
    ship.update_tag()
    h0 = attr_sum(eval_mesh(ship), "fi_hue")
    sm[ident(con, "FI_FleetShip", "Hue Jitter")] = 1.0
    ship.update_tag()
    h1 = attr_sum(eval_mesh(ship), "fi_hue")
    check(h1 > h0 + 1.0, f"Hue Jitter scales the hue attr ({h0:.1f} -> {h1:.1f})")
    sm[ident(con, "FI_FleetShip", "Hue Jitter")] = 0.35
    sm[ident(con, "FI_FleetShip", "Deck Markings")] = False
    ship.update_tag()
    dm0 = attr_sum(eval_mesh(ship), "fi_deckmark")
    sm[ident(con, "FI_FleetShip", "Deck Markings")] = True
    ship.update_tag()
    dm1 = attr_sum(eval_mesh(ship), "fi_deckmark")
    check(dm1 > dm0, f"Deck Markings gate the dash attr ({dm0:.0f} -> {dm1:.0f})")
    hull_mat = next(mm for mm in eval_mesh(ship).materials
                    if mm and mm.name.startswith("FI_Fleet_NAV_Hull"))
    nt = hull_mat.node_tree
    has_light_attr = any(n.bl_idname == "ShaderNodeAttribute" and
                         n.attribute_name == "fi_light" for n in nt.nodes)
    emis_linked = any(lk.to_socket.name == "Emission Strength"
                      for lk in nt.links)
    check(has_light_attr and emis_linked,
          "hull shader wires fi_light into emission")

    # ---- ISLAND OVERLAP: every attached shell must touch the hull ---------
    def island_overlap(me2, margin=0.01):
        from collections import defaultdict, deque
        vert_faces = defaultdict(list)
        for p in me2.polygons:
            for v in p.vertices:
                vert_faces[v].append(p.index)
        seen = set()
        shells = []
        for p in me2.polygons:
            if p.index in seen:
                continue
            q = deque([p.index])
            seen.add(p.index)
            lo = [1e9] * 3
            hi = [-1e9] * 3
            while q:
                f = me2.polygons[q.popleft()]
                for vi in f.vertices:
                    co = me2.vertices[vi].co
                    for k in range(3):
                        lo[k] = min(lo[k], co[k])
                        hi[k] = max(hi[k], co[k])
                    for nf in vert_faces[vi]:
                        if nf not in seen:
                            seen.add(nf)
                            q.append(nf)
            shells.append((lo, hi))
        # transitive attachment: a shell is attached if its AABB
        # overlaps any already-attached shell (antenna tips touch masts,
        # masts touch plates, plates touch the hull)
        def touches(a, b):
            return all(a[0][k] <= b[1][k] - margin and
                       a[1][k] >= b[0][k] + margin for k in range(3))

        main_i = max(range(len(shells)),
                     key=lambda i: (shells[i][1][0] - shells[i][0][0]) *
                     (shells[i][1][1] - shells[i][0][1]) *
                     (shells[i][1][2] - shells[i][0][2]))
        attached = {main_i}
        grew = True
        while grew:
            grew = False
            for i, s in enumerate(shells):
                if i in attached:
                    continue
                if any(touches(s, shells[j]) for j in attached):
                    attached.add(i)
                    grew = True
        return len(shells), len(shells) - len(attached)

    saved = []
    for k, v in {"Towers": 2, "Dorsal Fins": 2, "Ventral Fins": 1,
                 "Prow Pods": 3, "Nacelles": 2, "Sponsons": 3,
                 "Vents": 4, "Radomes": 2, "Antennas": 3, "Decals": 2,
                 "Nose Style": 1, "Nose Taper": 2.0}.items():
        kid = ident(con, "FI_FleetShip", k)
        saved.append((kid, sm.get(kid, None)))
        sm[kid] = v
    ship.update_tag()
    nsh, nbad = island_overlap(eval_mesh(ship))
    check(nbad == 0,
          f"island overlap: all {nsh} shells touch the hull ({nbad} float)")
    for kid, old_v in saved:
        if old_v is None:
            del sm[kid]
        else:
            sm[kid] = old_v
    ship.update_tag()

    # ---- WATERTIGHT: daylight edges == 0 at stress configs ----------------
    wt_configs = (
        ("frigate default", {}),
        ("frigate stress", {"Seed": 7, "Chine": 1.0, "Nozzles": 3,
                            "Bow Wedge": 0.42, "Stern Block": 0.32,
                            "Keel": 1.0, "Plateaus": 2,
                            "Plateau Height": 1.0, "Detail": 2,
                            "Panel Density": 4, "Patchwork": 1.0,
                            "Blisters": 1.0, "Accent Fields": 3,
                            "Light Rows": 6, "Vents": 4, "Radomes": 2,
                            "Antennas": 3, "Sponsons": 3, "Decals": 2,
                            "Thrusters": True}),
        ("cruiser stress", {"Seed": 4, "Class": 1, "Nozzles": 3,
                            "Chine": 0.1, "Keel": 1.0, "Detail": 1,
                            "Panel Density": 3, "Blisters": 1.0,
                            "Vents": 4, "Sponsons": 2,
                            "Thrusters": True}),
        ("nose stress", {"Seed": 7, "Nose Style": 3, "Nose Taper": 2.2,
                         "Nose Tip": 0.1, "Bow Wedge": 0.45,
                         "Panel Density": 4, "Detail": 2,
                         "Beam Mult": 0.5}),
        ("catamaran stress", {"Seed": 6, "Hull Form": 1,
                              "Hull Spacing": 1.05, "Bridge Blocks": 3,
                              "Hangars": 1, "Panel Density": 3,
                              "Towers": 2, "Nacelles": 1}),
        ("aperture stress", {"Seed": 3, "Bow Mouth": 1.0, "Hangars": 2,
                             "Hangar Size": 1.5, "Deck Trench": 1.0,
                             "Stern Style": 2, "Nose Style": 1,
                             "Panel Density": 4, "Detail": 2,
                             "Towers": 2, "Prow Pods": 3}),
        ("plan/section stress", {"Seed": 5, "Waist": 1.0,
                                 "Waist Position": 0.35, "Saddle": 0.8,
                                 "Mass Bias": 0.8, "Deck Crown": 0.75,
                                 "Keel Crown": 0.75, "Chine 2": 1.0,
                                 "Stern Style": 1, "Stern Tip": 0.15,
                                 "Stern Taper": 2.0,
                                 "Panel Density": 4, "Detail": 2}),
    )
    for wname, wp in wt_configs:
        saved = []
        for k, v in wp.items():
            kid = ident(con, "FI_FleetShip", k)
            saved.append((kid, sm.get(kid, None)))
            sm[kid] = v
        ship.update_tag()
        me_wt = eval_mesh(ship)
        ext_x = max(v.co.x for v in me_wt.vertices) - \
            min(v.co.x for v in me_wt.vertices)
        # tolerance scales mildly with hull size: divider split points on
        # curved faces drift ~1e-4 of hull length off the chord (visually
        # nil T-vert noise, unweldable); anything bigger is a real hole
        ngaps = daylight_gaps(me_wt, tol=max(0.005, ext_x * 1e-4))
        check(ngaps == 0, f"watertight at {wname} (daylight edges={ngaps})")
        for kid, old_v in saved:
            if old_v is None:
                del sm[kid]
            else:
                sm[kid] = old_v
        ship.update_tag()

    # ---- renders -----------------------------------------------------------
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
    for name, ctr, dist in (("fleet_hull", Vector((0, 200, 0)), 170.0),
                            ("fleet_frigate", Vector((0, 0, 0)), 180.0)):
        d = Vector((0.7, -1.0, 0.55)).normalized()
        cam.location = ctr + d * dist
        cam.rotation_euler = (ctr - cam.location).to_track_quat(
            "-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(OUTDIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)
        check(os.path.exists(scene.render.filepath), f"render {name}")

    print(f"\nfleet_selftest: {'ALL PASS' if not FAILS else 'FAILURES:'}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1 if FAILS else 0)


main()
