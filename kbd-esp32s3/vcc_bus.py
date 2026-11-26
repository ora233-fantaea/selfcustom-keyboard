#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VCC 电源分配（不用平面，避免贯穿孔割断内层）。

为什么不用 VCC 平面：R 排的 1 脚是 VCC、2 脚是各键网，交替排列（间距 1.65mm）。
若 In1 铺 VCC 平面，任何从 F.Cu 下到 In2/B 的信号过孔都会穿过它 —— 实测就是
101 处短路。所以 In1 给 GND，VCC 走 In2 的水平总线：

  1. 每个 R.1 焊盘内打一个贯穿孔（焊盘内，同网天然合法）；
  2. In2 上把同一排相邻孔横向串起来（间距 3.06mm）；
  3. 两排之间、以及 165 的 VCC 脚 / 去耦电容，就近接入总线。

必须在布 K 网之前跑：先占好 VCC 的孔位和走廊，K 网再绕。
"""
import json
import os
import sys
import time

import numpy as np

import board_geom as BG
import router
from autoroute import build_grid, pad_layers

router.GRID = 0.2
G = router.GRID
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
OUT = os.path.join(HERE, "_vcc.json")

g = BG.load(PCB)
pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
NET_ID = {n: i + 1 for i, n in enumerate(sorted(pads_by_net))}
LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}
NID = NET_ID["VCC"]

gr = build_grid(g)
for t in g["tracks"]:
    if t["net"] in NET_ID:
        gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]),
                  NET_ID[t["net"]], LMAP[t["layer"]])
for v in g["vias"]:
    if v["net"] in NET_ID:
        gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])

items = []
done = []          # 已打孔的 (x, y)
skipped = []

VCC_PADS = [p for p in pads_by_net["VCC"] if p.get("drill", 0) == 0]


def clear_for_via(x, y, nid):
    """贯穿孔会穿 In2 和 B.Cu，两层都必须空或本网（In1 是 GND 铺铜，自动避让）"""
    i, j = gr.ix(x), gr.iy(y)
    for L in (2, 3):
        if gr.blocked[L, j, i]:
            return False
        o = gr.occ[L, j, i]
        if o != 0 and o != nid:
            return False
    return True


def spot_in_pad(pad, nid):
    """在焊盘里找一个能打贯穿孔的位置，优先中心"""
    cx, cy = pad["x"], pad["y"]
    hw, hh = pad["w"] / 2.0, pad["h"] / 2.0
    i0, i1 = gr.ix(cx - hw + 0.06), gr.ix(cx + hw - 0.06)
    j0, j1 = gr.iy(cy - hh + 0.06), gr.iy(cy + hh - 0.06)
    best = None
    for j in range(max(0, j0), min(gr.ny - 1, j1) + 1):
        for i in range(max(0, i0), min(gr.nx - 1, i1) + 1):
            x, y = i * G, j * G
            if not clear_for_via(x, y, nid):
                continue
            d = (x - cx) ** 2 + (y - cy) ** 2
            if best is None or d < best[0]:
                best = (d, x, y)
    return None if best is None else (best[1], best[2])


# ---- 1) 给每个 VCC SMD 焊盘打孔 ----
for p in VCC_PADS:
    s = spot_in_pad(p, NID)
    if s is None:
        skipped.append((p["ref"], p["num"]))
        continue
    x, y = s
    items.append(("via", "VCC", x, y))
    i, j = gr.ix(x), gr.iy(y)
    for L in (2, 3):                     # 贯穿孔，占住内层
        gr.occ[L, j, i] = NID
    gr.mark_via(i, j, NID)
    done.append((x, y))

print(f"VCC 孔 {len(done)} 个，无孔位 {len(skipped)} 个 {skipped[:6]}", flush=True)

# ---- 2) In2 横向串接：按 y 分行，同排相邻孔连起来 ----
rows = {}
for x, y in done:
    rows.setdefault(round(y, 1), []).append(x)

links = 0
for y, xs in sorted(rows.items()):
    xs.sort()
    for xa, xb in zip(xs, xs[1:]):
        if xb - xa > 6.0:                # 缺口太大，交给 A* 或后续
            pass
        p = gr.astar((xa, y, 2), (xb, y, 2), NID,
                     margin_mm=max(3.0, xb - xa + 2.0), budget=200_000,
                     deadline=time.monotonic() + 3.0)
        if p is None:
            continue
        seg = [(i * G, j * G) for L, j, i in p]
        seg = [q for k, q in enumerate(seg) if k == 0 or q != seg[k - 1]]
        for a, b in zip(seg, seg[1:]):
            items.append(("seg", "VCC", 2, [a[0], a[1]], [b[0], b[1]]))
        for L, j, i in p:
            gr.occ[2, j, i] = NID
        links += 1

print(f"In2 横向串接 {links} 段", flush=True)

tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(items, f)
os.replace(tmp, OUT)
print("写出", OUT, len(items), "项")
