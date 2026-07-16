#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# station_selftest.py -- headless QA for FI_StationKit.blend.
#   blender -b --python station_selftest.py

import bpy
import json
import math
import os
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONKIT = os.path.join(HERE, "FI_StationKit.blend")
OUTDIR = os.path.join(HERE, "out", "station_selftest")
FAILS = []

# golden coord_sums: Seed 1, per-Form defaults. Geometry must only move
# when a deliberate change ships (baked 2026-07-16, W2 assembly + the
# island/corridor fixes: pad hub-roots, gantry tie beams, spine sans
# crown plateaus).
GOLDENS = {0: 85992455.1, 1: 47736947.6, 2: 36217694.1, 3: 33543125.4}


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


def shells_and_bboxes(me2):
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
        faces = []
        while q:
            fi = q.popleft()
            faces.append(fi)
            f = me2.polygons[fi]
            for vi in f.vertices:
                co = me2.vertices[vi].co
                for k in range(3):
                    lo[k] = min(lo[k], co[k])
                    hi[k] = max(hi[k], co[k])
                for nf in vert_faces[vi]:
                    if nf not in seen:
                        seen.add(nf)
                        q.append(nf)
        shells.append((lo, hi, faces))
    return shells


def island_overlap(me2, margin=0.01):
    shells = [(lo, hi) for lo, hi, _ in shells_and_bboxes(me2)]

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


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(STATIONKIT, link=True) as (s, d):
        d.node_groups = list(s.node_groups)
    con = json.load(open(os.path.join(HERE, "station_contract.json")))
    os.makedirs(OUTDIR, exist_ok=True)
    groups = {ng.name: ng for ng in bpy.data.node_groups}
    for want in ("FI_Station", "FI_StationProfile", "FI_StationCore",
                 "FI_StationDress", "FI_StationCoreDressed",
                 "FI_StationTruss", "FI_StationTank", "FI_DockPad",
                 "FI_DockMaw", "FI_StationRing", "FI_StationTurret",
                 "FI_StationArm", "FI_StationVentGrate",
                 "FI_StationRadome", "FI_StationAntennaMast",
                 "FI_StationSensorBoom", "FI_StationChevron",
                 "FI_StationHullNumber"):
        check(want in groups, f"stationkit provides {want}")
    # the kit is self-contained: no fleet-named datablocks leak in
    leaked = [n for n in groups if n.startswith("FI_Fleet")]
    check(not leaked, f"no fleet groups leak into the kit ({leaked})")

    def gen(name, group, at, params=None):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.scene.collection.objects.link(ob)
        ob.location = at
        m = ob.modifiers.new("m", "NODES")
        m.node_group = groups[group]
        for k, v in (params or {}).items():
            m[ident(con, group, k)] = v
        return ob

    # ---- component budgets -------------------------------------------
    for gname, lo, hi in (("FI_StationTruss", 100, 12000),
                          ("FI_StationTank", 60, 5000),
                          ("FI_DockPad", 60, 4000),
                          ("FI_StationRing", 50, 2500),
                          ("FI_StationTurret", 50, 1500),
                          ("FI_DockMaw", 800, 40000),
                          ("FI_StationArm", 200, 16000),
                          ("FI_StationVentGrate", 40, 2500),
                          ("FI_StationRadome", 40, 3000),
                          ("FI_StationAntennaMast", 30, 1200),
                          ("FI_StationSensorBoom", 20, 600),
                          ("FI_StationChevron", 20, 300),
                          ("FI_StationHullNumber", 20, 800),
                          ("FI_StationCoreDressed", 2000, 40000)):
        ob = gen(f"t_{gname}", gname, (0, -3000, 0))
        t = tri_count(eval_mesh(ob))
        check(lo < t < hi, f"{gname} budget {lo}<{t}<{hi}")

    # ---- component variants respond ----------------------------------
    tr = bpy.data.objects["t_FI_StationTruss"]
    tsums = []
    for b in (2, 6, 12):
        tr.modifiers[0][ident(con, "FI_StationTruss", "Bays")] = b
        tr.update_tag()
        tsums.append(round(coord_sum(eval_mesh(tr))))
    check(len(set(tsums)) == 3, f"truss bay counts differ ({tsums})")
    tk = bpy.data.objects["t_FI_StationTank"]
    ksums = []
    for c in (1, 4, 7):
        tk.modifiers[0][ident(con, "FI_StationTank", "Count")] = c
        tk.update_tag()
        ksums.append(round(coord_sum(eval_mesh(tk))))
    check(len(set(ksums)) == 3, f"tank counts 1/4/7 differ ({ksums})")
    ar = bpy.data.objects["t_FI_StationArm"]
    asums = []
    for st in (0, 1, 2):
        ar.modifiers[0][ident(con, "FI_StationArm", "Module Style")] = st
        ar.update_tag()
        asums.append(round(coord_sum(eval_mesh(ar))))
    check(len(set(asums)) == 3,
          f"arm module styles box/drum/rack differ ({asums})")

    # ---- profile styles all differ (via the dressed core) -------------
    core = gen("t_core", "FI_StationCoreDressed", (0, 3000, 0),
               {"Seed": 3})
    cm = core.modifiers[0]
    csty = []
    for s in range(5):
        cm[ident(con, "FI_StationCoreDressed", "Style")] = s
        core.update_tag()
        csty.append(round(coord_sum(eval_mesh(core))))
    check(len(set(csty)) == 5,
          f"five silhouette styles all differ ({csty})")
    cm[ident(con, "FI_StationCoreDressed", "Style")] = 0
    core.update_tag()

    # towers stack monotonically on the crown
    zmaxes = []
    for tu in (0, 1, 3):
        cm[ident(con, "FI_StationCoreDressed", "Towers Up")] = tu
        core.update_tag()
        zmaxes.append(max(v.co.z for v in eval_mesh(core).vertices))
    check(zmaxes[0] < zmaxes[1] <= zmaxes[2] + 1e-6,
          f"crown towers raise the skyline "
          f"({[f'{z:.1f}' for z in zmaxes]})")
    zmins = []
    for td in (0, 2):
        cm[ident(con, "FI_StationCoreDressed", "Towers Down")] = td
        core.update_tag()
        zmins.append(min(v.co.z for v in eval_mesh(core).vertices))
    check(zmins[1] < zmins[0],
          f"keel towers grow DOWNWARD ({[f'{z:.1f}' for z in zmins]})")

    # ---- station: per-form evaluation, budgets, goldens ---------------
    st = gen("t_station", "FI_Station", (0, 0, 0), {"Seed": 1})
    sm = st.modifiers[0]
    FORM_NAMES = ("spire", "yard", "saucer", "bastion")
    D0_BUDGET = (70000, 60000, 55000, 35000)
    fsums = []
    for f in range(4):
        sm[ident(con, "FI_Station", "Form")] = f
        st.update_tag()
        me_f = eval_mesh(st)
        t_f = tri_count(me_f)
        fsums.append(round(coord_sum(me_f)))
        check(4000 < t_f < D0_BUDGET[f],
              f"{FORM_NAMES[f]} Detail-0 budget 4000<{t_f}<{D0_BUDGET[f]}")
        if GOLDENS[f] is None:
            print(f"  GOLDEN-BAKE  Form {f} ({FORM_NAMES[f]}): "
                  f"coord_sum={coord_sum(me_f):.1f}")
        else:
            g = GOLDENS[f]
            sv = coord_sum(me_f)
            check(abs(sv - g) < g * 2e-3,
                  f"golden {FORM_NAMES[f]} (coord_sum={sv:.1f} vs {g})")
    check(len(set(fsums)) == 4, f"four forms all differ ({fsums})")
    sm[ident(con, "FI_Station", "Form")] = 0
    st.update_tag()

    # ---- factions: all four swap the hull set (proves FPT wiring) ------
    for fi, key in ((0, "NAV"), (1, "OXR"), (2, "NYX"), (3, "FPT")):
        sm[ident(con, "FI_Station", "Faction")] = fi
        st.update_tag()
        mset = {m.name.split(".")[0] for m in eval_mesh(st).materials if m}
        check(f"FI_Station_{key}_Hull" in mset,
              f"faction {fi} swaps in the {key} hull set")
    sm[ident(con, "FI_Station", "Faction")] = 0
    st.update_tag()

    # materials land on actual faces
    me_sp = eval_mesh(st)

    def mat_on_faces(me2, name):
        return any(me2.materials[p.material_index] and
                   me2.materials[p.material_index].name.split(".")[0]
                   == name for p in me2.polygons)

    check(mat_on_faces(me_sp, "FI_Station_NAV_Deck"),
          "deck platforms on actual faces (spire plateaus)")
    check(mat_on_faces(me_sp, "FI_Station_Beacon"),
          "nav beacons on actual faces")
    sm[ident(con, "FI_Station", "Form")] = 1
    st.update_tag()
    me_yd = eval_mesh(st)
    check(mat_on_faces(me_yd, "FI_Station_NAV_Glow"),
          "maw glow throat on actual faces (yard)")
    check(mat_on_faces(me_yd, "FI_Station_Truss"),
          "gantry truss material on actual faces (yard)")
    sm[ident(con, "FI_Station", "Form")] = 2
    st.update_tag()
    check(mat_on_faces(eval_mesh(st), "FI_Station_Pad"),
          "landing pads on actual faces (saucer)")
    sm[ident(con, "FI_Station", "Form")] = 0
    st.update_tag()

    # ---- knob sweep: every knob must reshape its live form -------------
    # (attr-only and material-only knobs are checked separately below)
    SWEEP = {
        0: (
            ("Seed", (("Seed", 9),)),
            ("Class", (("Class", 1),)),
            ("Detail", (("Detail", 1),)),
            ("Scale", (("Scale", 1.5),)),
            ("Height Mult", (("Height Mult", 1.5),)),
            ("Footprint Mult", (("Footprint Mult", 1.5),)),
            ("Silhouette Style", (("Silhouette Style", 2),)),
            ("Tiers", (("Tiers", 7),)),
            ("Tier Jitter", (("Tier Jitter", 1.0),)),
            ("Taper Top", (("Taper Top", 1.0),)),
            ("Taper Bottom", (("Taper Bottom", 1.0),)),
            ("Bulge", (("Silhouette Style", 1), ("Bulge", 1.0))),
            ("Bulge Position", (("Silhouette Style", 1),
                                ("Bulge", 1.0), ("Bulge Position", 0.25))),
            ("Waist", (("Waist", 0.8),)),
            ("Skyline", (("Skyline", 1.0),)),
            ("Corner Cut", (("Corner Cut", 0.0),)),
            ("Corner Cut Slope", (("Corner Cut", 0.9),
                                  ("Corner Cut Slope", 2.6))),
            ("Footprint Aspect", (("Footprint Aspect", 0.6),)),
            ("Base Flare", (("Base Flare", 1.0),)),
            ("Ledges", (("Ledges", 0),)),
            ("Ledge Depth", (("Ledge Depth", 1.0),)),
            ("Top Plateaus", (("Top Plateaus", 0),)),
            ("Plateau Height", (("Plateau Height", 1.0),)),
            ("Towers Up", (("Towers Up", 0),)),
            ("Towers Down", (("Towers Down", 3),)),
            ("Tower Height", (("Tower Height", 2.0),)),
            ("Tower Rake", (("Tower Rake", 1.0),)),
            ("Arms", (("Arms", 0),)),
            ("Arm Length", (("Arm Length", 1.1),)),
            ("Arm Levels", (("Arm Levels", 3),)),
            ("Arm Stagger", (("Arm Stagger", 1.0),)),
            ("Arm Phase", (("Arm Phase", 2.5),)),
            ("Arm Module Scale", (("Arm Module Scale", 1.7),)),
            ("Arm Truss", (("Arm Truss", True),)),
            ("Ring", (("Ring", 2),)),
            ("Ring Radius", (("Ring", 1), ("Ring Radius", 1.35))),
            ("Spires", (("Spires", 0),)),
            ("Spire Height", (("Spire Height", 2.0),)),
            ("Turrets", (("Turrets", 4),)),
            ("Turret Scale", (("Turrets", 4), ("Turret Scale", 1.8))),
            ("Vents", (("Vents", 0),)),
            ("Radomes", (("Radomes", 0),)),
            ("Antennas", (("Antennas", 0),)),
            ("Decals", (("Decals", 0),)),
            ("Beacons", (("Beacons", 0),)),
            ("Panel Density", (("Panel Density", 1),)),
            ("Patchwork", (("Patchwork", 0.02),)),
            ("Accent Fields", (("Accent Fields", 0),)),
            ("Accent Bands", (("Accent Bands", 0),)),
            # isolate the stripe: the default accent fields already
            # cover |x|<0.1, so the stripe alone would be a no-op
            ("Meridian Stripe", (("Accent Fields", 0),
                                 ("Accent Bands", 0),
                                 ("Meridian Stripe", True))),
            ("Blisters", (("Blisters", 1.0),)),
            ("Trenches", (("Trenches", 2),)),
            ("Trench Depth", (("Trenches", 2), ("Trench Depth", 1.0))),
            ("Hangars", (("Hangars", 1),)),
            ("Hangar Size", (("Hangars", 1), ("Hangar Size", 1.5))),
        ),
        1: (
            ("Spine Stretch", (("Spine Stretch", 2.5),)),
            ("Gantries", (("Gantries", 0),)),
            ("Gantry Spacing", (("Gantry Spacing", 1.4),)),
            ("Cranes", (("Cranes", 0),)),
            ("Maw", (("Maw", 0.0),)),
            ("Maw Aspect", (("Maw Aspect", 1.5),)),
            ("Maw Depth", (("Maw Depth", 1.4),)),
            ("Tank Clusters", (("Tank Clusters", 0),)),
            ("Tanks Per Cluster", (("Tanks Per Cluster", 7),)),
            ("Tank Scale", (("Tank Scale", 1.7),)),
        ),
        2: (
            ("Pads", (("Pads", 0),)),
            ("Pad Radius", (("Pad Radius", 1.02),)),
            ("Pad Size", (("Pad Size", 1.5),)),
            ("Pad Tier", (("Pad Tier", 1.0),)),
        ),
    }
    moved = total = 0
    for form, knobs in SWEEP.items():
        sm[ident(con, "FI_Station", "Form")] = form
        st.update_tag()
        base_sum = coord_sum(eval_mesh(st))
        for label, pairs in knobs:
            total += 1
            saved = []
            for name, val in pairs:
                keyid = ident(con, "FI_Station", name)
                saved.append((keyid, sm.get(keyid, None)))
                sm[keyid] = val
            st.update_tag()
            sv = coord_sum(eval_mesh(st))
            if abs(sv - base_sum) > 0.5:
                moved += 1
            else:
                print(f"  KNOB-DEAD (form {form}):", label)
            for keyid, old_v in saved:
                if old_v is None:
                    del sm[keyid]
                else:
                    sm[keyid] = old_v
            st.update_tag()
    check(moved == total, f"knob sweep: {moved}/{total} knobs reshape")
    sm[ident(con, "FI_Station", "Form")] = 0
    st.update_tag()

    # completeness: every contract INPUT socket is either swept or on
    # the documented exempt list — a new knob cannot dodge the sweep
    swept = {label for knobs in SWEEP.values() for label, _ in knobs}
    exempt = {
        "Form",           # covered by the four-forms-differ check
        "Faction",        # material-only, covered by the faction check
        "Window Glow",    # attr-only  (fi_glowpanel check below)
        "Hue Jitter",     # attr-only  (fi_hue check below)
        "Light Rows",     # attr-only  (fi_light check below)
        "Deck Markings",  # attr-only  (fi_deckmark check below)
    }
    allin = {it["name"] for it in con["FI_Station"]
             if it["in_out"] == "INPUT"}
    missing = sorted(allin - swept - exempt)
    check(not missing, f"sweep covers the whole contract (missing: "
                       f"{missing})")

    # ---- patchwork attrs live on the evaluated mesh --------------------
    me_pw = eval_mesh(st)
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

    def attr_sum(me2, name):
        a = me2.attributes.get(name)
        if a is None:
            return -1.0
        return sum(float(d.value) for d in a.data)

    l6 = attr_sum(me_pw, "fi_light")
    check(l6 > 1.0, f"fi_light band mask populated (sum={l6:.1f})")
    sm[ident(con, "FI_Station", "Light Rows")] = 0
    st.update_tag()
    l0 = attr_sum(eval_mesh(st), "fi_light")
    check(l0 < l6 * 0.05,
          f"Light Rows gates the emission mask ({l6:.1f} -> {l0:.1f})")
    sm[ident(con, "FI_Station", "Light Rows")] = 4
    sm[ident(con, "FI_Station", "Window Glow")] = 0.0
    st.update_tag()
    g0 = attr_sum(eval_mesh(st), "fi_glowpanel")
    sm[ident(con, "FI_Station", "Window Glow")] = 1.0
    st.update_tag()
    g1 = attr_sum(eval_mesh(st), "fi_glowpanel")
    check(g1 > g0 + 3,
          f"Window Glow scales lit panels ({g0:.0f} -> {g1:.0f})")
    check(g1 > 30, f"night-city coverage floor at full glow ({g1:.0f})")
    sm[ident(con, "FI_Station", "Window Glow")] = 0.5
    sm[ident(con, "FI_Station", "Hue Jitter")] = 0.0
    st.update_tag()
    h0 = attr_sum(eval_mesh(st), "fi_hue")
    sm[ident(con, "FI_Station", "Hue Jitter")] = 1.0
    st.update_tag()
    h1 = attr_sum(eval_mesh(st), "fi_hue")
    check(h1 > h0 + 1.0,
          f"Hue Jitter scales the hue attr ({h0:.1f} -> {h1:.1f})")
    sm[ident(con, "FI_Station", "Hue Jitter")] = 0.35
    sm[ident(con, "FI_Station", "Deck Markings")] = False
    st.update_tag()
    dm0 = attr_sum(eval_mesh(st), "fi_deckmark")
    sm[ident(con, "FI_Station", "Deck Markings")] = True
    st.update_tag()
    dm1 = attr_sum(eval_mesh(st), "fi_deckmark")
    check(dm1 > dm0,
          f"Deck Markings gate the dash attr ({dm0:.0f} -> {dm1:.0f})")
    hull_mat = next(mm for mm in eval_mesh(st).materials
                    if mm and mm.name.startswith("FI_Station_NAV_Hull"))
    nt = hull_mat.node_tree
    has_light_attr = any(n.bl_idname == "ShaderNodeAttribute" and
                         n.attribute_name == "fi_light" for n in nt.nodes)
    emis_linked = any(lk.to_socket.name == "Emission Strength"
                      for lk in nt.links)
    check(has_light_attr and emis_linked,
          "hull shader wires fi_light into emission")

    # ---- island overlap at greeble-max, per form -----------------------
    GREEBLE_MAX = {"Arms": 6, "Arm Levels": 3, "Ring": 2, "Spires": 3,
                   "Turrets": 8, "Vents": 4, "Radomes": 2, "Antennas": 3,
                   "Decals": 2, "Beacons": 4, "Tank Clusters": 4,
                   "Gantries": 6, "Cranes": 4, "Pads": 10}
    for form in range(4):
        saved = []
        for k, v in dict(GREEBLE_MAX, Form=form).items():
            kid = ident(con, "FI_Station", k)
            saved.append((kid, sm.get(kid, None)))
            sm[kid] = v
        st.update_tag()
        nsh, nbad = island_overlap(eval_mesh(st))
        check(nbad == 0,
              f"island overlap {FORM_NAMES[form]}: all {nsh} shells "
              f"attach ({nbad} float)")
        for kid, old_v in saved:
            if old_v is None:
                del sm[kid]
            else:
                sm[kid] = old_v
        st.update_tag()

    # ---- watertight: daylight edges == 0 at stress configs -------------
    wt_configs = (
        ("spire default", {}),
        ("spire stress", {"Form": 0, "Detail": 2, "Panel Density": 4,
                          "Arms": 6, "Arm Levels": 3, "Ring": 2,
                          "Towers Up": 3, "Towers Down": 3,
                          "Spires": 3, "Seed": 5, "Patchwork": 1.0,
                          "Blisters": 1.0, "Trenches": 2, "Hangars": 2}),
        ("yard stress", {"Form": 1, "Detail": 2, "Gantries": 6,
                         "Cranes": 4, "Tank Clusters": 4, "Maw": 1.0,
                         "Maw Aspect": 1.5, "Spine Stretch": 2.5,
                         "Panel Density": 3, "Seed": 9}),
        ("yard sparse", {"Form": 1, "Gantries": 0, "Cranes": 0,
                         "Tank Clusters": 0, "Maw": 0.0,
                         "Spine Stretch": 1.0, "Seed": 2}),
        ("saucer stress", {"Form": 2, "Detail": 2, "Pads": 12,
                           "Corner Cut": 0.9, "Panel Density": 4,
                           "Seed": 3}),
        ("saucer thin", {"Form": 2, "Height Mult": 0.5, "Pads": 8,
                         "Silhouette Style": 1, "Seed": 8}),
        ("bastion stress", {"Form": 3, "Detail": 2, "Turrets": 8,
                            "Trenches": 4, "Trench Depth": 1.0,
                            "Tank Clusters": 2, "Panel Density": 4,
                            "Seed": 7}),
        ("class-1 spire", {"Form": 0, "Class": 1, "Detail": 2,
                           "Seed": 11}),
    )
    for wname, wp in wt_configs:
        saved = []
        for k, v in wp.items():
            kid = ident(con, "FI_Station", k)
            saved.append((kid, sm.get(kid, None)))
            sm[kid] = v
        st.update_tag()
        me_wt = eval_mesh(st)
        ext = [max(v.co[i] for v in me_wt.vertices) -
               min(v.co[i] for v in me_wt.vertices) for i in range(3)]
        ngaps = daylight_gaps(me_wt, tol=max(0.005, max(ext) * 1e-4))
        check(ngaps == 0, f"watertight at {wname} (daylight edges={ngaps})")
        for kid, old_v in saved:
            if old_v is None:
                del sm[kid]
            else:
                sm[kid] = old_v
        st.update_tag()

    # ---- station-specific invariants ------------------------------------
    # spire verticality
    me_s0 = eval_mesh(st)
    ext0 = [max(v.co[i] for v in me_s0.vertices) -
            min(v.co[i] for v in me_s0.vertices) for i in range(3)]
    check(ext0[2] > 1.4 * max(ext0[0], ext0[1]),
          f"spire is vertical (Z={ext0[2]:.0f} vs XY="
          f"{max(ext0[0], ext0[1]):.0f})")
    # yard horizontality + the maw corridor is genuinely open
    saved = []
    for k, v in (("Form", 1), ("Maw", 1.0), ("Maw Aspect", 1.0),
                 ("Maw Depth", 1.0), ("Spine Stretch", 1.6),
                 ("Scale", 1.0), ("Footprint Mult", 1.0),
                 ("Height Mult", 1.0), ("Class", 0)):
        kid = ident(con, "FI_Station", k)
        saved.append((kid, sm.get(kid, None)))
        sm[kid] = v
    st.update_tag()
    me_y = eval_mesh(st)
    ext_y = [max(v.co[i] for v in me_y.vertices) -
             min(v.co[i] for v in me_y.vertices) for i in range(3)]
    check(ext_y[0] > 1.8 * max(ext_y[1], ext_y[2]),
          f"yard is a horizontal spine (X={ext_y[0]:.0f})")
    # docking corridor: the maw channel interior must contain no verts
    W0, H0 = 140.0, 380.0
    mawW = W0 * 1.0 * (0.55 + 0.55 * 1.0)
    mawD = W0 * 1.1 * 1.0
    maw_x = H0 * 1.6 * 0.5 + mawD * 0.22
    n_inside = sum(1 for v in me_y.vertices
                   if abs(v.co.x - maw_x) < mawD * 0.18
                   and abs(v.co.y) < mawW * 0.24
                   and -0.08 * mawW < v.co.z < 0.22 * mawW)
    check(n_inside == 0,
          f"maw docking corridor is open ({n_inside} verts inside)")
    for kid, old_v in saved:
        if old_v is None:
            del sm[kid]
        else:
            sm[kid] = old_v
    st.update_tag()
    # saucer roundness + pad count matches the knob
    saved = []
    for k, v in (("Form", 2), ("Silhouette Style", 1), ("Skyline", 0.0),
                 ("Footprint Aspect", 1.0), ("Pads", 0), ("Arms", 0)):
        kid = ident(con, "FI_Station", k)
        saved.append((kid, sm.get(kid, None)))
        sm[kid] = v
    st.update_tag()
    me_sc = eval_mesh(st)
    ext_sc = [max(v.co[i] for v in me_sc.vertices) -
              min(v.co[i] for v in me_sc.vertices) for i in range(3)]
    ratio = ext_sc[0] / max(ext_sc[1], 1e-6)
    check(0.90 < ratio < 1.10,
          f"saucer footprint is round (X/Y={ratio:.3f})")
    kid_p = ident(con, "FI_Station", "Pads")
    for want in (2, 4, 6):
        sm[kid_p] = want
        st.update_tag()
        me_p = eval_mesh(st)
        pad_shells = 0
        for lo, hi, faces in shells_and_bboxes(me_p):
            if any(me_p.materials[me_p.polygons[f].material_index] and
                   me_p.materials[
                       me_p.polygons[f].material_index].name.split(".")[0]
                   == "FI_Station_Pad" for f in faces):
                pad_shells += 1
        check(pad_shells == want,
              f"saucer pad shells == knob ({pad_shells} vs {want})")
    for kid, old_v in saved:
        if old_v is None:
            del sm[kid]
        else:
            sm[kid] = old_v
    st.update_tag()
    # bastion trenches carve visible dark bands
    saved = []
    for k, v in (("Form", 3), ("Trenches", 3), ("Trench Depth", 1.0)):
        kid = ident(con, "FI_Station", k)
        saved.append((kid, sm.get(kid, None)))
        sm[kid] = v
    st.update_tag()
    me_b = eval_mesh(st)
    n_dark = sum(1 for p in me_b.polygons
                 if me_b.materials[p.material_index] and
                 me_b.materials[p.material_index].name.split(".")[0]
                 in ("FI_Station_Dark", "FI_Station_Cavity"))
    check(n_dark > 20,
          f"bastion trenches carve dark bands ({n_dark} faces)")
    for kid, old_v in saved:
        if old_v is None:
            del sm[kid]
        else:
            sm[kid] = old_v
    st.update_tag()
    # scale calibration: defaults land in the 300-1500 m envelope and
    # Scale is linear
    exts = {}
    kid_c = ident(con, "FI_Station", "Class")
    for cl in (0, 1):
        sm[kid_c] = cl
        st.update_tag()
        me_c = eval_mesh(st)
        exts[cl] = max(max(v.co[i] for v in me_c.vertices) -
                       min(v.co[i] for v in me_c.vertices)
                       for i in range(3))
    check(300 <= exts[0] <= 900,
          f"class-0 envelope ({exts[0]:.0f} m)")
    check(900 <= exts[1] <= 1500 * 1.05,
          f"class-1 envelope ({exts[1]:.0f} m)")
    sm[kid_c] = 0
    kid_s = ident(con, "FI_Station", "Scale")
    sm[kid_s] = 0.75
    st.update_tag()
    e_lo = max(max(v.co[i] for v in eval_mesh(st).vertices) -
               min(v.co[i] for v in eval_mesh(st).vertices)
               for i in range(3))
    sm[kid_s] = 1.5
    st.update_tag()
    e_hi = max(max(v.co[i] for v in eval_mesh(st).vertices) -
               min(v.co[i] for v in eval_mesh(st).vertices)
               for i in range(3))
    check(abs(e_hi / e_lo - 2.0) < 0.05,
          f"Scale is linear ({e_hi:.0f}/{e_lo:.0f}={e_hi / e_lo:.3f})")
    sm[kid_s] = 1.0
    st.update_tag()

    # ---- renders: one per form, camera framed from the evaluated bbox --
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 900
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("s", "SUN"))
    sun.rotation_euler = (math.radians(55), 0, math.radians(30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("c"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.clip_end = 100000.0
    for f in range(4):
        sm[ident(con, "FI_Station", "Form")] = f
        st.update_tag()
        me_r = eval_mesh(st)
        ctr = Vector((0.0, 0.0, 0.0))
        rad = max(max(abs(v.co[i]) for v in me_r.vertices)
                  for i in range(3))
        d = Vector((0.7, -1.0, 0.55)).normalized()
        cam.location = ctr + d * rad * 3.2
        cam.rotation_euler = (ctr - cam.location).to_track_quat(
            "-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(
            OUTDIR, f"station_{FORM_NAMES[f]}.png")
        bpy.ops.render.render(write_still=True)
        check(os.path.exists(scene.render.filepath),
              f"render station_{FORM_NAMES[f]}")
    sm[ident(con, "FI_Station", "Form")] = 0

    print(f"\nstation_selftest: {'ALL PASS' if not FAILS else 'FAILURES:'}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1 if FAILS else 0)


main()
