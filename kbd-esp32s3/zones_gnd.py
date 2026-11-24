#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给已布线的板子加 GND 整面铺铜（B.Cu + F.Cu），用 KiCad 的 ZONE_FILLER 填充。

必须用 KiCad 自带的 python 运行：
    KiCad/bin/python.exe zones_gnd.py [板文件]

铺铜放在布线之后：填充器会自动对所有异网走线/焊盘保持间距。
"""
import sys

import pcbnew

path = sys.argv[1] if len(sys.argv) > 1 else "kbd-esp32s3.kicad_pcb"

b = pcbnew.LoadBoard(path)
if b is None:
    raise SystemExit(f"加载失败: {path}")

bb = b.GetBoardEdgesBoundingBox()
inset = pcbnew.FromMM(0.8)
x0, y0 = bb.GetLeft() + inset, bb.GetTop() + inset
x1, y1 = bb.GetRight() - inset, bb.GetBottom() - inset

net_gnd = b.FindNet("GND")
if net_gnd is None:
    raise SystemExit("找不到 GND 网络")

zones = []
for layer, name in ((pcbnew.B_Cu, "GND_B"), (pcbnew.F_Cu, "GND_F")):
    z = pcbnew.ZONE(b)
    z.SetNetCode(net_gnd.GetNetCode())
    z.SetLayer(layer)
    z.SetLocalClearance(pcbnew.FromMM(0.30))
    z.SetMinThickness(pcbnew.FromMM(0.25))
    o = z.Outline()
    idx = o.NewOutline()
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(px, py, idx)
    b.Add(z)
    zones.append(z)
    print(f"添加 GND 区域 ({'B.Cu' if layer == pcbnew.B_Cu else 'F.Cu'})")

filler = pcbnew.ZONE_FILLER(b)
ok = filler.Fill(zones)
print("填充:", "成功" if ok else "返回 False")

b.Save(path)

# 统计填充面积
for z in zones:
    area_mm2 = z.GetFilledArea() / 1e12
    print(f"  {'B.Cu' if z.GetLayer() == pcbnew.B_Cu else 'F.Cu'}: 填充 {area_mm2:.0f} mm2")
print("已保存", path)
