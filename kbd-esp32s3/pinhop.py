#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给顽固 K 网的焊盘打「接到本网已存在 In2 铜皮」的盘中孔。

思路：这些网的 SW→IC 段已经走过 In2 了，R.2 焊盘正下方往往就压着本网的
In2 铜（occ == nid），只是缺一个孔把它接上去。孔打在焊盘内、In2 同一网的
格子上，天然合法，不需要 A*。
"""
import json
import os
import sys

import numpy as np

import board_geom as BG
import router
from autoroute import build_grid, pad_layers

router.GRID = 0.2
G = router.GRID
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
OUT = os.path.join(HERE, "_routes9.json")

NETS = ["K36", "K42", "K48", "K51", "K55", "K61", "K62", "K65", "K69"]

g = BG.load(PCB)
pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
NET_ID = {n: i + 1 for i, n in enumerate(sorted(pads_by_net))}
LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}

gr = build_grid(g)
for t in g["tracks"]:
    if t["net"] in NET_ID:
        gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]),
                  NET_ID[t["net"]], LMAP[t["layer"]])
for v in g["vias"]:
    if v["net"] in NET_ID:
        gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])


def k_chip(kn):
    """K 网 -> (165 编号, 引脚号)，从 PCB 焊盘直接查，不用公式。
    公式 (kn-1)//8+1 是错的：键盘按键是按物理位置分配到最近的一片 165，
    K36 接 U6.5 而不是 U5.4。这类映射只能有一个真相源 —— 板子本身。"""
    net = f"K{kn:02d}"
    for p in g["pads"]:
        if p["net"] == net and p["ref"].startswith("U"):
            return int(p["ref"][1:]), int(p["num"])
    return None, None



def on_net_in_pad(pad, nid):
    """焊盘内 In2 上归属本网的最近格子"""
    cx, cy = pad["x"], pad["y"]
    hw, hh = pad["w"] / 2.0, pad["h"] / 2.0
    i0, i1 = gr.ix(cx - hw + 0.05), gr.ix(cx + hw - 0.05)
    j0, j1 = gr.iy(cy - hh + 0.05), gr.iy(cy + hh - 0.05)
    best = None
    for j in range(max(0, j0), min(gr.ny - 1, j1) + 1):
        for i in range(max(0, i0), min(gr.nx - 1, i1) + 1):
            if gr.blocked[2, j, i] or gr.occ[2, j, i] != nid:
                continue
            d = (i * G - cx) ** 2 + (j * G - cy) ** 2
            if best is None or d < best[0]:
                best = (d, i, j)
    return None if best is None else (best[1] * G, best[2] * G, best[0] ** 0.5)


items = []
hits, miss = 0, []
for net in NETS:
    nid = NET_ID[net]
    kn = int(net[1:])
    u, pin = k_chip(kn)
    for label, rref, rnum in ((f"R{kn:02d}.2", f"R{kn:02d}", "2"),
                              (f"U{u}.{pin}", f"U{u}", str(pin))):
        cand = [p for p in pads_by_net[net]
                if p["ref"] == rref and p["num"] == rnum]
        if not cand:
            miss.append((net, label, "无此焊盘"))
            continue
        p0 = cand[0]
        spot = on_net_in_pad(p0, nid)
        if spot is None:
            miss.append((net, label, "焊盘内 In2 无本网铜"))
            continue
        x, y, d = spot
        items.append(("via", net, float(x), float(y)))
        hits += 1
        print(f"  [✓] {net} {label} 孔 ({x:.2f},{y:.2f}) 偏离中心 {d:.2f}mm", flush=True)

print(f"\n打孔 {hits} 个，未定位 {len(miss)} 处")
for m in miss:
    print("   ×", m)

if items:
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f)
    os.replace(tmp, OUT)
    print("写出", OUT, len(items), "项")
