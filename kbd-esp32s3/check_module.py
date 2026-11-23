#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主控模块座与 MX 轴座的规格校对（实测 .kicad_pcb vs 官方图纸标注）

官方数据来源：
  ESP32-S3-DEV-KIT-N8R8_20260110.pdf / .dxf（机械图，Waveshare 官方）
  ESP32-S3-DEV-KIT-N8R8-schematic.pdf（原理图，P1/P2 标注 "Header 22"）
  Cherry MX 轴规格（中心柱 Ø4、定位柱 ±5.08、两针脚 -3.81/-2.54 与 +2.54/-5.08）
"""
import sys

import kbd_design as D
import board_geom as G

TOL = 0.02


def near(a, b, tol=TOL):
    return abs(a - b) <= tol


def main(path="kbd-esp32s3.kicad_pcb"):
    g = G.load(path)
    rows = []

    def chk(name, got, want, unit="mm", tol=TOL):
        if isinstance(want, (int, float)):
            ok = near(float(got), float(want), tol)
            rows.append((ok, name, f"{got:.3f} {unit}", f"{want:.2f} {unit}"))
        else:
            ok = (got == want)
            rows.append((ok, name, str(got), str(want)))

    def pads(ref):
        return sorted([p for p in g["pads"] if p["ref"] == ref], key=lambda p: p["x"])

    p1, p2 = pads("J_P1"), pads("J_P2")
    chk("P1 焊盘数", len(p1), D.MOD_PINS_PER_ROW, "个")
    chk("P2 焊盘数", len(p2), D.MOD_PINS_PER_ROW, "个")

    xs = sorted(p["x"] for p in p1)
    pitches = [b - a for a, b in zip(xs, xs[1:])]
    chk("P1 针距 min", min(pitches), D.MOD_PITCH)
    chk("P1 针距 max", max(pitches), D.MOD_PITCH)
    chk("P1 首末跨距", max(xs) - min(xs), (D.MOD_PINS_PER_ROW - 1) * D.MOD_PITCH)

    chk("两排中心距", D.P2_Y - D.P1_Y, D.MOD_ROW_SPACING)
    chk("P1 到模块上缘", D.P1_Y - D.MOD_Y0, D.MOD_EDGE_TO_PIN)
    chk("P1 首针(USB端)到模块左缘", min(xs) - D.MOD_X0, D.MOD_END_MARGIN_USB)
    chk("P1 末针(天线端)到模块右缘", D.MOD_X1 - max(xs), D.MOD_END_MARGIN_ANT)
    chk("模块长度", D.MOD_X1 - D.MOD_X0, D.MOD_LEN)
    chk("模块宽度", D.MOD_Y1 - D.MOD_Y0, D.MOD_WID)

    # 焊盘尺寸（2.54 排针标准：Ø1.7 盘 / Ø1.0 孔）
    chk("焊盘外径 min", min(p["w"] for p in p1), 1.70)
    chk("钻孔 min", min(p["drill"] for p in p1), 1.00)

    # P1/P2 是否共线对齐
    chk("P1/P2 X 对齐偏差", max(abs(a["x"] - b["x"]) for a, b in zip(p1, p2)), 0.0)

    # 模块与键区净空
    top_key = min(k["cy"] for k in D.KEYS) - D.U / 2.0
    rows.append((top_key - D.MOD_Y1 >= 2.0, "模块下缘→首行键中心净空",
                 f"{top_key - D.MOD_Y1:.2f} mm", "≥ 2.00 mm"))

    # MX 轴座：相对封装原点的关键几何
    sw = next(f for f in g["fps"] if f["ref"] == "SW01")
    sp = [p for p in g["pads"] if p["ref"] == "SW01"]
    loc = [(p["num"], p["x"] - sw["x"], p["y"] - sw["y"], p["w"], p["h"], p["drill"]) for p in sp]
    center = [p for p in loc if abs(p[1]) < 0.01 and abs(p[2]) < 0.01]
    pegs = [p for p in loc if near(abs(p[1]), 5.08) and abs(p[2]) < 0.01]
    pin1_th = [p for p in loc if p[0] == "1" and p[5] > 1]
    pin2_th = [p for p in loc if p[0] == "2" and p[5] > 1]
    rows.append((bool(center) and near(center[0][3], 4.0), "MX 中心柱孔 Ø",
                 f"{center[0][3]:.2f} mm" if center else "缺失", "4.00 mm"))
    rows.append((len(pegs) == 2, "MX 定位柱孔 ±5.08", f"{len(pegs)} 个", "2 个"))
    if pin1_th and pin2_th:
        a, b = pin1_th[0], pin2_th[0]
        dx, dy = abs(a[1] - b[1]), abs(a[2] - b[2])
        # MX 规格：两针脚在 X 相差 6.35（=2.54+3.81），在 Y 相差 2.54
        rows.append((near(dx, 6.35) and near(dy, 2.54), "MX 两针脚 ΔX / ΔY",
                     f"{dx:.3f} / {dy:.3f} mm", "6.35 / 2.54 mm"))
        # 针脚是否落在标准四点之一（整体 180° 旋转后同样合格）
        std = {(-3.81, -2.54), (2.54, -5.08)}
        got = {(round(a[1], 2), round(a[2], 2)), (round(b[1], 2), round(b[2], 2))}
        rot = {(-round(x, 2), -round(y, 2)) for x, y in got}
        rows.append((got == std or rot == std, "MX 针脚符合标准位置",
                     "180° 旋转位" if rot == std else ("标准位" if got == std else "偏离"),
                     "标准位/180° 位"))
        rows.append((near(a[3], 3.6) and near(a[5], 3.0), "MX 针脚焊盘/孔径",
                     f"{a[3]:.1f}/{a[5]:.1f} mm", "3.6/3.0 mm"))

    w = max(len(r[1]) for r in rows) + 2
    print(f"规格校对：{path}\n" + "=" * (w + 34))
    bad = 0
    for ok, name, got, want in rows:
        if ok is None:
            continue
        bad += 0 if ok else 1
        print(f"  [{'OK' if ok else 'FAIL'}] {name:<{w}} 实测 {got:>12}   规格 {want:>12}")
    print("=" * (w + 34))
    print(f"  {len([r for r in rows if r[0] is not None]) - bad} 项通过，{bad} 项不符")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
