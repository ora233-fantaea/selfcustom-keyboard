#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""route4：4 层板布线（In1 留作 GND 平面，走线用 F / In2 / B）

为什么这次能成
--------------
2 层板上 75 条按键线全挤在 F.Cu 的 IC 焊盘列 + 两排上拉电阻（1.65mm 间距）
的缝里，物理容量不够。4 层后多出 In2.Cu 一整层空的纵向高速通道：
每条键线在按键旁打孔下到 In2，一路直下（开槽门容量翻倍），
到 IC 附近再打孔上 F.Cu 进焊盘。F.Cu 只剩 R 短跳和最后 2mm。

落地方式：本脚本只输出 _routes.json，由 apply_routes.py 用 pcbnew 写板，
避免手写 s-expr 出现 KiCad 打不开的文件。
"""
import json
import math
import os
import sys
import time

import numpy as np

import board_geom as BG
import kbd_design as D
import router
from router import path_to_geom

router.GRID = 0.2
G = router.GRID
SIG = router.SIG
from autoroute import build_grid, pad_layers, LAYER_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
OUT = os.path.join(HERE, "_routes.json")

g = BG.load(PCB)
gr = build_grid(g)
pads_by_net = {}
for p in g["pads"]:
    if p["net"]:
        pads_by_net.setdefault(p["net"], []).append(p)
NET_ID = {n: i + 1 for i, n in enumerate(sorted(pads_by_net))}
LAY = {v: k for k, v in LAYER_NAME.items()}
for t in g["tracks"]:
    if t["net"] in NET_ID and t["layer"] in LAY:
        gr.occupy((t["x1"], t["y1"]), (t["x2"], t["y2"]), NET_ID[t["net"]], LAY[t["layer"]])
for v in g["vias"]:
    if v["net"] in NET_ID:
        gr.mark_via(gr.ix(v["x"]), gr.iy(v["y"]), NET_ID[v["net"]])
print(f"既有走线 {len(g['tracks'])} 段 / 过孔 {len(g['vias'])} 个  "
      f"栅格 {gr.nx}x{gr.ny}x{router.NL}", flush=True)

PADIDX = {}
for p in g["pads"]:
    k = (p["ref"], p["num"])
    cur = PADIDX.get(k)
    if cur is None or (p.get("drill", 0) > 0 and cur.get("drill", 0) == 0):
        PADIDX[k] = p

items = []          # ("seg", net, layer_idx, (x1,y1), (x2,y2)) / ("via", net, x, y)


def _cv(o):
    """numpy 标量不能直接 json 序列化"""
    if isinstance(o, (tuple, list)):
        return [_cv(x) for x in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return o


def dump():
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_cv(items), f)
    os.replace(tmp, OUT)


def commit(path, net):
    nid = NET_ID[net]
    geo, vs = path_to_geom(gr, path)
    for L, pts in geo:
        for p, q in zip(pts, pts[1:]):
            if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                continue
            gr.occupy(p, q, nid, L)
            items.append(("seg", net, L, (p[0], p[1]), (q[0], q[1])))
    for (vx, vy) in vs:
        gr.mark_via(gr.ix(vx), gr.iy(vy), nid)
        items.append(("via", net, vx, vy))


def try_astar(a, b, net, tlim=12.0, margins=None):
    nid = NET_ID[net]
    las, lbs = (pad_layers(a) or (0,)), (pad_layers(b) or (0,))
    span = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
    mgs = margins or (max(10.0, min(span * 0.6, 25.0)), 45.0)
    sa, sb = gr.open_pad(a, pad_layers(a)), gr.open_pad(b, pad_layers(b))
    try:
        for la in las:
            for lb in lbs:
                for mg in mgs:
                    p = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), nid,
                                 margin_mm=mg, budget=3_000_000,
                                 deadline=time.monotonic() + tlim)
                    if p is not None:
                        return p
    finally:
        gr.restore(sa)
        gr.restore(sb)
    return None


def nb4(a):
    out = np.zeros_like(a)
    out[:, 1:, :] |= a[:, :-1, :]
    out[:, :-1, :] |= a[:, 1:, :]
    out[:, :, 1:] |= a[:, :, :-1]
    out[:, :, :-1] |= a[:, :, 1:]
    return out


def nbL(a):
    """该点在任一信号层可达 → 可经贯穿孔换到其它信号层"""
    m = a[list(SIG)].any(axis=0)
    out = np.zeros_like(a)
    for L in SIG:
        out[L] = m
    return out


def try_wave(a, b, net, margin_mm=None):
    nid = NET_ID[net]
    if margin_mm is None:
        margin_mm = max(40.0, math.hypot(a["x"] - b["x"], a["y"] - b["y"]) * 0.35)
    sa, sb = gr.open_pad(a, pad_layers(a)), gr.open_pad(b, pad_layers(b))
    try:
        m = int(margin_mm / G)
        i0 = max(0, min(gr.ix(a["x"]), gr.ix(b["x"])) - m)
        i1 = min(gr.nx - 1, max(gr.ix(a["x"]), gr.ix(b["x"])) + m)
        j0 = max(0, min(gr.iy(a["y"]), gr.iy(b["y"])) - m)
        j1 = min(gr.ny - 1, max(gr.iy(a["y"]), gr.iy(b["y"])) + m)
        H, W = j1 - j0 + 1, i1 - i0 + 1
        blk = gr.blocked[:, j0:j1 + 1, i0:i1 + 1]
        occ = gr.occ[:, j0:j1 + 1, i0:i1 + 1]
        vb = gr.via_block[:, j0:j1 + 1, i0:i1 + 1]
        usable = (~blk) & ((occ == 0) | (occ == nid))
        for L in range(router.NL):
            if L not in SIG:
                usable[L] = False          # In1 保留给 GND 平面
        vok = (~vb) & usable
        allok = vok[list(SIG)].all(axis=0)   # 贯穿孔：所有信号层都要干净
        vokL = np.zeros_like(vok)
        for L in SIG:
            vokL[L] = allok
        dA = np.full((router.NL, H, W), -1, np.int32)
        dB = np.full((router.NL, H, W), -1, np.int32)
        for p, dist in ((a, dA), (b, dB)):
            jj, ii = gr.iy(p["y"]) - j0, gr.ix(p["x"]) - i0
            if not (0 <= jj < H and 0 <= ii < W):
                return None
            hit = False
            for L in pad_layers(p):
                if L in SIG and usable[L, jj, ii]:
                    dist[L, jj, ii] = 0
                    hit = True
            if not hit:
                return None
        fa, fb = dA == 0, dB == 0
        it = 0
        meet = None
        while True:
            it += 1
            grow = ((nb4(fa) & usable) | (nbL(fa) & vokL)) & (dA < 0)
            if not grow.any():
                return None
            dA[grow] = it
            fa = grow
            grow = ((nb4(fb) & usable) | (nbL(fb) & vokL)) & (dB < 0)
            if not grow.any():
                return None
            dB[grow] = it
            fb = grow
            hit = (dA >= 0) & (dB >= 0)
            if hit.any():
                s = np.where(hit, dA + dB, np.int32(1 << 30))
                L, j, i = np.unravel_index(int(np.argmin(s)), s.shape)
                meet = (int(L), int(j), int(i))
                break

        def back(dist, start):
            pts = [start]
            L, j, i = start
            d = int(dist[L, j, i])
            while d > 0:
                nxt = None
                cands = [(L, j, i - 1), (L, j, i + 1), (L, j - 1, i), (L, j + 1, i)]
                for ol in SIG:
                    if ol != L:
                        cands.append((ol, j, i))
                for nl, nj, ni in cands:
                    if not (0 <= nj < H and 0 <= ni < W):
                        continue
                    if nl != L and not vokL[nl, nj, ni]:
                        continue
                    if dist[nl, nj, ni] == d - 1:
                        nxt = (nl, nj, ni)
                        break
                if nxt is None:
                    return None
                L, j, i = nxt
                d -= 1
                pts.append(nxt)
            return pts

        if meet is None:
            return None
        pa, pb = back(dA, meet), back(dB, meet)
        if pa is None or pb is None:
            return None
        return [(L, j0 + j, i0 + i) for L, j, i in (pa[::-1] + pb[1:])]
    finally:
        gr.restore(sa)
        gr.restore(sb)


def commit_raw(path, net):
    nid = NET_ID[net]
    runs, cur = [], [path[0]]
    for nd in path[1:]:
        if nd[0] != cur[-1][0]:
            runs.append(cur)
            cur = [nd]
        else:
            cur.append(nd)
    runs.append(cur)
    for ri, run in enumerate(runs):
        pts = [(i * G, j * G) for L, j, i in run]
        simp = [pts[0]]
        for k in range(1, len(pts) - 1):
            x0, y0 = simp[-1]
            x1, y1 = pts[k]
            x2, y2 = pts[k + 1]
            if (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1) == 0:
                continue
            simp.append(pts[k])
        if len(pts) > 1:
            simp.append(pts[-1])
        L = run[0][0]
        for p, q in zip(simp, simp[1:]):
            if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                continue
            gr.occupy(p, q, nid, L)
            items.append(("seg", net, L, (p[0], p[1]), (q[0], q[1])))
        if ri < len(runs) - 1:
            vx, vy = pts[-1]
            gr.mark_via(gr.ix(vx), gr.iy(vy), nid)
            items.append(("via", net, vx, vy))


def route(a, b, net):
    p = try_astar(a, b, net)
    if p is not None:
        commit(p, net)
        return "A*"
    p = try_wave(a, b, net)
    if p is not None:
        commit_raw(p, net)
        return "波前"
    return None


def k_chip(kn):
    """K 网 -> (165 编号, 引脚号)，从 PCB 焊盘直接查，不用公式。
    公式 (kn-1)//8+1 是错的：键盘按键是按物理位置分配到最近的一片 165，
    K36 接 U6.5 而不是 U5.4。这类映射只能有一个真相源 —— 板子本身。"""
    net = f"K{kn:02d}"
    for p in g["pads"]:
        if p["net"] == net and p["ref"].startswith("U"):
            return int(p["ref"][1:]), int(p["num"])
    return None, None



def p1_pin(net):
    for n_, (lab_, nt_) in D.P1_PINOUT.items():
        if nt_ == net:
            return str(n_)
    raise KeyError(net)


tasks = []
FIXMODE = len(sys.argv) > 1 and sys.argv[1] == "fix"
if FIXMODE:
    # 增量补齐：只按「真实仍断开的焊盘组」连最短边（就近合组 MST）
    import conncheck as CC
    miss = CC.analyze(PCB)
    miss.pop("GND", None)
    for net, groups in miss.items():
        if net in ("VCC", "GND"):
            continue          # VCC 由 In1 平面 + 盘中孔解决，GND 由铺铜
        gs = []
        for gp in groups:
            ps = [PADIDX[(q["ref"], q["num"])] for q in gp
                  if (q["ref"], q["num"]) in PADIDX]
            if ps:
                gs.append(ps)
        # 单焊盘孤岛：原地打一个过孔（同网，天然合法），
        # 把这块铜接到空着的 In2 层，绕开 F.Cu 的死角
        if net in NET_ID:
            for gp in gs:
                if len(gp) == 1:
                    q = gp[0]
                    lays = pad_layers(q)
                    if lays and not q.get("drill", 0) and len(lays) == 1:
                        i, j = gr.ix(q["x"]), gr.iy(q["y"])
                        gr.mark_via(i, j, NET_ID[net])
                        gr.via_block[:, j, i] = False   # 自己焊盘挡的，放开
                        items.append(("via", net, q["x"], q["y"]))
        grp = [list(x) for x in gs]
        while len(grp) > 1:
            best = None
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    for aa in grp[i]:
                        for bb in grp[j]:
                            d = (aa["x"] - bb["x"]) ** 2 + (aa["y"] - bb["y"]) ** 2
                            if best is None or d < best[0]:
                                best = (d, i, j, aa, bb)
            tasks.append((net, best[3], best[4], None, "fix"))
            grp[best[1]] = grp[best[1]] + grp[best[2]]
            del grp[best[2]]
    print(f"待补 {len(tasks)} 条", flush=True)
# 1) 总线：10 片 165 的 CLK / SH_LD 必须先占 1、2 脚
if not FIXMODE:
    for net, ipin in (("CLK", "2"), ("SH_LD", "1")):
        prev = PADIDX.get(("J_P1", p1_pin(net)))
        for i in range(D.CHIP_COUNT):
            cur = PADIDX.get((f"U{i+1}", ipin))
            if prev and cur:
                tasks.append((net, prev, cur, None, "bus"))
            prev = cur
# 2) IC -> 上拉电阻（0.8~3mm，别无替代路径）
for kn in (() if FIXMODE else range(1, D.CHIP_COUNT * 8 + 1)):
    u, pin = k_chip(kn)
    if u is None:
        continue
    ic = PADIDX.get((f"U{u}", str(pin)))
    rp = PADIDX.get((f"R{kn:02d}", "2"))
    if ic and rp:
        tasks.append((f"K{kn:02d}", ic, rp, None, "r"))
# 3) 按键长线（长的先布）
kt = []
for kn in (() if FIXMODE else range(1, D.CHIP_COUNT * 8 + 1)):
    u, pin = k_chip(kn)
    if u is None:
        continue
    sw = PADIDX.get((f"SW{kn:02d}", "1"))
    ic = PADIDX.get((f"U{u}", str(pin)))
    if sw and ic:
        kt.append((f"K{kn:02d}", sw, ic, None, "k"))
kt.sort(key=lambda t: -math.hypot(t[1]["x"] - t[2]["x"], t[1]["y"] - t[2]["y"]))
tasks += kt

only = None if FIXMODE else (sys.argv[1].split(",") if len(sys.argv) > 1 else None)
if only:
    tasks = [t for t in tasks if t[0] in only]
print(f"待布 {len(tasks)} 条", flush=True)

fails = []
for idx, (net, a, b, rp, kind) in enumerate(tasks):
    t0 = time.monotonic()
    how = route(a, b, net)
    if how is None:
        fails.append((net, kind))
        print(f"  [{idx+1}/{len(tasks)}] 失败 {net} {a['ref']}.{a['num']}->"
              f"{b['ref']}.{b['num']} ({time.monotonic()-t0:.0f}s)", flush=True)
        dump()
        continue
    print(f"  [{idx+1}/{len(tasks)}] {net} {a['ref']}.{a['num']}->{b['ref']}.{b['num']} "
          f"{how} ({time.monotonic()-t0:.0f}s)", flush=True)
    dump()

print(f"\n完成 {len(tasks)-len(fails)}/{len(tasks)}  段数 {sum(1 for i in items if i[0]=='seg')} "
      f"孔 {sum(1 for i in items if i[0]=='via')}", flush=True)
for f in fails:
    print("  [失败]", *f, flush=True)
