#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# building_selftest.py -- headless QA for FI_BuildingKit.blend.
#   blender -b --python building_selftest.py

import bpy
import json
import math
import os
import sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDINGKIT = os.path.join(HERE, "FI_BuildingKit.blend")
OUTDIR = os.path.join(HERE, "out", "building_selftest")
FAILS = []

# golden coord_sums: Seed 1, per-Form defaults at LOD 0.
GOLDENS = {0: 3962438.8, 1: 1607266.3, 2: 1109509.0,
           3: 6328804.6}

# per-LOD tri ceilings (city instancing budget) and degenerate floors
LOD_CEILING = (12000, 4000, 1000)
LOD_FLOOR = (1500, 400, 50)


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
    with bpy.data.libraries.load(BUILDINGKIT, link=True) as (s, d):
        d.node_groups = list(s.node_groups)
    con = json.load(open(os.path.join(HERE, "building_contract.json")))
    os.makedirs(OUTDIR, exist_ok=True)
    groups = {ng.name: ng for ng in bpy.data.node_groups}
    for want in ("FI_Building", "FI_BuildingProfile", "FI_BuildingCore",
                 "FI_BuildingDress", "FI_BuildingCoreDressed",
                 "FI_BuildingTruss", "FI_BuildingTank", "FI_BuildingPad",
                 "FI_BuildingPlinth", "FI_Stack", "FI_PipeRun",
                 "FI_BuildingVentGrate", "FI_BuildingRadome",
                 "FI_BuildingAntennaMast", "FI_BuildingSensorBoom",
                 "FI_BuildingChevron", "FI_BuildingHullNumber"):
        check(want in groups, f"buildingkit provides {want}")
    # node groups are self-contained; station MATERIALS are expected
    # (cities colour-match their orbitals) but station/fleet GROUPS not
    leaked = [n for n in groups
              if n.startswith("FI_Fleet") or n.startswith("FI_Station")]
    check(not leaked, f"no fleet/station groups leak into the kit "
                      f"({leaked})")

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
    for gname, lo, hi in (("FI_BuildingPlinth", 80, 2500),
                          ("FI_Stack", 50, 1500),
                          ("FI_PipeRun", 100, 4000),
                          ("FI_BuildingTruss", 100, 12000),
                          ("FI_BuildingTank", 60, 5000),
                          ("FI_BuildingPad", 60, 4000),
                          ("FI_BuildingVentGrate", 40, 2500),
                          ("FI_BuildingRadome", 40, 3000),
                          ("FI_BuildingAntennaMast", 30, 1200),
                          ("FI_BuildingCoreDressed", 2000, 40000)):
        ob = gen(f"t_{gname}", gname, (0, -3000, 0))
        t = tri_count(eval_mesh(ob))
        check(lo < t < hi, f"{gname} budget {lo}<{t}<{hi}")

    # ---- component variants respond ----------------------------------
    stk = bpy.data.objects["t_FI_Stack"]
    ssums = []
    for c in (0, 2, 3):
        stk.modifiers[0][ident(con, "FI_Stack", "Collars")] = c
        stk.update_tag()
        ssums.append(round(coord_sum(eval_mesh(stk))))
    check(len(set(ssums)) == 3, f"stack collar counts differ ({ssums})")
    pr = bpy.data.objects["t_FI_PipeRun"]
    psums = []
    for c in (1, 3, 4):
        pr.modifiers[0][ident(con, "FI_PipeRun", "Pipes")] = c
        pr.update_tag()
        psums.append(round(coord_sum(eval_mesh(pr))))
    check(len(set(psums)) == 3, f"pipe counts 1/3/4 differ ({psums})")
    pl = bpy.data.objects["t_FI_BuildingPlinth"]
    esums = []
    for c in (0, 1, 2):
        pl.modifiers[0][ident(con, "FI_BuildingPlinth", "Entrances")] = c
        pl.update_tag()
        esums.append(round(coord_sum(eval_mesh(pl))))
    check(len(set(esums)) == 3, f"plinth entrances 0/1/2 differ ({esums})")

    # ---- building: Form x LOD matrix ---------------------------------
    st = gen("t_building", "FI_Building", (0, 0, 0), {"Seed": 1})
    sm = st.modifiers[0]
    FORM_NAMES = ("tower", "works", "hab", "spaceport")
    kid_form = ident(con, "FI_Building", "Form")
    kid_lod = ident(con, "FI_Building", "LOD")
    lod_tris = {}
    lod_ext = {}
    fsums = []
    for f in range(4):
        sm[kid_form] = f
        for lodv in range(3):
            sm[kid_lod] = lodv
            st.update_tag()
            me_f = eval_mesh(st)
            t_f = tri_count(me_f)
            lod_tris[(f, lodv)] = t_f
            lod_ext[(f, lodv)] = [
                max(v.co[i] for v in me_f.vertices) -
                min(v.co[i] for v in me_f.vertices) for i in range(3)]
            check(LOD_FLOOR[lodv] < t_f < LOD_CEILING[lodv],
                  f"{FORM_NAMES[f]} lod{lodv} budget "
                  f"{LOD_FLOOR[lodv]}<{t_f}<{LOD_CEILING[lodv]}")
            # grounded invariant: base plane sits at z = 0
            minz = min(v.co.z for v in me_f.vertices)
            check(abs(minz) < 0.02,
                  f"{FORM_NAMES[f]} lod{lodv} grounded (min z="
                  f"{minz:.3f})")
            if lodv == 0:
                fsums.append(round(coord_sum(me_f)))
                if GOLDENS[f] is None:
                    print(f"  GOLDEN-BAKE  Form {f} ({FORM_NAMES[f]}): "
                          f"coord_sum={coord_sum(me_f):.1f}")
                else:
                    gld = GOLDENS[f]
                    sv = coord_sum(me_f)
                    check(abs(sv - gld) < gld * 2e-3,
                          f"golden {FORM_NAMES[f]} (coord_sum={sv:.1f} "
                          f"vs {gld})")
        # LOD monotonicity: strictly decreasing tris
        check(lod_tris[(f, 0)] > lod_tris[(f, 1)] > lod_tris[(f, 2)],
              f"{FORM_NAMES[f]} LOD tris strictly decrease "
              f"({lod_tris[(f, 0)]}>{lod_tris[(f, 1)]}>"
              f"{lod_tris[(f, 2)]})")
        # massing preservation: the shell keeps >= 75% of the dressed
        # extent per axis (fixtures/masts legitimately shrink the bbox)
        for ax in range(3):
            r = lod_ext[(f, 2)][ax] / max(lod_ext[(f, 0)][ax], 1e-6)
            # upper slack: the hab's LOD2 solo slab runs its own seed
            # stream and can outgrow the ring's skyline by a few %
            check(0.75 <= r <= 1.05,
                  f"{FORM_NAMES[f]} lod2 keeps axis-{ax} massing "
                  f"(ratio {r:.3f})")
    check(len(set(fsums)) == 4, f"four forms all differ ({fsums})")
    sm[kid_form] = 0
    sm[kid_lod] = 0
    st.update_tag()

    # LOD x Detail orthogonality: Detail still tessellates the shell
    sm[kid_lod] = 2
    sm[ident(con, "FI_Building", "Detail")] = 0
    st.update_tag()
    s_d0 = coord_sum(eval_mesh(st))
    sm[ident(con, "FI_Building", "Detail")] = 2
    st.update_tag()
    me_d2 = eval_mesh(st)
    s_d2 = coord_sum(me_d2)
    t_d2 = tri_count(me_d2)
    check(abs(s_d2 - s_d0) > 0.5,
          f"Detail is live at LOD2 ({s_d0:.0f} -> {s_d2:.0f})")
    check(t_d2 < LOD_CEILING[2] * 4,
          f"Detail-2 shell stays sane ({t_d2} < {LOD_CEILING[2] * 4})")
    sm[ident(con, "FI_Building", "Detail")] = 0
    sm[kid_lod] = 0
    st.update_tag()

    # ---- factions: all four swap the (station) hull set ---------------
    for fi, key in ((0, "NAV"), (1, "OXR"), (2, "NYX"), (3, "FPT")):
        sm[ident(con, "FI_Building", "Faction")] = fi
        st.update_tag()
        mset = {m.name.split(".")[0] for m in eval_mesh(st).materials if m}
        check(f"FI_Station_{key}_Hull" in mset,
              f"faction {fi} swaps in the {key} hull set")
    sm[ident(con, "FI_Building", "Faction")] = 0
    st.update_tag()

    me_t = eval_mesh(st)

    def mat_on_faces(me2, name):
        return any(me2.materials[p.material_index] and
                   me2.materials[p.material_index].name.split(".")[0]
                   == name for p in me2.polygons)

    check(mat_on_faces(me_t, "FI_Building_Asphalt"),
          "plinth asphalt on actual faces")
    check(mat_on_faces(me_t, "FI_Building_Hazard"),
          "hazard stripes on actual faces")
    check(mat_on_faces(me_t, "FI_Station_Beacon"),
          "beacons on actual faces")
    sm[kid_form] = 1
    st.update_tag()
    check(mat_on_faces(eval_mesh(st), "FI_Building_StackRing"),
          "stack collars on actual faces (works)")
    sm[kid_form] = 3
    st.update_tag()
    check(mat_on_faces(eval_mesh(st), "FI_Station_Pad"),
          "landing pads on actual faces (spaceport)")
    sm[kid_form] = 0
    st.update_tag()

    # ---- knob sweep: every knob must reshape its live form -------------
    SWEEP = {
        0: (
            ("Seed", (("Seed", 9),)),
            ("Class", (("Class", 1),)),
            ("Detail", (("Detail", 1),)),
            ("Scale", (("Scale", 1.5),)),
            ("Height Mult", (("Height Mult", 1.5),)),
            ("Footprint Mult", (("Footprint Mult", 1.5),)),
            ("Footprint Aspect", (("Footprint Aspect", 0.6),)),
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
            ("Base Flare", (("Base Flare", 1.0),)),
            ("Ledges", (("Ledges", 0),)),
            ("Ledge Depth", (("Ledge Depth", 1.0),)),
            ("Top Plateaus", (("Top Plateaus", 0),)),
            ("Plateau Height", (("Plateau Height", 1.0),)),
            ("Towers Up", (("Towers Up", 0),)),
            ("Tower Height", (("Tower Height", 2.0),)),
            ("Tower Rake", (("Tower Rake", 1.0),)),
            ("Entrances", (("Entrances", 0),)),
            ("Entrance Size", (("Entrances", 2),
                               ("Entrance Size", 1.5))),
            ("Helipad", (("Helipad", True),)),
            ("Panel Density", (("Panel Density", 1),)),
            ("Patchwork", (("Patchwork", 0.02),)),
            ("Trenches", (("Trenches", 2),)),
            ("Trench Depth", (("Trenches", 2), ("Trench Depth", 1.0))),
            # door band must span a face-centre row at Levels 12
            # (0.091 spacing) — size 1.5 makes the band 0.15 tall
            ("Hangars", (("Hangars", 1), ("Hangar Size", 1.5))),
            ("Hangar Size", (("Hangars", 2), ("Hangar Size", 1.5))),
            ("Vents", (("Vents", 0),)),
            ("Radomes", (("Radomes", 0),)),
            ("Antennas", (("Antennas", 0),)),
            ("Decals", (("Decals", 0),)),
            ("Beacons", (("Beacons", 0),)),
        ),
        1: (
            ("Stacks", (("Stacks", 0),)),
            ("Stack Height", (("Stacks", 3), ("Stack Height", 1.8))),
            ("Pipe Runs", (("Pipe Runs", 0),)),
            ("Tank Clusters", (("Tank Clusters", 0),)),
            ("Tanks Per Cluster", (("Tank Clusters", 2),
                                   ("Tanks Per Cluster", 7))),
            ("Tank Scale", (("Tank Clusters", 2), ("Tank Scale", 1.7))),
        ),
        2: (
            ("Courtyard", (("Courtyard", False),)),
            ("Courtyard Size", (("Courtyard Size", 0.65),)),
        ),
        3: (
            ("Pads", (("Pads", 0),)),
            ("Pad Size", (("Pads", 3), ("Pad Size", 1.5))),
            ("Terminal Span", (("Terminal Span", 2.8),)),
            ("Control Tower", (("Control Tower", False),)),
        ),
    }
    moved = total = 0
    for form, knobs in SWEEP.items():
        sm[kid_form] = form
        st.update_tag()
        base_sum = coord_sum(eval_mesh(st))
        for label, pairs in knobs:
            total += 1
            saved = []
            for name, val in pairs:
                keyid = ident(con, "FI_Building", name)
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
    sm[kid_form] = 0
    st.update_tag()

    # completeness: every contract INPUT socket is either swept or on
    # the documented exempt list — a new knob cannot dodge the sweep
    swept = {label for knobs in SWEEP.values() for label, _ in knobs}
    exempt = {
        "Form",           # covered by the four-forms-differ check
        "Faction",        # material-only, covered by the faction check
        "LOD",            # covered by the Form x LOD budget matrix
        "Window Glow",    # attr-only  (fi_glowpanel check below)
        "Hue Jitter",     # attr-only  (fi_hue check below)
        "Light Rows",     # attr-only  (fi_light check below)
        "Deck Markings",  # attr-only  (fi_deckmark check below)
        # at building scale the relief floor keeps accents shader-only
        # (paint, not 8 cm relief) — verified via fi_accent sums below
        "Accent Fields",
        "Accent Bands",
        "Meridian Stripe",
    }
    allin = {it["name"] for it in con["FI_Building"]
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
    # the shell must still carry paint attrs or LOD2 bakes go flat
    for lodv in (1, 2):
        sm[kid_lod] = lodv
        st.update_tag()
        a = eval_mesh(st).attributes.get("fi_tint")
        n = len({round(d.value, 3) for d in a.data}) if a else 0
        check(n >= 4, f"fi_tint alive at LOD{lodv} ({n} values)")
    sm[kid_lod] = 0
    st.update_tag()

    kid_af = ident(con, "FI_Building", "Accent Fields")
    kid_ab = ident(con, "FI_Building", "Accent Bands")
    kid_ms = ident(con, "FI_Building", "Meridian Stripe")

    def attr_sum(me2, name):
        a = me2.attributes.get(name)
        if a is None:
            return -1.0
        return sum(float(d.value) for d in a.data)

    sm[kid_af] = 0
    sm[kid_ab] = 0
    st.update_tag()
    a00 = attr_sum(eval_mesh(st), "fi_accent")
    sm[kid_ms] = True
    st.update_tag()
    a_ms = attr_sum(eval_mesh(st), "fi_accent")
    check(a_ms > a00, f"Meridian Stripe paints fi_accent "
                      f"({a00:.0f} -> {a_ms:.0f})")
    sm[kid_ms] = False
    sm[kid_af] = 3
    st.update_tag()
    a30 = attr_sum(eval_mesh(st), "fi_accent")
    check(a30 > a00, f"Accent Fields paint fi_accent "
                     f"({a00:.0f} -> {a30:.0f})")
    sm[kid_ab] = 2
    st.update_tag()
    a32 = attr_sum(eval_mesh(st), "fi_accent")
    check(a32 > a30, f"Accent Bands add fi_accent rings "
                     f"({a30:.0f} -> {a32:.0f})")
    sm[kid_af] = 2
    sm[kid_ab] = 1
    st.update_tag()

    l6 = attr_sum(me_pw, "fi_light")
    check(l6 > 0.5, f"fi_light band mask populated (sum={l6:.1f})")
    sm[ident(con, "FI_Building", "Light Rows")] = 0
    st.update_tag()
    l0 = attr_sum(eval_mesh(st), "fi_light")
    check(l0 < max(l6 * 0.05, 0.01),
          f"Light Rows gates the emission mask ({l6:.1f} -> {l0:.1f})")
    sm[ident(con, "FI_Building", "Light Rows")] = 2
    sm[ident(con, "FI_Building", "Window Glow")] = 0.0
    st.update_tag()
    g0 = attr_sum(eval_mesh(st), "fi_glowpanel")
    sm[ident(con, "FI_Building", "Window Glow")] = 1.0
    st.update_tag()
    g1 = attr_sum(eval_mesh(st), "fi_glowpanel")
    check(g1 > g0 + 3,
          f"Window Glow scales lit panels ({g0:.0f} -> {g1:.0f})")
    check(g1 > 30, f"night-city coverage floor at full glow ({g1:.0f})")
    sm[ident(con, "FI_Building", "Window Glow")] = 0.6
    sm[ident(con, "FI_Building", "Hue Jitter")] = 0.0
    st.update_tag()
    h0 = attr_sum(eval_mesh(st), "fi_hue")
    sm[ident(con, "FI_Building", "Hue Jitter")] = 1.0
    st.update_tag()
    h1 = attr_sum(eval_mesh(st), "fi_hue")
    check(h1 > h0 + 1.0,
          f"Hue Jitter scales the hue attr ({h0:.1f} -> {h1:.1f})")
    sm[ident(con, "FI_Building", "Hue Jitter")] = 0.35
    sm[ident(con, "FI_Building", "Deck Markings")] = False
    st.update_tag()
    dm0 = attr_sum(eval_mesh(st), "fi_deckmark")
    sm[ident(con, "FI_Building", "Deck Markings")] = True
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

    # ---- island overlap at greeble-max, per form, LOD0 and LOD2 --------
    GREEBLE_MAX = {"Helipad": True, "Stacks": 6, "Pipe Runs": 4,
                   "Tank Clusters": 4, "Tanks Per Cluster": 7,
                   "Pads": 4, "Vents": 4, "Radomes": 2, "Antennas": 3,
                   "Decals": 2, "Beacons": 4, "Towers Up": 3}
    for form in range(4):
        for lodv in (0, 2):
            saved = []
            for k, v in dict(GREEBLE_MAX, Form=form, LOD=lodv).items():
                kid = ident(con, "FI_Building", k)
                saved.append((kid, sm.get(kid, None)))
                sm[kid] = v
            st.update_tag()
            nsh, nbad = island_overlap(eval_mesh(st))
            check(nbad == 0,
                  f"islands {FORM_NAMES[form]} lod{lodv}: all {nsh} "
                  f"shells attach ({nbad} float)")
            for kid, old_v in saved:
                if old_v is None:
                    del sm[kid]
                else:
                    sm[kid] = old_v
            st.update_tag()

    # ---- watertight: daylight edges == 0 -------------------------------
    wt_configs = (
        ("tower default", {}),
        ("tower stress", {"Form": 0, "Panel Density": 4, "Detail": 2,
                          "Towers Up": 3, "Tower Rake": 1.0,
                          "Base Flare": 1.0, "Trenches": 3,
                          "Hangars": 2, "Seed": 7}),
        ("works stress", {"Form": 1, "Stacks": 6, "Tank Clusters": 4,
                          "Pipe Runs": 4, "Panel Density": 3,
                          "Trenches": 2, "Seed": 5}),
        ("hab stress", {"Form": 2, "Courtyard Size": 0.7, "Ledges": 3,
                        "Panel Density": 4, "Hangars": 2, "Seed": 3}),
        ("hab tight court", {"Form": 2, "Courtyard Size": 0.3,
                             "Seed": 11}),
        ("spaceport stress", {"Form": 3, "Pads": 4, "Terminal Span": 3.0,
                              "Panel Density": 3, "Seed": 9}),
        ("tower lod1", {"Form": 0, "LOD": 1, "Seed": 7}),
        ("works lod2", {"Form": 1, "LOD": 2, "Seed": 5}),
        ("hab lod2", {"Form": 2, "LOD": 2, "Seed": 3}),
        ("spaceport lod1", {"Form": 3, "LOD": 1, "Seed": 9}),
    )
    for wname, wp in wt_configs:
        saved = []
        for k, v in wp.items():
            kid = ident(con, "FI_Building", k)
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

    # ---- scale envelope -------------------------------------------------
    me_s = eval_mesh(st)
    ext_s = [max(v.co[i] for v in me_s.vertices) -
             min(v.co[i] for v in me_s.vertices) for i in range(3)]
    check(80 <= ext_s[2] <= 260,
          f"tower default height in the city envelope ({ext_s[2]:.0f} m)")
    check(ext_s[2] > 1.5 * max(ext_s[0], ext_s[1]),
          f"tower is taller than wide (H={ext_s[2]:.0f})")
    sm[kid_form] = 3
    st.update_tag()
    me_p = eval_mesh(st)
    ext_p = [max(v.co[i] for v in me_p.vertices) -
             min(v.co[i] for v in me_p.vertices) for i in range(3)]
    check(max(ext_p[0], ext_p[1]) > 1.5 * ext_p[2],
          f"spaceport is wider than tall (W={max(ext_p[0], ext_p[1]):.0f}"
          f" H={ext_p[2]:.0f})")
    sm[kid_form] = 0
    kid_s = ident(con, "FI_Building", "Scale")
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

    # ---- renders: one per form + a tower LOD strip ---------------------
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

    def frame_and_render(fname):
        me_r = eval_mesh(st)
        zc = 0.5 * max(v.co.z for v in me_r.vertices)
        ctr = Vector((0.0, 0.0, zc))
        rad = max(max(max(abs(v.co.x), abs(v.co.y)) for v in
                      me_r.vertices), zc)
        d = Vector((0.7, -1.0, 0.45)).normalized()
        cam.location = ctr + d * rad * 3.4
        cam.rotation_euler = (ctr - cam.location).to_track_quat(
            "-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(OUTDIR, f"{fname}.png")
        bpy.ops.render.render(write_still=True)
        check(os.path.exists(scene.render.filepath), f"render {fname}")

    for f in range(4):
        sm[kid_form] = f
        st.update_tag()
        frame_and_render(f"building_{FORM_NAMES[f]}")
    sm[kid_form] = 0
    for lodv in range(3):
        sm[kid_lod] = lodv
        st.update_tag()
        frame_and_render(f"tower_lod{lodv}")
    sm[kid_lod] = 0

    print(f"\nbuilding_selftest: "
          f"{'ALL PASS' if not FAILS else 'FAILURES:'}")
    for f in FAILS:
        print("  -", f)
    sys.exit(1 if FAILS else 0)


main()
