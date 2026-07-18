#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# make_building_playground.py -- regenerate building_playground.blend:
# the BUILDING family (FI_Building) across forms, factions and seeds,
# plus a generated CITY_BLOCK grid for massing-variety eyeballing.
#   blender -b --python make_building_playground.py

import bpy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def ident(con, group, name):
    for it in con[group]:
        if it["name"] == name and it["in_out"] == "INPUT":
            return it["identifier"]
    raise KeyError(f"{group}:{name}")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    con = json.load(open(os.path.join(HERE, "building_contract.json")))
    with bpy.data.libraries.load(os.path.join(HERE, "FI_BuildingKit.blend"),
                                 link=True) as (s, d):
        d.node_groups = ["FI_Building"]
    bld_ng = bpy.data.node_groups["FI_Building"]
    exp = bpy.data.collections.new("FI_EXPORT")
    bpy.context.scene.collection.children.link(exp)

    def spawn(name, at, params, coll):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        coll.objects.link(ob)
        ob.location = at
        mod = ob.modifiers.new("FI_Building", "NODES")
        mod.node_group = bld_ng
        for k, v in params.items():
            mod[ident(con, "FI_Building", k)] = v
        return ob

    buildings = [
        ("bld_tower_nav", (0, 0, 0),          # canonical HQ (EXPORT)
         {"Seed": 1, "Form": 0, "Faction": 0, "Helipad": True}, True),
        ("bld_tower_nyx", (0, 400, 0),        # dark tower, lit hard
         {"Seed": 6, "Form": 0, "Faction": 2, "Height Mult": 1.5,
          "Window Glow": 0.9, "Light Rows": 6, "Towers Up": 2,
          "Beacons": 4}, False),
        ("bld_tower_fpt", (0, 800, 0),        # neon bazaar tower
         {"Seed": 11, "Form": 0, "Faction": 3, "Hue Jitter": 1.0,
          "Patchwork": 1.0, "Window Glow": 1.0, "Accent Fields": 3,
          "Silhouette Style": 2}, False),
        ("bld_works_oxr", (0, 1200, 0),       # refinery, maxed (EXPORT)
         {"Seed": 5, "Form": 1, "Faction": 1, "Stacks": 5,
          "Tank Clusters": 4, "Tanks Per Cluster": 6, "Pipe Runs": 4,
          "Vents": 4, "Trenches": 2}, True),
        ("bld_works_nav", (0, 1600, 0),       # tidy navy depot
         {"Seed": 9, "Form": 1, "Faction": 0, "Stacks": 2,
          "Deck Markings": True, "Decals": 2, "Accent Fields": 3},
         False),
        ("bld_works_nyx", (0, 2000, 0),       # dark plant, low glow
         {"Seed": 14, "Form": 1, "Faction": 2, "Window Glow": 0.15,
          "Stacks": 4, "Stack Height": 1.6, "Beacons": 4}, False),
        ("bld_hab_nav", (0, -400, 0),         # canonical hab (EXPORT)
         {"Seed": 3, "Form": 2, "Faction": 0}, True),
        ("bld_hab_oxr", (0, -800, 0),         # worker slab, grime
         {"Seed": 7, "Form": 2, "Faction": 1, "Courtyard": False,
          "Ledges": 3, "Hangars": 2}, False),
        ("bld_hab_fpt", (0, -1200, 0),        # stacked bazaar, full glow
         {"Seed": 15, "Form": 2, "Faction": 3, "Window Glow": 1.0,
          "Hue Jitter": 1.0, "Courtyard Size": 0.6,
          "Accent Bands": 2}, False),
        ("bld_spaceport_nav", (0, -1700, 0),  # main port (EXPORT)
         {"Seed": 2, "Form": 3, "Faction": 0, "Pads": 4,
          "Deck Markings": True, "Decals": 2}, True),
        ("bld_spaceport_nyx", (0, -2200, 0),  # military pad
         {"Seed": 8, "Form": 3, "Faction": 2, "Pads": 2,
          "Window Glow": 0.2, "Beacons": 4, "Terminal Span": 1.4},
         False),
    ]
    for name, at, params, export in buildings:
        spawn(name, at,
              params, exp if export else bpy.context.scene.collection)
        print(f"  {name:22s} at {at}")

    # CITY BLOCK: a generated 4x4 district — perimeter habs, taller
    # towers toward the centre, one faction (NAV reads as one district),
    # per-cell seed + height/footprint jitter. All export=False.
    city = bpy.data.collections.new("CITY_BLOCK")
    bpy.context.scene.collection.children.link(city)
    spacing = 160.0
    for cy in range(4):
        for cx in range(4):
            i = cy * 4 + cx
            center = 1.0 - (abs(cx - 1.5) + abs(cy - 1.5)) / 3.0
            is_tower = 0.5 < center or (cx + cy) % 2 == 0
            params = {"Seed": 1 + i, "Faction": 0,
                      "Form": 0 if is_tower else 2,
                      "Scale": 0.8,
                      "Height Mult": 0.7 + 0.6 * center +
                                     0.07 * ((i * 7) % 3),
                      "Footprint Mult": 0.85 + 0.05 * ((i * 5) % 3),
                      "LOD": 0}
            spawn(f"city_{cx}{cy}",
                  (5000.0 + cx * spacing, cy * spacing, 0.0),
                  params, city)
    print("  city block: 4x4 grid at x=+5000")

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0, 0.5)
    bpy.context.scene.collection.objects.link(sun)
    out = os.path.join(HERE, "building_playground.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"make_building_playground: OK -> {out}")


main()
