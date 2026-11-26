#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GND 缝合孔：把 F / In2 / B 三层的 GND 铺铜彼此连通。

DRC 里那 24 条「未连接 GND」坐标全是 (0.75, 0.75) —— 那是 zone 的起始角，
意思是「F.Cu 的 GND 铜和 B.Cu 的 GND 铜不是同一块」，不是真的有 24 个孤岛。
In1 被 VCC 占用，F/B/In2 的 GND 只能靠通孔焊盘互通，数量不够。

做法：15mm 网格撒 GND 贯穿孔，位置必须三层都空或本网（栅格已含板边/开槽避让）。
"""
import json
import os

import numpy as np

import board_geom as BG
import router
from autoroute import build_grid

router.GRID = 0.2
G = router.GRID
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
OUT = os.path.join(HERE, "_stitch.json")

STEP_MM = 15.0
MARGIN = 1.2

g = BG.load(PCB)
pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
NET_ID = {n: i + 1 for i, n in enumerate(sorted(pads_by_net))}
LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}
NID = NET_ID["GND"]

gr = build_grid(g)
for t in g["tracks"]:
    if t["net"] in NET_ID:
        gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]),
                  NET_ID[t["net"]], LMAP[t["layer"]])
for v in g["vias"]:
    if v["net"] in NET_ID:
        gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])

o = g["outline"]
x0, y0, x1, y1 = o[0] + MARGIN, o[1] + MARGIN, o[2] - MARGIN, o[3] - MARGIN

items = []
n_ok = n_bad = 0
y = y0 + STEP_MM / 2
while y < y1:
    x = x0 + STEP_MM / 2
    while x < x1:
        i, j = gr.ix(x), gr.iy(y)
        ok = True
        if gr.blocked[0, j, i] or gr.blocked[2, j, i] or gr.blocked[3, j, i]:
            ok = False
        if ok:
            for L in (0, 2, 3):
                v = gr.occ[L, j, i]
                if v != 0 and v != NID:
                    ok = False
                    break
        if ok and gr.via_block[0, j, i]:
            ok = False
        if ok:
            items.append(("via", "GND", round(i * G, 3), round(j * G, 3)))
            for L in (0, 2, 3):
                gr.mark_via(i, j, NID)
            n_ok += 1
        else:
            n_bad += 1
        x += STEP_MM
    y += STEP_MM

print(f"GND 缝合孔 {n_ok} 个，跳过 {n_bad} 个候选点", flush=True)
if items:
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f)
    os.replace(tmp, OUT)
    print("写出", OUT)
