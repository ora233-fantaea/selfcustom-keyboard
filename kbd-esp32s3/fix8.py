#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定点重布：CHAIN_10 / LED_DATA / V5 / 5 条断开的 K 网。

删掉原走线后用修好的栅格（板边与开槽在 4 层上都已避让）重布。
分组用 conncheck 的连通分量，就近 MST 连接 —— 对菊花链（165 级联、LED 级联）
物理最近的焊盘就是电气上相邻的那一对，MST 正好还原原拓扑。
"""
import json
import os
import time

import numpy as np

import board_geom as BG
import conncheck as CC
import router
from autoroute import build_grid, pad_layers

router.GRID = 0.2
G = router.GRID
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
OUT = os.path.join(HERE, "_fix8.json")

TARGETS = ["V5"]

g = BG.load(PCB)
pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
NET_ID = {n: i + 1 for i, n in enumerate(sorted(pads_by_net))}
LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}

print(f"栅格构建… 走线 {len(g['tracks'])} / 过孔 {len(g['vias'])}", flush=True)
gr = build_grid(g)
for t in g["tracks"]:
    if t["net"] in NET_ID:
        gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]),
                  NET_ID[t["net"]], LMAP[t["layer"]])
for v in g["vias"]:
    if v["net"] in NET_ID:
        gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])
print(f"  {gr.nx}x{gr.ny}", flush=True)

miss = CC.analyze(PCB)
items = []
ok = fail = 0

for net in TARGETS:
    if net not in NET_ID:
        print(f"  [!] {net} 不在网络表"); continue
    nid = NET_ID[net]
    groups = miss.get(net, [])
    if not groups:
        print(f"  [=] {net} 已连通，跳过"); continue
    # 每组 -> 焊盘列表
    segs = []
    for gp in groups:
        ps = [p for p in pads_by_net[net]
              if any(p["ref"] == q["ref"] and p["num"] == q["num"] for q in gp)]
        if ps:
            segs.append(ps)
    print(f"  {net}: {len(segs)} 段", flush=True)
    t_net = time.monotonic()
    while len(segs) > 1:
        best = None
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                for aa in segs[i]:
                    for bb in segs[j]:
                        d = (aa["x"] - bb["x"]) ** 2 + (aa["y"] - bb["y"]) ** 2
                        if best is None or d < best[0]:
                            best = (d, i, j, aa, bb)
        _, i, j, aa, bb = best
        p = None
        sa = gr.open_pad(aa, pad_layers(aa))
        sb = gr.open_pad(bb, pad_layers(bb))
        try:
            for la in (pad_layers(aa) or (0,)):
                for lb in (pad_layers(bb) or (0,)):
                    span = abs(aa["x"] - bb["x"]) + abs(aa["y"] - bb["y"])
                    p = gr.astar((aa["x"], aa["y"], la), (bb["x"], bb["y"], lb), nid,
                                 margin_mm=max(18.0, min(span + 10.0, 110.0)),
                                 budget=1_500_000,
                                 deadline=time.monotonic() + 15.0)
                    if p is not None:
                        break
                if p is not None:
                    break
        finally:
            gr.restore(sa)
            gr.restore(sb)
        if p is None:
            fail += 1
            print(f"    [×] {aa['ref']}.{aa['num']} - {bb['ref']}.{bb['num']}", flush=True)
            segs[i] = segs[i] + segs[j]
            del segs[j]
            continue
        # 节点顺序是 (i, j, L)：i=x 索引、j=y 索引、L=层
        seq = [(nd[0] * G, nd[1] * G, nd[2]) for nd in p]
        seq = [q for k, q in enumerate(seq) if k == 0 or q != seq[k - 1]]
        for a, b in zip(seq, seq[1:]):
            if a[2] == b[2]:
                items.append(("seg", net, a[2], [a[0], a[1]], [b[0], b[1]]))
            else:
                items.append(("via", net, a[0], a[1]))
        for nd in p:
            gr.occ[nd[2], nd[1], nd[0]] = nid
        ok += 1
        segs[i] = segs[i] + segs[j]
        del segs[j]
    print(f"    {net} 完成 {time.monotonic()-t_net:.0f}s，剩 {len(segs)} 段", flush=True)

def _cv(o):
    if isinstance(o, (tuple, list)):
        return [_cv(x) for x in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return o


tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(_cv(items), f)
os.replace(tmp, OUT)
print(f"\n成功 {ok} 段 / 失败 {fail}，写出 {len(items)} 项 -> {OUT}")
