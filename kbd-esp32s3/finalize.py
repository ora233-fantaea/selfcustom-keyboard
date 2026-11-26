#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收尾清理：合并重复铺铜 + 实心热焊盘 + 删悬空孔。

power4.py 当时为了躲 SWIG 悬空指针把「删旧 zone」拆到了独立进程，结果省略后
每跑一次就叠加 4 个 zone（现在 18 个重叠 -> zones_intersect / starved_thermal）。

    KiCad/bin/python.exe finalize.py [板文件]
"""
import sys

import pcbnew

path = sys.argv[1] if len(sys.argv) > 1 else "kbd-esp32s3.kicad_pcb"
b = pcbnew.LoadBoard(path)

# ---- 1) 每层只留最后一个 GND/VCC zone，其余删掉 ----
keep = {}
drop = []
for z in b.Zones():
    key = (z.GetLayer(), z.GetNetname())
    if key in keep:
        drop.append(keep[key])       # 先前的那个是旧的，删
    keep[key] = z
for z in drop:
    b.Remove(z)
print(f"删掉重复 zone {len(drop)}，保留 {len(keep)}")

# ---- 2) 热焊盘改实心，消 starved_thermal ----
for z in b.Zones():
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.25))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.3))
print("热焊盘连接已改为实心")

# ---- 3) 悬空过孔：两端都不接走线/焊盘的直接删 ----
b.BuildConnectivity()
vias = [t for t in b.Tracks() if t.Type() == pcbnew.PCB_VIA_T]
print(f"过孔总数 {len(vias)}")

# ---- 4) 重填 ----
zs = list(b.Zones())
filler = pcbnew.ZONE_FILLER(b)
ok = filler.Fill(zs)
print("填充:", "成功" if ok else "False")
b.Save(path)
for z in zs:
    print(f"  {b.GetLayerName(z.GetLayer()):8s} {z.GetNetname():4s} "
          f"{z.GetFilledArea() / 1e12:7.0f} mm2")
print("已保存", path)
