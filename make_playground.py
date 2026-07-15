#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# make_playground.py -- regenerate shipgen_playground.blend: three FI_ShipGen
# ships (corvette seed 0, corvette seed 7, hauler preset) linked to the kit.
# Open it, select a ship, and play with the modifier sliders.
#
#   blender -b --python make_playground.py

import bpy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "FI_ShipKit.blend")
OUT = os.path.join(HERE, "shipgen_playground.blend")


def ident(con, group, name):
    for it in con[group]:
        if it["name"] == name and it["in_out"] == "INPUT":
            return it["identifier"]
    raise KeyError(f"{group}:{name}")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with open(os.path.join(HERE, "kit_contract.json")) as f:
        con = json.load(f)
    with bpy.data.libraries.load(KIT, link=True) as (src, dst):
        dst.node_groups = [n for n in src.node_groups if n.startswith("FI_")]
        dst.collections = ["FI_Greebles"]
    greebles = bpy.data.collections["FI_Greebles"]

    exp = bpy.data.collections.new("FI_EXPORT")
    bpy.context.scene.collection.children.link(exp)

    def slots(*types):
        return {f"Slot {i + 1} Type": t for i, t in enumerate(types)} | \
               {"Auto Slots": False}

    # (name, group, location, params, export) — FRAME-ONLY fleet
    ships = [
        ("frame_explorer", "FI_FrameShip", (0, 120, 0),
         {"Seed": 4, "Length": 90.0, "Depth": 14.0, "Wing Pairs": 3,
          "Ring": True, "Docked Craft": True, "Dish Count": 2,
          "Gold Fraction": 0.35, "Wing Fold (deg)": 25.0,
          **slots(1, 4, 1, 2, 3, 6)}, True),
        ("frame_tug", "FI_FrameShip", (0, 220, 0),
         {"Seed": 8, "Length": 70.0, "Depth": 12.0, "Wing Pairs": 1,
          "Gold Fraction": 0.5, "Engine Count": 3, "Bow Style": 2,
          "Wing Fold (deg)": 0.0, **slots(2, 3, 3, 6, 0, 0)}, False),
        ("frame_carrier", "FI_FrameShip", (0, 560, 0),
         {"Seed": 15, "Length": 120.0, "Depth": 16.0, "Wing Pairs": 2,
          "Bow Style": 3, "Engine Count": 4,
          **slots(1, 5, 5, 2, 3, 6)}, False),
        ("frame_hauler", "FI_FrameShip", (0, 330, 0),
         {"Seed": 12, "Length": 110.0, "Depth": 13.0, "Wing Pairs": 2,
          **slots(1, 4, 5, 5, 5, 2)}, True),
        ("frame_station", "FI_FrameShip", (0, 460, 0),
         {"Seed": 11, "Length": 100.0, "Depth": 16.0, "Wing Pairs": 5,
          "Engines": False, "Ring": True, "Ring Style": 2,
          "Ring Position": 0.55, "Radial Count": 4, "Dish Count": 3,
          "Wing Fold (deg)": 40.0, **slots(1, 4, 1, 4, 1, 4)}, True),
        ("frame_skiff", "FI_FrameShip", (60, 120, 0),
         {"Seed": 21, "Length": 16.0, "Depth": 4.5, "Wing Pairs": 1,
          "Bow Style": 1, "Dish Count": 0, "Engine Count": 1,
          "Engine Type": 1, **slots(1, 3, 0, 0, 0, 0)}, True),
        ("frame_shuttle", "FI_FrameShip", (60, 180, 0),
         {"Seed": 22, "Length": 26.0, "Depth": 6.0, "Wing Pairs": 1,
          "Bow Style": 1, "Dish Count": 1, "Engine Count": 2,
          **slots(1, 1, 3, 0, 0, 0)}, False),
    ]
    for name, group, at, params, export in ships:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        if export:
            exp.objects.link(ob)      # FI_EXPORT is in the view layer
        else:
            bpy.context.scene.collection.objects.link(ob)
        ob.location = at
        mod = ob.modifiers.new(group, "NODES")
        mod.node_group = bpy.data.node_groups[group]
        mod[ident(con, group, "Greebles")] = greebles
        for k, v in params.items():
            mod[ident(con, group, k)] = v
        print(f"  {name:18s} [{group}] at {at}")

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0, 0.5)
    bpy.context.scene.collection.objects.link(sun)
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
    # portable + leak-free: store texture/library paths relative to the
    # blend (absolute author paths break clones and leak the home dir)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
    print(f"make_playground: OK -> {OUT}")


main()
