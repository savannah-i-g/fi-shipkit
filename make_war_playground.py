#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# make_war_playground.py -- regenerate war_playground.blend: the military
# fleet (FI_WarShip) across classes, factions and seeds.
#   blender -b --python make_war_playground.py

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
    con = json.load(open(os.path.join(HERE, "war_contract.json")))
    with bpy.data.libraries.load(os.path.join(HERE, "FI_WarKit.blend"),
                                 link=True) as (s, d):
        d.node_groups = ["FI_WarShip"]
    with bpy.data.libraries.load(os.path.join(HERE, "FI_ShipKit.blend"),
                                 link=True) as (s, d):
        d.collections = ["FI_Greebles"]
    ship_ng = bpy.data.node_groups["FI_WarShip"]
    greebles = bpy.data.collections["FI_Greebles"]
    exp = bpy.data.collections.new("FI_EXPORT")
    bpy.context.scene.collection.children.link(exp)

    ships = [
        ("war_corvette_mcr", (0, 0, 0),      # Elite-viper: diamond raked
         {"Seed": 1, "Class": 0, "Faction": 0, "Drive Type": 0,
          "Section": 1, "Section Exponent": 1.6, "Side Profile": 1,
          "Visor Size": 0.8, "Step Count": 3, "Light Lines": 4}, True),
        ("war_corvette_unn", (0, 60, 0),     # smooth courier
         {"Seed": 2, "Class": 0, "Faction": 1, "Drive Type": 1,
          "Section": 2, "Blend": 0.45, "Bend": 0.3, "Visor Size": 1.0,
          "Panel Density": 2, "Silhouette": 1}, False),
        ("war_corvette_bel", (0, 120, 0),    # kitbash gunship
         {"Seed": 3, "Class": 0, "Faction": 2, "Drive Type": 2,
          "Detail Extrusions": 6, "Trench": 0.7, "Armor Plates": 0.9,
          "Sub Panels": 0.5, "Asymmetry": 1.0, "Silhouette": 2,
          "Greeble Density": 0.5}, False),
        ("war_destroyer_mcr", (0, -120, 0),  # inv-trap hammer
         {"Seed": 5, "Class": 1, "Faction": 0, "Turrets": 6,
          "Silhouette": 2, "Section": 3, "Hump Position": 0.30,
          "Hump Length": 0.25, "Hump Height": 0.45}, True),
        ("war_destroyer_unn", (0, -260, 0),  # raked wedge flagship
         {"Seed": 6, "Class": 1, "Faction": 1, "Turrets": 6,
          "Drive Type": 1, "Silhouette": 0, "Side Profile": 1,
          "Dorsal Taper": 0.5, "Trench": 0.5, "Light Lines": 8}, False),
        ("war_destroyer_bel", (0, -400, 0),  # bent dagger raider
         {"Seed": 7, "Class": 1, "Faction": 2, "Silhouette": 1,
          "Bend": -0.4, "Blend": 0.3, "Detail Extrusions": 4,
          "Armor Plates": 1.0}, False),
    ]
    for name, at, params, export in ships:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        (exp if export else bpy.context.scene.collection).objects.link(ob)
        ob.location = at
        mod = ob.modifiers.new("FI_WarShip", "NODES")
        mod.node_group = ship_ng
        mod[ident(con, "FI_WarShip", "Greebles")] = greebles
        for k, v in params.items():
            mod[ident(con, "FI_WarShip", k)] = v
        print(f"  {name:20s} at {at}")
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0, 0.5)
    bpy.context.scene.collection.objects.link(sun)
    out = os.path.join(HERE, "war_playground.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print(f"make_war_playground: OK -> {out}")


main()
