#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重填铺铜（只用 KiCad 自带 python.exe 跑）

traces 一改，旧的 zone fill 就过期了：DRC 会拿旧填充去算间距，
报出成百上千条假的 clearance / hole_clearance。所以布线后必须重填。

    ../../_tools/KiCad/bin/python.exe refill.py [板文件]
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "kbd-esp32s3.kicad_pcb")

b = pcbnew.LoadBoard(PCB)
zs = list(b.Zones())
print(f"zone 数 {len(zs)}")
if zs:
    ok = pcbnew.ZONE_FILLER(b).Fill(zs)
    print("填充", "成功" if ok else "失败")
pcbnew.SaveBoard(PCB, b)
print("已保存", PCB)
