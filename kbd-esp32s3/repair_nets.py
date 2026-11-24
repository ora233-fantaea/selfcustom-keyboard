#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定向修复：摘除指定网络的走线，在「其余走线已占用」的网格上重布。

用法: python repair_nets.py K67 K74 K75
"""
import math
import os
import sys
import time
import uuid

import pcbkit as K
import board_geom as BG
import kbd_design as D
from autoroute import build_grid, pad_layers, LAYER_NAME
from router import path_to_geom

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")

BAD = set(a for a in sys.argv[1:] if not a.startswith("-"))

g = BG.load(PCB)                      # 已布线文件（取走线清单）
gr = build_grid(BG.load("_unrouted.kicad_pcb"))   # 干净网格

pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
nets = sorted(pads_by_net)
NET_ID = {n: i + 1 for i, n in enumerate(nets)}

LAY = {"F.Cu": 0, "B.Cu": 1}

# 1) 占用除 BAD 外的全部走线与过孔
kept_traces, kept_vias = [], []
for t in g["tracks"]:
    if t["net"] in BAD:
        continue
    gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]), NET_ID[t["net"]], LAY[t["layer"]])
    kept_traces.append(t)
for v in g["vias"]:
    if v["net"] in BAD:
        continue
    gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])
    kept_vias.append(v)
print(f"保留走线 {len(kept_traces)} 段 / 过孔 {len(kept_vias)} 个；重布 {sorted(BAD)}")


def pad_of(ref, num):
    for p in g["pads"]:
        if p["ref"] == ref and p["num"] == str(num):
            return p


def pick(net, ref, num):
    for p in pads_by_net.get(net, []):
        if p["ref"] == ref and p["num"] == str(num):
            return p


# 2) 重布 BAD 网络的任务
new_traces, new_vias = [], []
for kn in sorted(int(n[1:]) for n in BAD):
    net = f"K{kn:02d}" if kn < 100 else f"K{kn}"
    net = f"K{kn}"
    chip = None
    for i, inputs in enumerate(D.CHIP_INPUTS):
        for pin, k2 in inputs:
            if k2 == kn:
                chip = (i + 1, pin)
    if chip is None:
        print(f"  [跳过] {net}: 找不到芯片引脚")
        continue
    uid, upin = chip
    tasks = []
    sw = pick(net, f"SW{kn:02d}", "1")
    ic = pick(net, f"U{uid}", upin)
    rp = pick(net, f"R{kn:02d}", "2")
    if ic and rp:
        tasks.append((ic, rp))
    if sw and ic:
        tasks.append((sw, ic))
    for a, b in tasks:
        nid = NET_ID[net]
        la = pad_layers(a)[0] if pad_layers(a) else 0
        lb = pad_layers(b)[0] if pad_layers(b) else 0
        sa = gr.open_pad(a, pad_layers(a))
        sb = gr.open_pad(b, pad_layers(b))
        span = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        t_end = time.monotonic() + 200.0
        path = None
        for mg in (max(14.0, span * 0.9), max(40.0, span * 1.8), max(80.0, span * 2.5)):
            path = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), nid,
                            margin_mm=mg, budget=10_000_000, deadline=t_end)
            if path is None:
                path = gr.astar((a["x"], a["y"], 1 - la), (b["x"], b["y"], 1 - lb), nid,
                                margin_mm=mg, budget=10_000_000, deadline=t_end)
            if path is not None:
                break
        gr.restore(sa)
        gr.restore(sb)
        if path is None:
            print(f"  [失败] {net} {a['ref']}.{a['num']}->{b['ref']}.{b['num']}")
            continue
        geo, vs = path_to_geom(gr, path)
        for L, pts in geo:
            for p, q in zip(pts, pts[1:]):
                if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                    continue
                gr.occupy(p, q, nid, L)
                new_traces.append((net, LAYER_NAME[L], p, q))
        for (vx, vy) in vs:
            gr.mark_via(gr.ix(vx), gr.iy(vy), nid)
            new_vias.append((net, vx, vy))
        print(f"  [重布] {net} {a['ref']}.{a['num']}->{b['ref']}.{b['num']} "
              f"len={sum(math.hypot(q[0]-p[0], q[1]-p[1]) for L, pts in geo for p, q in zip(pts, pts[1:])):.0f}mm")

# 3) 写回：原走线去掉 BAD 网的，加上新布的
root = K.parse(open(PCB, encoding="utf-8").read())[0]
segs = [n for n in root[1:] if isinstance(n, list) and n[0] == "segment"]
vias = [n for n in root[1:] if isinstance(n, list) and n[0] == "via"]
netid = {str(n[2]): str(n[1]) for n in K.find_all(root, "net")}

def net_name_of(node):
    nn = K.get(node, "net")
    if nn is None:
        return ""
    if len(nn) >= 3:
        return str(nn[2])
    return netname.get(str(nn[1]), "")


netname = {str(n[1]): str(n[2]) for n in K.find_all(root, "net") if len(n) >= 3}
drop_seg, drop_via = 0, 0
for n in segs:
    if net_name_of(n) in BAD:
        root.remove(n)
        drop_seg += 1
for n in vias:
    if net_name_of(n) in BAD:
        root.remove(n)
        drop_via += 1

added = 0
for net, layer, p, q in new_traces:
    if net not in netid:
        continue
    root.append(["segment",
                 ["start", f"{p[0]:.3f}", f"{p[1]:.3f}"],
                 ["end", f"{q[0]:.3f}", f"{q[1]:.3f}"],
                 ["width", "0.15"],
                 ["layer", K.Str(layer)],
                 ["net", netid[net]],
                 ["uuid", K.Str(str(uuid.uuid4()))]])
    added += 1
for net, vx, vy in new_vias:
    if net not in netid:
        continue
    root.append(["via", ["at", f"{vx:.3f}", f"{vy:.3f}"],
                 ["size", "0.6"], ["drill", "0.3"],
                 ["layers", K.Str("F.Cu"), K.Str("B.Cu")],
                 ["net", netid[net]],
                 ["uuid", K.Str(str(uuid.uuid4()))]])

open(PCB, "w", encoding="utf-8").write(K.dumps(root, pretty=True) + "\n")
print(f"删除 {drop_seg} 段旧走线 / {drop_via} 个旧过孔，新增 {added} 段")
