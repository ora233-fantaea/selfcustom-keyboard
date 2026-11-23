#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 kbd-esp32s3.kicad_pcb 做信号布线（电源走铺铜，见 add_zones.py）

用法: python autoroute.py [--limit N]
"""
import math
import os
import time
import sys
import uuid

import numpy as np
import pcbkit as K
import board_geom as BG
from router import Grid, path_to_geom, GRID

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")


def dist2(a, b):
    return (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2


def build_grid(g):
    gr = Grid(g["outline"][2], g["outline"][3])
    gr.margin(0.45)
    for s in g["slots"]:
        gr.rect(s[0], s[1], s[2], s[3], layers=(0, 1), pad=0.35)
    for p in g["pads"]:
        lays = BG.copper_layers(p)
        idx = tuple(0 if l == "F.Cu" else 1 for l in lays)
        if p["drill"] > 0:
            gr.disc(p["x"], p["y"], p["drill"] / 2.0 + 0.35, layers=(0, 1))
        if idx:
            gr.rect(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2,
                    p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, layers=idx, pad=0.30)
    gr.occ = np.zeros_like(gr.blocked)
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

    def pick_anchor(net, ref=None, num=None, prefer_drill=True):
        cand = [p for p in pads_by_net.get(net, []) if p["ref"].startswith("SW")]
        if ref:
            cand = [p for p in pads_by_net.get(net, []) if p["ref"] == ref]
        if num is not None:
            cand = [p for p in cand if p["num"] == str(num)]
        if not cand:
            return None
        th = [p for p in cand if p["drill"] > 0] if prefer_drill else []
        return (th or cand)[0]

    # ---------------- 生成待布网络 ----------------
    import kbd_design as D
    tasks = []          # (netname, padA, padB)
    for i in range(D.CHIP_COUNT):
        for pin, knum in D.CHIP_INPUTS[i]:
            if not knum:
                continue
            net = D.key_net(knum)
            sw = pick_anchor(net, ref=f"SW{knum:02d}", num="1")
            rp = pick_anchor(net, ref=f"R{knum:02d}", num="2", prefer_drill=False)
            ic = pick_anchor(net, ref=f"U{i+1}", num=pin, prefer_drill=False)
            if not (sw and ic and rp):
                print(f"  [跳过] {net}: 缺焊盘 sw={bool(sw)} ic={bool(ic)} r={bool(rp)}")
                continue
            tasks.append((net, sw, ic))
            tasks.append((net, ic, rp))

    def pad_of(ref, num):
        for p in g["pads"]:
            if p["ref"] == ref and p["num"] == str(num):
                return p
        return None

    # CLK / SH_LD 链
    for net, ipin in (("CLK", "2"), ("SH_LD", "1")):
        prev = pad_of("J_P1", "3" if net == "CLK" else "4")
        for i in range(D.CHIP_COUNT):
            cur = pad_of(f"U{i+1}", ipin)
            if prev and cur:
                tasks.append((net, prev, cur))
            prev = cur
    # 级联链
    for i in range(D.CHIP_COUNT - 1):
        net = f"CHAIN_{i+1}"
        tasks.append((net, pad_of(f"U{i+1}", "9"), pad_of(f"U{i+2}", "10")))
    tasks.append(("CHAIN_10", pad_of(f"U{D.CHIP_COUNT}", "9"), pad_of("J_P1", "5")))
    # 编码器
    for net, num in (("ENC_A", "A"), ("ENC_B", "B"), ("ENC_SW", "S1")):
        tasks.append((net, pad_of("ENC1", num), pad_of("J_P1", {"ENC_A": "6", "ENC_B": "7", "ENC_SW": "8"}[net])))

    # ---- 灯带链（确定性） ----
    led_extra = []
    for i in range(D.LED_COUNT - 1):
        a = pad_of(f"L{i+1:02d}", "2")
        b = pad_of(f"L{i+2:02d}", "4")
        if not a or not b:
            continue
        yb = D.LED_Y + 1.75
        pts = [(a["x"], a["y"]), (a["x"] + 1.75, a["y"]),
               (a["x"] + 1.75, yb), (b["x"], yb), (b["x"], b["y"])]
        for p, q in zip(pts, pts[1:]):
            led_extra.append((D.led_net_out(i), "B.Cu", p, q))
            for t_ in np.linspace(0, 1, max(2, int(math.hypot(q[0]-p[0], q[1]-p[1]) / 0.2))):
                xx = p[0] + (q[0] - p[0]) * t_
                yy = p[1] + (q[1] - p[1]) * t_
                gr.occ[1, gr.iy(yy), gr.ix(xx)] = True

    tasks = [t for t in tasks if t[1] and t[2]]
    tasks.sort(key=lambda t: dist2(t[1], t[2]))

    print(f"待布 {len(tasks)} 条（含同网络分段）")
    if limit:
        tasks = tasks[:limit]

    def soft_open(pad):
        saved = []
        x1, y1 = pad["x"] - pad["w"] / 2 - 0.8, pad["y"] - pad["h"] / 2 - 0.8
        x2, y2 = pad["x"] + pad["w"] / 2 + 0.8, pad["y"] + pad["h"] / 2 + 0.8
        for L in (0, 1):
            i0, i1 = max(0, gr.ix(x1)), min(gr.nx - 1, gr.ix(x2))
            j0, j1 = max(0, gr.iy(y1)), min(gr.ny - 1, gr.iy(y2))
            sub = gr.blocked[L, j0:j1 + 1, i0:i1 + 1].copy()
            saved.append((L, i0, i1, j0, j1, sub))
            gr.blocked[L, j0:j1 + 1, i0:i1 + 1] = False
        return saved

    def soft_restore(saved):
        for L, i0, i1, j0, j1, sub in saved:
            gr.blocked[L, j0:j1 + 1, i0:i1 + 1] = sub

    traces, vias = list(led_extra), []
    ok, fail = 0, []
    for idx, (net, a, b) in enumerate(tasks):
        la = 0 if "F.Cu" in BG.copper_layers(a) and "B.Cu" not in BG.copper_layers(a) else (
            1 if "B.Cu" in BG.copper_layers(a) and "F.Cu" not in BG.copper_layers(a) else 0)
        lb = 0 if "F.Cu" in BG.copper_layers(b) and "B.Cu" not in BG.copper_layers(b) else (
            1 if "B.Cu" in BG.copper_layers(b) and "F.Cu" not in BG.copper_layers(b) else 0)
        t0 = time.time()
        print(f"  #{idx:03d} {net} {a['ref']}.{a['num']}->{b['ref']}.{b['num']} "
              f"d={math.hypot(a['x']-b['x'], a['y']-b['y']):.1f}")
        sa = soft_open(a)
        sb = soft_open(b)
        span = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        mg = max(12.0, span * 0.75)
        path = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), occupied=gr.occ, margin_mm=mg)
        if path is None:
            path = gr.astar((a["x"], a["y"], 1 - la), (b["x"], b["y"], 1 - lb),
                            occupied=gr.occ, margin_mm=mg)
        if path is None:
            path = gr.astar((a["x"], a["y"], la), (b["x"], b["y"], lb), occupied=gr.occ,
                            margin_mm=max(mg, 60.0), budget=300_000)
        soft_restore(sa)
        soft_restore(sb)
        if path is None:
            fail.append((net, a, b))
            continue
        # 按层写占用
        for (x, y, L) in path:
            i0, i1 = max(0, x - 1), min(gr.nx - 1, x + 1)
            j0, j1 = max(0, y - 1), min(gr.ny - 1, y + 1)
            gr.occ[L, j0:j1 + 1, i0:i1 + 1] = True
        geo, vs = path_to_geom(gr, path)
        for L, pts in geo:
            for p, q in zip(pts, pts[1:]):
                if abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                    continue
                traces.append((net, L, p, q))
        for (vx, vy) in vs:
            vias.append((net, vx, vy))
            gr.mark_via(gr.ix(vx), gr.iy(vy))
        ok += 1
        if t0 and time.time() - t0 > 2.0:
            print(f"  [慢] #{idx} {net} {a['ref']}.{a['num']}->{b['ref']}.{b['num']} {time.time()-t0:.1f}s")
        if (idx + 1) % 20 == 0:
            print(f"  ... {idx+1}/{len(tasks)}  成功 {ok} 失败 {len(fail)}")

    # ---------------- 电源网络：MST 连接 ----------------
    def mst_route(net, budget_hint=1):
        pts = [p for p in pads_by_net.get(net, []) if p["net"] == net]
        if len(pts) < 2:
            return 0, 0
        unvisited = list(range(1, len(pts)))
        done = [0]
        edges = []
        while unvisited:
            best = None
            for i in done:
                for j in unvisited:
                    d = dist2(pts[i], pts[j])
                    if best is None or d < best[0]:
                        best = (d, i, j)
            edges.append((pts[best[1]], pts[best[2]]))
            done.append(best[2])
            unvisited.remove(best[2])
        good = 0
        for a, b in edges:
            sa = soft_open(a); sb = soft_open(b)
            pa = gr.astar((a["x"], a["y"], 0), (b["x"], b["y"], 0), occupied=gr.occ,
                          margin_mm=max(10.0, math.hypot(a["x"]-b["x"], a["y"]-b["y"]) * 0.8),
                          budget=120_000)
            if pa is None:
                pa = gr.astar((a["x"], a["y"], 1), (b["x"], b["y"], 1), occupied=gr.occ,
                              margin_mm=max(10.0, math.hypot(a["x"]-b["x"], a["y"]-b["y"]) * 0.8),
                              budget=120_000)
            soft_restore(sa); soft_restore(sb)
            if pa is None:
                continue
            for (x, y, L) in pa:
                gr.occ[L, max(0, y-1):y+2, max(0, x-1):x+2] = True
            geo, vs = path_to_geom(gr, pa)
            for L, pl in geo:
                for p, q in zip(pl, pl[1:]):
                    traces.append((net, L, p, q))
            for (vx, vy) in vs:
                vias.append((net, vx, vy))
                gr.mark_via(gr.ix(vx), gr.iy(vy))
            good += 1
        print(f"  [电源] {net}: {good}/{len(edges)} 段")
        return good, len(edges)

    for pnet in ("GND", "VCC", "V5"):
        mst_route(pnet)

    print(f"\n布线完成 {ok}/{len(tasks)}，失败 {len(fail)}")
    for net, a, b in fail[:15]:
        print(f"  [失败] {net}: {a['ref']}.{a['num']}({a['x']:.1f},{a['y']:.1f}) -> "
              f"{b['ref']}.{b['num']}({b['x']:.1f},{b['y']:.1f})")

    # ---------------- 写回 ----------------
    root = K.parse(open(PCB, encoding="utf-8").read())[0]
    netid = {}
    for n in K.find_all(root, "net"):
        netid[str(n[2])] = str(n[1])

    for net, layer, p, q in traces:
        root.append(["segment",
                     ["start", f"{p[0]:.3f}", f"{p[1]:.3f}"],
                     ["end", f"{q[0]:.3f}", f"{q[1]:.3f}"],
                     ["width", "0.2"],
                     ["layer", K.Str(layer)],
                     ["net", netid[net]],
                     ["uuid", K.Str(str(uuid.uuid4()))]])
    for net, vx, vy in vias:
        root.append(["via", ["at", f"{vx:.3f}", f"{vy:.3f}"],
                     ["size", "0.6"], ["drill", "0.3"],
                     ["layers", K.Str("F.Cu"), K.Str("B.Cu")],
                     ["net", netid[net]],
                     ["uuid", K.Str(str(uuid.uuid4()))]])

    open(PCB, "w", encoding="utf-8").write(K.dumps(root, pretty=True) + "\n")
    print(f"已写入: {len(traces)} 段走线, {len(vias)} 个过孔")


if __name__ == "__main__":
    main()
