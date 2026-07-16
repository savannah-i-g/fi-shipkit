#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# make_station_playground.py -- regenerate station_playground.blend: the
# STATION family (FI_Station) across forms, factions and seeds.
#   blender -b --python make_station_playground.py

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
    con = json.load(open(os.path.join(HERE, "station_contract.json")))
    with bpy.data.libraries.load(os.path.join(HERE, "FI_StationKit.blend"),
                                 link=True) as (s, d):
        d.node_groups = ["FI_Station"]
    st_ng = bpy.data.node_groups["FI_Station"]
    exp = bpy.data.collections.new("FI_EXPORT")
    bpy.context.scene.collection.children.link(exp)

    # 2 km spacing on Y — stations run up to ~1.5 km
    stations = [
        ("station_spire_nav", (0, 0, 0),        # canonical citadel (EXPORT)
         {"Seed": 1, "Form": 0, "Faction": 0}, True),
        ("station_spire_nyx", (0, 2000, 0),     # tall dark spire, lit hard
         {"Seed": 6, "Form": 0, "Faction": 2, "Height Mult": 1.5,
          "Towers Up": 3, "Towers Down": 2, "Tower Height": 1.6,
          "Light Rows": 6, "Window Glow": 0.8, "Beacons": 4,
          "Spires": 3, "Arms": 3, "Ring": 1}, False),
        ("station_spire_oxr", (0, 4000, 0),     # small oxide comm relay
         {"Seed": 12, "Form": 0, "Faction": 1, "Scale": 0.4,
          "Arms": 2, "Arm Levels": 1, "Spires": 3, "Spire Height": 2.0,
          "Radomes": 2, "Antennas": 3, "Towers Up": 1,
          "Towers Down": 0, "Top Plateaus": 2}, False),
        ("station_gantry_fpt", (0, 6000, 0),    # flagship freeport yard
         {"Seed": 5, "Form": 1, "Faction": 3, "Maw": 1.0,             # (EXPORT)
          "Maw Aspect": 1.3, "Gantries": 5, "Cranes": 4,
          "Tank Clusters": 4, "Tanks Per Cluster": 6,
          "Spine Stretch": 2.2, "Window Glow": 0.7,
          "Accent Bands": 2, "Beacons": 4}, True),
        ("station_gantry_nav", (0, 8000, 0),    # navy drydock, by the book
         {"Seed": 9, "Form": 1, "Faction": 0, "Maw": 0.8,
          "Gantries": 3, "Cranes": 2, "Tank Clusters": 1,
          "Decals": 2, "Deck Markings": True,
          "Accent Fields": 3}, False),
        ("station_saucer_nav", (0, -2000, 0),   # canonical trade hub (EXPORT)
         {"Seed": 3, "Form": 2, "Faction": 0, "Pads": 6,
          "Silhouette Style": 1, "Corner Cut": 0.85}, True),
        ("station_saucer_oxr", (0, -4000, 0),   # mining hub, grime-forward
         {"Seed": 7, "Form": 2, "Faction": 1, "Pads": 4,
          "Silhouette Style": 4, "Tank Scale": 1.4,
          "Pad Size": 1.3, "Blisters": 1.0}, False),
        ("station_saucer_fpt", (0, -6000, 0),   # freeport bazaar, neon
         {"Seed": 15, "Form": 2, "Faction": 3, "Pads": 9,
          "Window Glow": 1.0, "Hue Jitter": 1.0, "Patchwork": 1.0,
          "Accent Fields": 3, "Pad Tier": 0.35,
          "Silhouette Style": 2}, False),
        ("station_monolith_nyx", (0, -8000, 0),  # bastion, sparse windows
         {"Seed": 9, "Form": 3, "Faction": 2, "Turrets": 6,           # (EXPORT)
          "Trenches": 3, "Trench Depth": 0.8, "Window Glow": 0.15,
          "Spires": 2, "Beacons": 4, "Corner Cut": 0.3}, True),
        ("station_monolith_oxr", (0, -10000, 0),  # refinery bastion
         {"Seed": 21, "Form": 3, "Faction": 1, "Tank Clusters": 2,
          "Tanks Per Cluster": 7, "Tank Scale": 1.6, "Turrets": 2,
          "Trenches": 2, "Silhouette Style": 4, "Vents": 4}, False),
    ]
    for name, at, params, export in stations:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        (exp if export else bpy.context.scene.collection).objects.link(ob)
        ob.location = at
        mod = ob.modifiers.new("FI_Station", "NODES")
        mod.node_group = st_ng
        for k, v in params.items():
            mod[ident(con, "FI_Station", k)] = v
        print(f"  {name:22s} at {at}")
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0, 0.5)
    bpy.context.scene.collection.objects.link(sun)
    out = os.path.join(HERE, "station_playground.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"make_station_playground: OK -> {out}")


main()
