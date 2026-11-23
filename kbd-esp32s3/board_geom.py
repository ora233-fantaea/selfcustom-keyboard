#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 .kicad_pcb 中提取带旋转的世界坐标几何（焊盘/槽/走线/过孔/板框）"""
import math
import pcbkit as K

ROT_SWAP = {90, 270}


def _rot(dx, dy, deg):
    d = deg % 360
    if d == 0:
        return dx, dy
    if d == 90:
        return dy, -dx
    if d == 180:
        return -dx, -dy
    if d == 270:
        return -dy, dx
    a = math.radians(d)
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def load(path):
    root = K.parse(open(path, encoding="utf-8").read())[0]
    g = dict(board=root, fps=[], pads=[], slots=[], tracks=[], vias=[])
    netname = {}
    for n in K.find_all(root, "net"):
        if len(n) >= 3:
            netname[str(n[1])] = str(n[2])

    def netof(node):
        if node is None:
            return ""
        if len(node) >= 3:
            return str(node[2])
        return netname.get(str(node[1]), "")

    for fp in K.find_all(root, "footprint"):
        at = K.get(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        rot = float(at[3]) if len(at) > 3 else 0.0
        ref = "?"
        for p in K.get_all(fp, "property"):
            if p[1] == "Reference":
                ref = p[2]
        entry = dict(ref=ref, lib=fp[1], x=fx, y=fy, rot=rot, pads=[])
        for pad in K.get_all(fp, "pad"):
            pat = K.get(pad, "at")
            dx, dy = float(pat[1]), float(pat[2])
            prot = float(pat[3]) if len(pat) > 3 else 0.0
            sz = K.get(pad, "size")
            w, h = float(sz[1]), float(sz[2])
            rx, ry = _rot(dx, dy, rot)
            if (rot + prot) % 180 == 90:
                w, h = h, w
            dr = K.get(pad, "drill")
            drill = 0.0
            if dr:
                nums = [float(v) for v in dr[1:] if not isinstance(v, list) and v != "oval"]
                drill = max(nums) if nums else 0.0
            layers = K.get(pad, "layers")
            lays = [str(x) for x in layers[1:]] if layers else []
            net = K.get(pad, "net")
            p = dict(num=str(pad[1]), x=fx + rx, y=fy + ry, w=w, h=h, drill=drill,
                     shape=str(pad[3]), layers=lays,
                     net=netof(net))
            entry["pads"].append(p)
            g["pads"].append(dict(p, ref=ref))
        g["fps"].append(entry)

    # 槽：Edge.Cuts 中非外框的闭合矩形
    segs = []
    for ln in K.find_all(root, "gr_line"):
        lay = K.get(ln, "layer")
        if lay and str(lay[1]) == "Edge.Cuts":
            s, e = K.get(ln, "start"), K.get(ln, "end")
            segs.append((float(s[1]), float(s[2]), float(e[1]), float(e[2])))
    parent = list(range(len(segs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    from collections import defaultdict
    bypt = defaultdict(list)
    for i, (x1, y1, x2, y2) in enumerate(segs):
        bypt[(round(x1, 3), round(y1, 3))].append(i)
        bypt[(round(x2, 3), round(y2, 3))].append(i)
    for _, lst in bypt.items():
        for k in lst[1:]:
            uni(lst[0], k)
    grp = defaultdict(list)
    for i in range(len(segs)):
        grp[find(i)].append(i)
    conts = []
    for _, idxs in grp.items():
        xs, ys = [], []
        for i in idxs:
            xs += [segs[i][0], segs[i][2]]
            ys += [segs[i][1], segs[i][3]]
        conts.append((min(xs), min(ys), max(xs), max(ys), len(idxs)))
    conts.sort(key=lambda c: (c[2] - c[0]) * (c[3] - c[1]), reverse=True)
    g["outline"] = conts[0]
    g["slots"] = [c for c in conts[1:]]

    for t in K.find_all(root, "segment"):
        s, e = K.get(t, "start"), K.get(t, "end")
        w = K.get(t, "width")
        lay = K.get(t, "layer")
        net = K.get(t, "net")
        g["tracks"].append(dict(x1=float(s[1]), y1=float(s[2]), x2=float(e[1]), y2=float(e[2]),
                                w=float(w[1]), layer=str(lay[1]),
                                net=netof(net)))
    for v in K.find_all(root, "via"):
        at = K.get(v, "at"); sz = K.get(v, "size"); dr = K.get(v, "drill")
        net = K.get(v, "net")
        g["vias"].append(dict(x=float(at[1]), y=float(at[2]), d=float(sz[1]),
                              drill=float(dr[1]), net=netof(net)))
    return g


def copper_layers(pad):
    """返回该焊盘占用的铜层集合"""
    lays = pad["layers"]
    if any("*.Cu" in l for l in lays):
        return {"F.Cu", "B.Cu"}
    out = set()
    if any("F.Cu" in l for l in lays):
        out.add("F.Cu")
    if any("B.Cu" in l for l in lays):
        out.add("B.Cu")
    return out


if __name__ == "__main__":
    import sys
    g = load(sys.argv[1])
    print("封装", len(g["fps"]), "焊盘", len(g["pads"]), "槽", len(g["slots"]),
          "走线", len(g["tracks"]), "过孔", len(g["vias"]))
    print("外框", g["outline"])
    for p in g["pads"]:
        if p["ref"] in ("J_P1", "J_P2"):
            print(f"  {p['ref']}.{p['num']} ({p['x']:.2f},{p['y']:.2f}) {p['w']}x{p['h']}")
