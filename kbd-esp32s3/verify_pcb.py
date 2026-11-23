#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PCB 几何校验：同层不同网络的最小间距 + 逐网络连通性 + 走线到开槽间距"""
import math
import sys
from collections import defaultdict

import board_geom as BG

MIN_CLEAR = 0.20
BUCKET = 2.0


def seg_pt(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def seg_seg(a, b):
    x1, y1, x2, y2 = a
    x3, y3, x4, y4 = b
    d1 = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
    d2 = (x4 - x3) * (y2 - y3) - (y4 - y3) * (x2 - x3)
    d3 = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
    d4 = (x2 - x1) * (y4 - y1) - (y2 - y1) * (x4 - x1)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(seg_pt(x1, y1, x3, y3, x4, y4), seg_pt(x2, y2, x3, y3, x4, y4),
               seg_pt(x3, y3, x1, y1, x2, y2), seg_pt(x4, y4, x1, y1, x2, y2))


def pt_rect(px, py, r):
    x1, y1, x2, y2 = r
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return math.hypot(dx, dy)


def seg_rect(a, r):
    x1, y1, x2, y2 = a
    rx1, ry1, rx2, ry2 = r
    if rx1 <= x1 <= rx2 and ry1 <= y1 <= ry2:
        return 0.0
    if rx1 <= x2 <= rx2 and ry1 <= y2 <= ry2:
        return 0.0
    best = min(pt_rect(rx1, ry1, a), pt_rect(rx2, ry1, a),
               pt_rect(rx1, ry2, a), pt_rect(rx2, ry2, a))
    best = min(best, seg_pt(x1, y1, rx1, ry1, rx2, ry1), seg_pt(x1, y1, rx2, ry1, rx2, ry2),
               seg_pt(x1, y1, rx2, ry2, rx1, ry2), seg_pt(x1, y1, rx1, ry2, rx1, ry1))
    best = min(best, seg_pt(x2, y2, rx1, ry1, rx2, ry1), seg_pt(x2, y2, rx2, ry1, rx2, ry2),
               seg_pt(x2, y2, rx2, ry2, rx1, ry2), seg_pt(x2, y2, rx1, ry2, rx1, ry1))
    return best


class Item:
    __slots__ = ("kind", "net", "layers", "seg", "rect", "pt", "r", "ref", "bbox")

    def __init__(self, kind, net, layers, ref="", seg=None, rect=None, pt=None, r=0.0):
        self.kind, self.net, self.layers, self.ref = kind, net, layers, ref
        self.seg, self.rect, self.pt, self.r = seg, rect, pt, r
        if seg:
            x1, y1, x2, y2 = seg
            self.bbox = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        elif rect:
            self.bbox = rect
        else:
            self.bbox = (pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r)


def build_items(g):
    items = []
    for p in g["pads"]:
        if not p["net"]:
            continue
        lays = frozenset(BG.copper_layers(p))
        if not lays:
            continue
        items.append(Item("pad", p["net"], lays, p["ref"],
                          rect=(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2,
                                p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)))
    for t in g["tracks"]:
        items.append(Item("trk", t["net"], frozenset([t["layer"]]),
                          seg=(t["x1"], t["y1"], t["x2"], t["y2"]), r=t["w"] / 2))
    for v in g["vias"]:
        items.append(Item("via", v["net"], frozenset(["F.Cu", "B.Cu"]),
                          pt=(v["x"], v["y"]), r=v["d"] / 2))
    return items


def gap(a, b):
    """两个铜元素边缘之间的最小间距"""
    if a.seg and b.seg:
        return seg_seg(a.seg, b.seg) - a.r - b.r
    if a.seg and b.rect:
        return seg_rect(a.seg, b.rect) - a.r
    if a.rect and b.seg:
        return seg_rect(b.seg, a.rect) - b.r
    if a.seg and b.pt:
        return seg_pt(b.pt[0], b.pt[1], *a.seg) - a.r - b.r
    if a.pt and b.seg:
        return seg_pt(a.pt[0], a.pt[1], *b.seg) - a.r - b.r
    if a.rect and b.rect:
        dx = max(a.rect[0] - b.rect[2], b.rect[0] - a.rect[2], 0.0)
        dy = max(a.rect[1] - b.rect[3], b.rect[1] - a.rect[3], 0.0)
        return math.hypot(dx, dy)
    if a.rect and b.pt:
        return pt_rect(b.pt[0], b.pt[1], a.rect) - b.r
    if a.pt and b.rect:
        return pt_rect(a.pt[0], a.pt[1], b.rect) - a.r
    return math.hypot(a.pt[0] - b.pt[0], a.pt[1] - b.pt[1]) - a.r - b.r


def main(path):
    g = BG.load(path)
    items = build_items(g)
    print(f"铜元素 {len(items)}（焊盘/走线/过孔），走线 {len(g['tracks'])}，过孔 {len(g['vias'])}")

    # ---------- 1. 间距 ----------
    buckets = defaultdict(list)
    for it in items:
        x1, y1, x2, y2 = it.bbox
        for bx in range(int(math.floor(x1 / BUCKET)), int(math.floor(x2 / BUCKET)) + 1):
            for by in range(int(math.floor(y1 / BUCKET)), int(math.floor(y2 / BUCKET)) + 1):
                buckets[(bx, by)].append(it)

    seen = set()
    viol = []
    for cell, lst in buckets.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                k = (id(a), id(b))
                if k in seen:
                    continue
                seen.add(k)
                if a.net == b.net:
                    continue
                if not (a.layers & b.layers):
                    continue
                gv = gap(a, b)
                if gv < MIN_CLEAR - 1e-6:
                    viol.append((gv, a, b))
    viol.sort(key=lambda t: t[0])
    print(f"\n[1] 同层异网间距 < {MIN_CLEAR}mm 的违例: {len(viol)}")
    for gv, a, b in viol[:15]:
        print(f"   {gv:.3f}mm  {a.kind}({a.net},{a.ref}) ↔ {b.kind}({b.net},{b.ref})")

    # ---------- 2. 走线到开槽 ----------
    sbad = 0
    for t in g["tracks"]:
        for s in g["slots"]:
            d = seg_rect((t["x1"], t["y1"], t["x2"], t["y2"]), s[:4]) - t["w"] / 2
            if d < 0.2:
                sbad += 1
                break
    print(f"[2] 走线到开槽 < 0.2mm 的条数: {sbad}")

    # ---------- 3. 连通性 ----------
    parent = list(range(len(items)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    idx_b = defaultdict(list)
    for i, it in enumerate(items):
        x1, y1, x2, y2 = it.bbox
        for bx in range(int(math.floor(x1 / BUCKET)), int(math.floor(x2 / BUCKET)) + 1):
            for by in range(int(math.floor(y1 / BUCKET)), int(math.floor(y2 / BUCKET)) + 1):
                idx_b[(bx, by)].append(i)
    for cell, lst in idx_b.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = items[lst[i]], items[lst[j]]
                if a.net != b.net or not (a.layers & b.layers):
                    continue
                if gap(a, b) <= 0.0:
                    uni(lst[i], lst[j])

    nets = defaultdict(list)
    for i, it in enumerate(items):
        if it.kind == "pad":
            nets[it.net].append(i)

    bad = []
    for net, ids in nets.items():
        roots = {find(i) for i in ids}
        if len(roots) > 1:
            bad.append((net, len(ids), len(roots)))
    bad.sort(key=lambda t: t[1])
    print(f"\n[3] 未完全连通的网络: {len(bad)}")
    for net, np_, nr in bad[:20]:
        print(f"   {net}: {np_} 个焊盘分散在 {nr} 个岛")

    total = len(nets)
    print(f"\n汇总: 网络 {total}, 间距违例 {len(viol)}, 未连通 {len(bad)}")
    return 0 if (not viol and not bad) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "kbd-esp32s3.kicad_pcb"))
