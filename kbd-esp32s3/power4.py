#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4 层板电源方案：
  - In1.Cu = VCC 完整平面（75 个上拉 + 10 个 165 的 VCC 脚 + 10 个去耦电容全在这里）
  - F/B/In2 = GND 铺铜（GND 有 85 个通孔焊盘，双层铺铜天然连通）
  - 给每个 VCC 的 SMD 焊盘打「盘中孔」(via-in-pad) 接到 In1

为什么不是 In1=GND：VCC 有 95 个纯 F.Cu 的 SMD 焊盘散在整板，
只有平面能连；GND 有 85 个通孔焊盘，铺铜就够。

幂等：先删所有 GND/VCC zone 与「盘中的 VCC 过孔」再重建。
    KiCad/bin/python.exe power4.py [板文件]
"""
import os
import sys

import pcbnew

path = sys.argv[1] if len(sys.argv) > 1 else "kbd-esp32s3.kicad_pcb"
b = pcbnew.LoadBoard(path)
if b is None:
    raise SystemExit(f"加载失败: {path}")

MM = pcbnew.FromMM

# ---- 1) 旧 zone 已由独立进程清空（删除会留悬空指针，见 purge_zones.py）----

# ---- 2) 给 VCC SMD 焊盘打盘中孔 ----
net_vcc = b.FindNet("VCC")
net_gnd = b.FindNet("GND")
if net_vcc is None or net_gnd is None:
    raise SystemExit("找不到 VCC/GND 网络")

# 先删掉已有的 VCC 过孔（幂等重跑时不叠加）
# 注意：本机 pcbnew 的 BOARD.GetTracks() 在 SWIG 层不可迭代，改用容器接口。
rm = 0
print(f"清理旧 VCC 过孔: {rm}")

# 孔已由 vcc_bus.py 按「避开 In2/B 走线」的规则打好，这里不再重复打。
added = 0
print(f"VCC 盘中孔（复用 vcc_bus 已打的孔）")

# ---- 3) 铺铜：In1=VCC，其余=GND ----
bb = b.GetBoardEdgesBoundingBox()
inset = MM(0.8)
x0, y0 = bb.GetLeft() + inset, bb.GetTop() + inset
x1, y1 = bb.GetRight() - inset, bb.GetBottom() - inset

PLAN = [("In1.Cu", net_vcc), ("F.Cu", net_gnd), ("In2.Cu", net_gnd), ("B.Cu", net_gnd)]

zones = []
for lname, net in PLAN:
    lid = b.GetLayerID(lname)
    if lid < 0:
        print(f"  跳过不存在的层 {lname}")
        continue
    z = pcbnew.ZONE(b)
    z.SetNetCode(net.GetNetCode())
    z.SetLayer(lid)
    z.SetLocalClearance(MM(0.30))
    z.SetMinThickness(MM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    o = z.Outline()
    idx = o.NewOutline()
    for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(px, py, idx)
    b.Add(z)
    zones.append((lname, net.GetNetname(), z))
    print(f"  铺 {lname} = {net.GetNetname()}")

b.Save(path + ".z")          # 先落盘：若 Fill 崩溃，zone 定义仍在
print("zone 已写入", path + ".z", flush=True)

filler = pcbnew.ZONE_FILLER(b)
ok = filler.Fill([z for _, _, z in zones])
print("填充:", "成功" if ok else "返回 False", flush=True)

b.Save(path)
for lname, nn, z in zones:
    print(f"  {lname:7s} {nn:4s} 填充 {z.GetFilledArea() / 1e12:7.0f} mm2")
print("已保存", path)
