#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# make_fleet_playground.py -- regenerate fleet_playground.blend: the FLEET
# family (FI_FleetShip) across classes, palettes and seeds.
#   blender -b --python make_fleet_playground.py

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
    con = json.load(open(os.path.join(HERE, "fleet_contract.json")))
    with bpy.data.libraries.load(os.path.join(HERE, "FI_FleetKit.blend"),
                                 link=True) as (s, d):
        d.node_groups = ["FI_FleetShip"]
    ship_ng = bpy.data.node_groups["FI_FleetShip"]
    exp = bpy.data.collections.new("FI_EXPORT")
    bpy.context.scene.collection.children.link(exp)

    ships = [
        ("fleet_frigate_nav", (0, 0, 0),      # canonical frigate (EXPORT)
         {"Seed": 1, "Class": 0, "Faction": 0}, True),
        ("fleet_frigate_oxr", (0, 70, 0),     # oxide patrol: deep chine
         {"Seed": 3, "Class": 0, "Faction": 1, "Chine": 0.9,
          "Plateaus": 1, "Nozzles": 1, "Vents": 3,
          "Nose Style": 5, "Chine 2": 0.8, "Keel Crown": 0.5,
          "Nacelles": 1}, False),
        ("fleet_frigate_nyx", (0, 140, 0),    # dark raider (+RCS option)
         {"Seed": 4, "Class": 0, "Faction": 2, "Bow Wedge": 0.38,
          "Keel": 0.3, "Nozzles": 3, "Thrusters": True,
          "Light Rows": 6, "Nose Style": 1, "Nose Taper": 1.1,
          "Mass Bias": 0.8, "Waist": 0.65, "Waist Position": 0.40,
          "Deck Crown": 0.3, "Chine": 0.85, "Chine 2": 0.6,
          "Stern Style": 1, "Stern Taper": 1.6,
          "Stern Tip": 0.5, "Prow Pods": 2, "Dorsal Fins": 1}, False),
        ("fleet_cruiser_nav", (0, -160, 0),   # canonical cruiser (EXPORT)
         {"Seed": 5, "Class": 1, "Faction": 0, "Nozzles": 3,
          "Sponsons": 2, "Radomes": 2, "Antennas": 3}, True),
        ("fleet_cruiser_oxr", (0, -360, 0),   # heavy hauler: square slab
         {"Seed": 7, "Class": 1, "Faction": 1, "Chine": 0.3,
          "Stern Block": 0.30, "Blisters": 1.0, "Vents": 4,
          "Nozzles": 2, "Nose Style": 5, "Stern Style": 3,
          "Nacelles": 1, "Towers": 2, "Nacelle Position": 0.25,
          "Hangars": 2, "Deck Trench": 0.7}, False),
        ("fleet_cruiser_nyx", (0, -560, 0),   # dark flagship
         {"Seed": 9, "Class": 1, "Faction": 2, "Plateau Height": 0.8,
          "Accent Fields": 3, "Light Rows": 6, "Decals": 2,
          "Nozzles": 3, "Nose Style": 3, "Nose Tip": 0.6,
          "Saddle": 0.6, "Stern Style": 2, "Stern Rake": 0.15,
          "Deck Crown": 0.4, "Prow Pods": 3, "Dorsal Fins": 2,
          "Ventral Fins": 1, "Bow Mouth": 0.7, "Overbite": 0.6}, False),
        ("fleet_shipyard_nav", (0, 260, 0),   # twin-hull shipyard
         {"Seed": 11, "Class": 1, "Faction": 0, "Hull Form": 1,
          "Hull Spacing": 0.95, "Bridge Blocks": 3, "Hangars": 2,
          "Towers": 2, "Nose Style": 5, "Stern Style": 3,
          "Light Rows": 6}, False),
        ("fleet_carrier_asym", (0, -820, 0),   # HW1-style side module
         {"Seed": 13, "Class": 1, "Faction": 1, "Hull Form": 2,
          "Module Scale": 0.5, "Nose Style": 5, "Hangars": 1,
          "Towers": 1, "Blisters": 0.8, "Accent Bands": 2}, False),
    ]
    for name, at, params, export in ships:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        (exp if export else bpy.context.scene.collection).objects.link(ob)
        ob.location = at
        mod = ob.modifiers.new("FI_FleetShip", "NODES")
        mod.node_group = ship_ng
        for k, v in params.items():
            mod[ident(con, "FI_FleetShip", k)] = v
        print(f"  {name:20s} at {at}")
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0, 0.5)
    bpy.context.scene.collection.objects.link(sun)
    out = os.path.join(HERE, "fleet_playground.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"make_fleet_playground: OK -> {out}")


main()
