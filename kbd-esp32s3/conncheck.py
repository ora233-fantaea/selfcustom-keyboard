#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""连通性检查：按真实铜箔几何判断每个网络的焊盘是否连通

不依赖 DRC（DRC 一次要几分钟），用并查集 + 空间哈希：
- 走线沿线段每 0.04mm 采样，采样点落在同一 0.05mm 格子即视为相连
  （共端点、T 型搭接、过孔换层都能正确连通）
- 过孔把 F/B 两层在同一点并起来
- 焊盘与落在其外框内（本层）的走线采样点相连
"""
import math
import sys

import board_geom as BG

STEP = 0.04
LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}
CELL = 0.05


class UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        p = self.p
        if a not in p:
            p[a] = a
            return a
        r = a
        while p[r] != r:
            r = p[r]
        while p[a] != r:
            p[a], a = r, p[a]
        return r

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def ck(layer, x, y):
    return (layer, int(math.floor(x / CELL + 0.5)), int(math.floor(y / CELL + 0.5)))


def analyze(path):
    g = BG.load(path)
    uf = UF()
    for t in g["tracks"]:
        L = LMAP.get(t["layer"], 0)
        x1, y1, x2, y2 = t["x1"], t["y1"], t["x2"], t["y2"]
        d = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(d / STEP))
        k0 = ck(L, x1, y1)
        for i in range(1, n + 1):
            f = i / n
            uf.union(k0, ck(L, x1 + (x2 - x1) * f, y1 + (y2 - y1) * f))
    for v in g["vias"]:
        for L in (0, 1, 2, 3):      # 贯穿孔，四层同点相连
            uf.union(ck(0, v["x"], v["y"]), ck(L, v["x"], v["y"]))

    pads = [p for p in g["pads"] if p["net"]]
    # 焊盘 -> 落在外框内的走线采样格
    for p in pads:
        lays = BG.copper_layers(p)
        Ls = ([0, 1, 2, 3] if any("*.Cu" in l for l in p["layers"])
              else sorted(LMAP[l] for l in lays if l in LMAP))
        if not Ls:
            continue
        x0, x1 = p["x"] - p["w"] / 2, p["x"] + p["w"] / 2
        y0, y1 = p["y"] - p["h"] / 2, p["y"] + p["h"] / 2
        pk = ("PAD", p["ref"], p["num"])
        uf.find(pk)
        nx = max(1, int((x1 - x0) / CELL))
        ny = max(1, int((y1 - y0) / CELL))
        for L in Ls:
            for a in range(nx + 1):
                x = x0 + (x1 - x0) * a / nx
                for b in range(ny + 1):
                    y = y0 + (y1 - y0) * b / ny
                    k = ck(L, x, y)
                    if k in uf.p:
                        uf.union(pk, k)

    by_net = {}
    for p in pads:
        by_net.setdefault(p["net"], []).append(p)
    out = {}
    for net, ps in by_net.items():
        if len(ps) < 2:
            continue
        groups = {}
        for p in ps:
            groups.setdefault(uf.find(("PAD", p["ref"], p["num"])), []).append(p)
        if len(groups) > 1:
            out[net] = list(groups.values())
    return out


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "kbd-esp32s3.kicad_pcb"
    bad = analyze(p)
    print(f"未连通网络 {len(bad)} 个:")
    for net in sorted(bad):
        gs = bad[net]
        desc = " | ".join(f"{len(x)}:" + ",".join(f"{q['ref']}.{q['num']}" for q in x[:3])
                          for x in gs)
        print(f"  {net:<10} {desc}")
