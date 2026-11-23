#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板上封装 vs 官方/第三方库的逐焊盘比对

用法: python check_libs.py [board.kicad_pcb]
库目录: ../libs（kicad-official = KiCad 官方子集，MX_Alps_Hybrid = ai03 键盘库）
"""
import os
import sys
import glob

import pcbkit as K
import board_geom as G

LIB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "libs")
TOL = 0.005


def pads_from_node(fp):
    """从 footprint 节点取 [(num, x, y, w, h, drill, type)]，局部坐标"""
    out = []
    for p in K.find_all(fp, "pad"):
        if len(p) < 2:
            continue
        num = str(p[1])
        typ = str(p[2]) if len(p) > 2 else ""
        at = K.get(p, "at")
        sz = K.get(p, "size")
        dr = K.get(p, "drill")
        if at is None or sz is None:
            continue
        x, y = float(at[1]), float(at[2])
        w, h = float(sz[1]), float(sz[2])
        d = 0.0
        if dr is not None and len(dr) > 1:
            vals = []
            for v in dr[1:]:
                try:
                    vals.append(float(v))
                except ValueError:
                    pass
            if vals:
                d = max(vals)          # 椭圆孔取长轴
        out.append((num, round(x, 3), round(y, 3), round(w, 3), round(h, 3), round(d, 3), typ))
    return out


def index_library():
    idx = {}
    for path in glob.glob(os.path.join(LIB_ROOT, "**", "*.kicad_mod"), recursive=True):
        name = os.path.basename(path)[:-len(".kicad_mod")]
        idx.setdefault(name, []).append(path)
    return idx


def load_mod(path):
    root = K.parse(open(path, encoding="utf-8").read())[0]
    if isinstance(root, list) and root and root[0] in ("footprint", "module"):
        return pads_from_node(root)
    return []


def signature(pads):
    """旋转/平移/镜像不变的特征：焊盘数 + 尺寸/孔径集合 + 两两中心距集合"""
    pts = [(p[1], p[2]) for p in pads]
    sizes = sorted((p[3], p[4], p[5]) for p in pads)
    dists = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dx, dy = pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]
            dists.append(round((dx * dx + dy * dy) ** 0.5, 2))
    return len(pads), sizes, sorted(dists)


def diff(a, b):
    na, sa, da = signature(a)
    nb, sb, db = signature(b)
    msgs = []
    if na != nb:
        msgs.append(f"焊盘数不同：板上 {na} / 库 {nb}")
    if len(da) == len(db):
        worst = max((abs(x - y) for x, y in zip(da, db)), default=0.0)
    else:
        worst = float("inf")
    if worst > 0.02:
        msgs.append(f"焊盘相对位置不一致，最大差 {worst:.3f} mm")
        bad_pairs = [(x, y) for x, y in zip(da, db) if abs(x - y) > 0.02][:3]
        msgs.append("示例间距 板上/库: " + ", ".join(f"{x}/{y}" for x, y in bad_pairs))
    if len(sa) == len(sb):
        sd = max((max(abs(u - v) for u, v in zip(x, y)) for x, y in zip(sa, sb)), default=0.0)
        if sd > 0.02:
            msgs.append(f"焊盘尺寸/孔径最大差 {sd:.2f} mm")
            worst = max(worst, sd)
    else:
        msgs.append("焊盘尺寸项数不同")
    return (not msgs), worst, msgs


def main(path="kbd-esp32s3.kicad_pcb"):
    idx = index_library()
    g = G.load(path)
    used = {}
    for fp in g["fps"]:
        used.setdefault(fp["lib"], []).append(fp)
    print(f"库目录 {os.path.abspath(LIB_ROOT)}")
    print(f"库内封装 {sum(len(v) for v in idx.values())} 个，板上用到 {len(used)} 种\n")
    bad = 0
    for lib in sorted(used):
        refs = used[lib]
        # 板上焊盘（相对封装原点）
        fp0 = refs[0]
        bp = []
        for p in g["pads"]:
            if p["ref"] != fp0["ref"]:
                continue
            bx, by = p["x"] - fp0["x"], p["y"] - fp0["y"]
            bp.append((str(p["num"]), round(bx, 3), round(by, 3),
                       round(p["w"], 3), round(p["h"], 3), round(p["drill"], 3),
                       "thru" if p["drill"] > 0 else "smd"))
        if lib not in idx:
            print(f"[--] {lib:<44} x{len(refs):<3} 库中无同名封装")
            bad += 1
            continue
        lp = load_mod(idx[lib][0])
        ok, worst, msgs = diff(bp, lp)
        tag = "OK" if ok else "DIFF"
        if not ok:
            bad += 1
        print(f"[{tag}] {lib:<44} x{len(refs):<3} 焊盘 {len(bp)}/{len(lp)} 最大偏差 {worst:.3f} mm")
        for m in msgs[:4]:
            print(f"       {m}")
        if len(msgs) > 4:
            print(f"       ... 另有 {len(msgs) - 4} 条")

    # MX 轴座：与 ai03 MXOnly-1U-NoLED（标准 MX 通孔）比对孔位
    key = "MXOnly-1U-NoLED"
    if key in idx:
        lib_holes = [(p[1], p[2], p[5]) for p in load_mod(idx[key][0]) if p[6].startswith(("thru", "np_thru"))]
        sw = next(f for f in g["fps"] if f["ref"] == "SW01")
        mine = [(round(p["x"] - sw["x"], 3), round(p["y"] - sw["y"], 3), p["drill"])
                for p in g["pads"] if p["ref"] == "SW01" and p["drill"] > 0]

        def dsig(pts):
            return sorted(round(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5, 2)
                          for i, a in enumerate(pts) for b in pts[i + 1:])

        same = len(mine) == len(lib_holes) and dsig(mine) == dsig(lib_holes)
        print(f"\n[{'OK' if same else 'DIFF'}] MX 轴座孔位 vs {key}（{len(mine)} 孔）")
        print(f"       板上孔径 {sorted(round(m[2],2) for m in mine)}")
        print(f"       库孔径   {sorted(round(l[2],2) for l in lib_holes)}")
        if same:
            print("       孔位两两间距完全一致（本封装为 180° 放置，电气对称）")
        else:
            bad += 1

    print(f"\n{len(used) - bad} 种与库一致，{bad} 种存在差异或缺库")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
