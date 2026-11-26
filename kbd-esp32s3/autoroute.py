#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 kbd-esp32s3.kicad_pcb 做信号布线

用法: python autoroute.py [--limit N]

2026-11-24 重写：障碍按真实几何栅格化、Edge.Cuts 进入禁布区、
占用带网络号（同网可贴合、异网严禁）、进入焊盘只解锁自身外扩区。
以 kicad-cli DRC 为准（见 run_drc.py），不再信任自研间距校验。
"""
import math
import os
import sys
import time
import uuid

import pcbkit as K
import board_geom as BG
from router import (Grid, path_to_geom, GRID, EDGE_INFLATE, HOLE_INFLATE,
                    TRACE_W, NL)

LAYER_NAME = {0: "F.Cu", 1: "In1.Cu", 2: "In2.Cu", 3: "B.Cu"}
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")


def dist2(a, b):
    return (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2


LMAP = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}


def pad_layers(p):
    """焊盘铜层 -> 层索引元组（4 层：0=F 1=In1 2=In2 3=B）"""
    if any("*.Cu" in l for l in p["layers"]):
        return (0, 1, 2, 3)                      # 通孔焊盘贯穿所有铜层
    lays = BG.copper_layers(p)
    return tuple(sorted(LMAP[l] for l in lays if l in LMAP))


def _cluster(items, gap=1.0):
    """把同一 (ref,num,net) 的多个几何按外框相近程度分组（<1mm 才算同一焊盘）"""
    n = len(items)
    if n <= 1:
        return [items]
    par = list(range(n))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    box = []
    for p, _ in items:
        box.append((p["x"] - p["w"] / 2 - gap, p["y"] - p["h"] / 2 - gap,
                    p["x"] + p["w"] / 2 + gap, p["y"] + p["h"] / 2 + gap))
    for i in range(n):
        for j in range(i + 1, n):
            a, b = box[i], box[j]
            if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                ra, rb = find(i), find(j)
                if ra != rb:
                    par[ra] = rb
    out = {}
    for i in range(n):
        out.setdefault(find(i), []).append(items[i])
    return list(out.values())


def build_grid(g):
    gr = Grid(g["outline"][2], g["outline"][3])
    gr.margin(EDGE_INFLATE)                       # 板框
    for s in g["slots"]:                          # 开槽
        gr.rect(s[0], s[1], s[2], s[3], layers=tuple(range(NL)), inflate=EDGE_INFLATE)
    groups = {}
    for p in g["pads"]:
        lays = pad_layers(p)
        if not lays and p.get("drill", 0) > 0:    # NPTH 安装孔 / 定位柱孔
            gr.disc(p["x"], p["y"], p["drill"] / 2.0, layers=tuple(range(NL)),
                    inflate=HOLE_INFLATE, count=True)   # 计入 shape_cnt，防止别的焊盘解锁到这
            continue
        if not lays:
            continue
        # 同一焊盘号的多重几何必须合并计数，否则 open_pad 永远解不开
        groups.setdefault((p["ref"], p["num"], p["net"]), []).append((p, lays))
    for base, items in groups.items():
        for ci, ps in enumerate(_cluster(items)):
            gr.add_pad_group(ps, ("G", base, ci))
    gr.build_via_mask()
    return gr


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    g = BG.load(PCB)
    gr = build_grid(g)

    pads_by_net = {}
    for p in g["pads"]:
        if p["net"]:
            pads_by_net.setdefault(p["net"], []).append(p)

    nets = sorted(pads_by_net)
    NET_ID = {n: i + 1 for i, n in enumerate(nets)}

    def pick_anchor(net, ref=None, num=None):
        cand = [p for p in pads_by_net.get(net, []) if p["ref"].startswith("SW")]
        cand = [p for p in pads_by_net.get(net, []) if p["ref"] == ref] if ref else cand
        if num is not None:
            cand = [p for p in cand if p["num"] == str(num)]
        if not cand:
            return None
        th = [p for p in cand if p.get("drill", 0) > 0]
        return (th or cand)[0]

    import kbd_design as D

    def pad_of(ref, num):
        for p in g["pads"]:
            if p["ref"] == ref and p["num"] == str(num):
                return p
        return None

    # ---------------- 待布网络 ----------------
    tasks = []
    for i in range(D.CHIP_COUNT):
        for pin, knum in D.CHIP_INPUTS[i]:
            if not knum:
                continue
            net = D.key_net(knum)
            sw = pick_anchor(net, ref=f"SW{knum:02d}", num="1")
            rp = pick_anchor(net, ref=f"R{knum:02d}", num="2")
            ic = pick_anchor(net, ref=f"U{i+1}", num=pin)
            if not (sw and ic and rp):
                print(f"  [跳过] {net}: 缺焊盘 sw={bool(sw)} ic={bool(ic)} r={bool(rp)}")
                continue
            tasks.append((net, sw, ic))
            tasks.append((net, ic, rp))

    # J_P1 引脚号一律从设计引脚表派生，杜绝与 22 针映射脱节
    def p1_pin(net):
        for n_, (lab_, nt_) in D.P1_PINOUT.items():
            if nt_ == net:
                return str(n_)
        raise KeyError(f"P1_PINOUT 里没有 {net}")

    for net, ipin in (("CLK", "2"), ("SH_LD", "1")):
        prev = pad_of("J_P1", p1_pin(net))
        for i in range(D.CHIP_COUNT):
            cur = pad_of(f"U{i+1}", ipin)
            if prev and cur:
                tasks.append((net, prev, cur))
            prev = cur
    for i in range(D.CHIP_COUNT - 1):
        tasks.append((f"CHAIN_{i+1}", pad_of(f"U{i+1}", "9"), pad_of(f"U{i+2}", "10")))
    tasks.append(("CHAIN_10", pad_of(f"U{D.CHIP_COUNT}", "9"), pad_of("J_P1", p1_pin("CHAIN_10"))))
    for net, num in (("ENC_A", "A"), ("ENC_B", "B"), ("ENC_SW", "S1")):
        tasks.append((net, pad_of("ENC1", num), pad_of("J_P1", p1_pin(net))))

    tasks = [t for t in tasks if t[1] and t[2]]
    # 先短后长：短网络快速占位，长网络留给大预算重试
    tasks.sort(key=lambda t: dist2(t[1], t[2]))
    print(f"待布 {len(tasks)} 条（含同网络分段）")
    if limit:
        tasks = tasks[:limit]

    traces, vias = [], []

    def commit(path, net):
        """把路径写入占位图与走线表"""
        nid = NET_ID[net]
        geo, vs = path_to_geom(gr, path)
        for L, pts in geo:
            for p, q in zip(pts, pts[1:]):
                if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                    continue
                gr.occupy(p, q, nid, L)
                traces.append((net, LAYER_NAME[L], p, q))
        for (vx, vy) in vs:
            gr.mark_via(gr.ix(vx), gr.iy(vy), nid)
            vias.append((net, vx, vy))

    # ---- 灯带链（确定性，先占位）----
    for i in range(D.LED_COUNT - 1):
        a, b = pad_of(f"L{i+1:02d}", "2"), pad_of(f"L{i+2:02d}", "4")
        if not a or not b:
            continue
        net = D.led_net_out(i)
        yb = D.LED_Y + D.LED_PAD_DY + 1.0
        pts = [(a["x"], a["y"]), (a["x"] + D.LED_PAD_DX + 0.6, a["y"]),
               (a["x"] + D.LED_PAD_DX + 0.6, yb), (b["x"], yb), (b["x"], b["y"])]
        nid = NET_ID.setdefault(net, len(NET_ID) + 1)
        for p, q in zip(pts, pts[1:]):
            gr.occupy(p, q, nid, 1)
            traces.append((net, "B.Cu", p, q))

    ok, fail = 0, []
    for idx, (net, a, b) in enumerate(tasks):
        if a["net"] != net or b["net"] != net:
            print(f"  [跳过] {net}: 端点焊盘网络不符 "
                  f"({a['ref']}.{a['num']}={a['net']}, {b['ref']}.{b['num']}={b['net']})")
            fail.append((net, a, b))
            continue
        nid = NET_ID[net]
        la, lb = pad_layers(a), pad_layers(b)
        la = la[0] if la else 0
        lb = lb[0] if lb else 0
        sa = gr.open_pad(a, pad_layers(a))
        sb = gr.open_pad(b, pad_layers(b))
        span = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        mg = max(12.0, span * 0.55)
        t_end = time.monotonic() + 10.0          # 单条上限，防止一条卡死整轮
        path = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), nid,
                        margin_mm=mg, deadline=t_end)
        if path is None:
            path = gr.astar((a["x"], a["y"], 1 - la), (b["x"], b["y"], 1 - lb), nid,
                            margin_mm=mg, deadline=t_end)
        if path is None:
            path = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), nid,
                            margin_mm=max(mg, 40.0), budget=400_000, deadline=t_end)
        gr.restore(sa)
        gr.restore(sb)
        if path is None:
            fail.append((net, a, b))
            continue
        commit(path, net)
        ok += 1
        if (idx + 1) % 20 == 0:
            print(f"  ... {idx+1}/{len(tasks)}  成功 {ok} 失败 {len(fail)}")

    # ---------------- 失败网络重试：长网络优先，放宽预算 ----------------
    if fail:
        fail.sort(key=lambda t: -dist2(t[1], t[2]))
        print(f"\n重试 {len(fail)} 条失败网络（长网络优先，60s/条）")
        still = []
        for net, a, b in fail:
            nid = NET_ID[net]
            la, lb = pad_layers(a), pad_layers(b)
            la = la[0] if la else 0
            lb = lb[0] if lb else 0
            sa, sb = gr.open_pad(a, pad_layers(a)), gr.open_pad(b, pad_layers(b))
            span = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            t_end = time.monotonic() + 60.0
            path = None
            for mg in (max(20.0, span * 1.2), max(60.0, span * 2.0)):
                path = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), nid,
                                margin_mm=mg, budget=2_000_000, deadline=t_end)
                if path is None:
                    path = gr.astar((a["x"], a["y"], 1 - la), (b["x"], b["y"], 1 - lb), nid,
                                    margin_mm=mg, budget=2_000_000, deadline=t_end)
                if path is not None:
                    break
            gr.restore(sa)
            gr.restore(sb)
            if path is None:
                still.append((net, a, b))
                continue
            commit(path, net)
            ok += 1
            print(f"  [重试成功] {net} {a['ref']}.{a['num']}->{b['ref']}.{b['num']}")
        fail = still

    # ---------------- 电源网络：MST ----------------
    def mst_route(net):
        pts = list(pads_by_net.get(net, []))
        if len(pts) < 2:
            return
        nid = NET_ID[net]
        rest = list(range(1, len(pts)))
        done, edges = [0], []
        while rest:
            best = None
            for i in done:
                for j in rest:
                    d = dist2(pts[i], pts[j])
                    if best is None or d < best[0]:
                        best = (d, i, j)
            edges.append((pts[best[1]], pts[best[2]]))
            done.append(best[2])
            rest.remove(best[2])
        good = 0
        for a, b in edges:
            la, lb = pad_layers(a), pad_layers(b)
            la = la[0] if la else 0
            lb = lb[0] if lb else 0
            sa, sb = gr.open_pad(a, pad_layers(a)), gr.open_pad(b, pad_layers(b))
            mg = max(10.0, math.hypot(a["x"] - b["x"], a["y"] - b["y"]) * 0.55)
            t_end = time.monotonic() + 6.0
            pa = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), nid,
                          margin_mm=mg, deadline=t_end)
            if pa is None:
                pa = gr.astar((a["x"], a["y"], 1 - la), (b["x"], b["y"], 1 - lb), nid,
                              margin_mm=max(mg, 40.0), budget=400_000, deadline=t_end)
            gr.restore(sa)
            gr.restore(sb)
            if pa is None:
                continue
            commit(pa, net)
            good += 1
        print(f"  [电源] {net}: {good}/{len(edges)} 段")

    # GND 不走 MST——改用 B.Cu 整面铺铜（zones_gnd.py 用 pcbnew 生成并填充），
    # 290 段 MST 走线既占通道又没必要。V5/VCC 仍走 MST。
    for pnet in ("VCC", "V5"):
        mst_route(pnet)

    print(f"\n布线完成 {ok}/{len(tasks)}，失败 {len(fail)}")
    for net, a, b in fail[:12]:
        print(f"  [失败] {net}: {a['ref']}.{a['num']} -> {b['ref']}.{b['num']}")

    # ---------------- 写回 ----------------
    root = K.parse(open(PCB, encoding="utf-8").read())[0]
    netid = {str(n[2]): str(n[1]) for n in K.find_all(root, "net")}

    for net, layer, p, q in traces:
        if net not in netid:
            continue
        root.append(["segment",
                     ["start", f"{p[0]:.3f}", f"{p[1]:.3f}"],
                     ["end", f"{q[0]:.3f}", f"{q[1]:.3f}"],
                     ["width", f"{TRACE_W:g}"],
                     ["layer", K.Str(layer)],
                     ["net", netid[net]],
                     ["uuid", K.Str(str(uuid.uuid4()))]])
    for net, vx, vy in vias:
        if net not in netid:
            continue
        root.append(["via", ["at", f"{vx:.3f}", f"{vy:.3f}"],
                     ["size", "0.6"], ["drill", "0.3"],
                     ["layers", K.Str("F.Cu"), K.Str("B.Cu")],
                     ["net", netid[net]],
                     ["uuid", K.Str(str(uuid.uuid4()))]])

    open(PCB, "w", encoding="utf-8").write(K.dumps(root, pretty=True) + "\n")
    print(f"已写入: {len(traces)} 段走线, {len(vias)} 个过孔")


if __name__ == "__main__":
    main()
