#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中孔扇出：解决 R.2 出线空间不足。

75 个上拉电阻的 1 脚(VCC) 在焊盘中心有 0.6mm 贯穿孔，2 脚(K 网) 就在
1.65mm 外。留给 2 脚出线的缝隙只有 1.65-0.4-0.4-0.3 = 0.55mm，
而一条 0.15 线要 0.85mm —— A* 和波前都过不去。

做法：直接在 R.2 焊盘内部打孔（0.3 钻 / 0.6 外径，环宽 0.15 合法），
下到 In2 再走。焊盘 0.8x0.95 放得下。
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
OUT = os.path.join(HERE, "_pinfan.json")

TARGETS = sys.argv[1].split(",") if len(sys.argv) > 1 else []

g = BG.load(PCB)
pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
NET_ID = {n: i + 1 for i, n in enumerate(sorted(pads_by_net))}
LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}

print(f"栅格… 走线 {len(g['tracks'])} / 过孔 {len(g['vias'])}", flush=True)
gr = build_grid(g)
for t in g["tracks"]:
    if t["net"] in NET_ID:
        gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]),
                  NET_ID[t["net"]], LMAP[t["layer"]])
for v in g["vias"]:
    if v["net"] in NET_ID:
        gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])


def spot_in_pad(pad, nid):
    """焊盘内找一格 In2 上可打贯穿孔的位置（中心优先）"""
    cx, cy = pad["x"], pad["y"]
    hw, hh = pad["w"] / 2.0, pad["h"] / 2.0
    i0, i1 = gr.ix(cx - hw + 0.1), gr.ix(cx + hw - 0.1)
    j0, j1 = gr.iy(cy - hh + 0.1), gr.iy(cy + hh - 0.1)
    best = None
    for j in range(max(0, j0), min(gr.ny - 1, j1) + 1):
        for i in range(max(0, i0), min(gr.nx - 1, i1) + 1):
            if gr.blocked[2, j, i] or gr.blocked[3, j, i]:
                continue
            # 孔-孔最小间距 0.5mm：半径 3 格（0.6mm）内不能已有孔
            if gr.via_used[0, max(0, j - 3):j + 4,
                           max(0, i - 3):i + 4].any():
                continue
            okk = True
            for L in (2, 3):
                o = gr.occ[L, j, i]
                if o != 0 and o != nid:
                    okk = False
                    break
            if not okk:
                continue
            d = (i * G - cx) ** 2 + (j * G - cy) ** 2
            if best is None or d < best[0]:
                best = (d, i, j)
    return None if best is None else (best[1] * G, best[2] * G)


def k_chip_net(net):
    """该网在 165 上的引脚（若存在，只取一个）"""
    for p in pads_by_net.get(net, []):
        if p["ref"].startswith("U"):
            return p
    return None


items = []
ok = fail = 0
for net in TARGETS:
    if net not in NET_ID:
        print(f"  [!] {net} 无网络号"); continue
    nid = NET_ID[net]
    kn = int(net[1:]) if net.startswith("K") and net[1:].isdigit() else None
    cands = []
    if kn:
        for ref, num in ((f"R{kn:02d}", "2"), (f"SW{kn:02d}", "1")):
            for p in pads_by_net[net]:
                if p["ref"] == ref and p["num"] == num:
                    cands.append(p)
    u = k_chip_net(net)
    if u is not None:
        cands.append(u)
    seen = set()
    uniq = []
    for p in cands:
        k = (p["ref"], p["num"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    cands = uniq
    if len(cands) < 2:
        print(f"  [×] {net} 焊盘不足 {len(cands)}"); continue

    # 每个焊盘找接入点：
    #  - R.2 / U 焊盘：打盘中孔下到 In2
    #  - SW 焊盘：背面贴装（B.Cu），本身有 3.0mm 通孔、环宽只有 0.2mm，
    #    放不下新孔，直接从 B.Cu 的 SMD 焊盘出线即可
    spots = []
    for p in cands:
        if p["ref"].startswith("SW"):
            # SW 的通孔焊盘 3.4/3.0 在 F.Cu 上也有 0.2mm 环，
            # F.Cu 在键区是空的，直接从 F.Cu 出线最快
            spots.append((p, (p["x"], p["y"]), 0))
            continue
        st = spot_in_pad(p, nid)
        if st is None:
            print(f"  [×] {net} {p['ref']}.{p['num']} 焊盘内无孔位", flush=True)
            continue
        items.append(("via", net, round(st[0], 3), round(st[1], 3)))
        gr.mark_via(gr.ix(st[0]), gr.iy(st[1]), nid)
        for L in (2, 3):
            gr.occ[L, gr.iy(st[1]), gr.ix(st[0])] = nid
        spots.append((p, st, 2))
    if len(spots) < 2:
        fail += 1
        continue

    # 相邻孔在 In2 上 A* 连接
    t0 = time.monotonic()
    for a, b in zip(spots, spots[1:]):
        (pa, sa, la), (pb, sb, lb) = a, b
        saa = gr.open_pad(pa, pad_layers(pa))
        sbb = gr.open_pad(pb, pad_layers(pb))
        try:
            p = gr.astar((sa[0], sa[1], la), (sb[0], sb[1], lb), nid,
                         margin_mm=max(18.0, min(abs(sa[0] - sb[0]) +
                                                 abs(sa[1] - sb[1]) + 12.0, 120.0)),
                         budget=1_500_000, deadline=time.monotonic() + 20.0)
        finally:
            gr.restore(saa)
            gr.restore(sbb)
        if p is None:
            fail += 1
            print(f"    [×] {pa['ref']}.{pa['num']} - {pb['ref']}.{pb['num']}", flush=True)
            continue
        seq = [(nd[0] * G, nd[1] * G, nd[2]) for nd in p]
        seq = [q for k, q in enumerate(seq) if k == 0 or q != seq[k - 1]]
        for c, d in zip(seq, seq[1:]):
            if c[2] == d[2]:
                items.append(("seg", net, c[2], [c[0], c[1]], [d[0], d[1]]))
            else:
                items.append(("via", net, round(c[0], 3), round(c[1], 3)))
        for nd in p:
            gr.occ[nd[2], nd[1], nd[0]] = nid
        ok += 1
    print(f"  {net}: {len(spots)} 孔 {time.monotonic()-t0:.0f}s", flush=True)


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
print(f"\n成功 {ok} 段 / 失败 {fail}，写出 {len(items)} 项")
