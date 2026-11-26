#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 _routes.json 里的走线/过孔用 pcbnew 写进板子（KiCad 自己写文件，保证能打开）

    ../../_tools/KiCad/bin/python.exe apply_routes.py [板文件] [json]
"""
import json
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
JS = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "_routes.json")

LAY = {0: pcbnew.F_Cu, 1: pcbnew.In1_Cu, 2: pcbnew.In2_Cu, 3: pcbnew.B_Cu}
W = pcbnew.FromMM(0.15)
VIA_D = pcbnew.FromMM(0.6)
VIA_DRILL = pcbnew.FromMM(0.3)

b = pcbnew.LoadBoard(PCB)
# 直接从焊盘收集 网络名 -> NETINFO_ITEM（GetNetsByName 的 SWIG 迭代器不好用）
netmap = {}
for fp in b.GetFootprints():
    for pad in fp.Pads():
        nm = str(pad.GetNetname())
        if nm:
            netmap[nm] = pad.GetNet()
print("板上有焊盘的网络", len(netmap))
items = json.load(open(JS, encoding="utf-8"))
print("铜层数", b.GetCopperLayerCount(), " 待写入", len(items))

nseg = nvia = 0
missing = set()
for it in items:
    if it[0] == "seg":
        _, net, L, p, q = it
        nt = netmap.get(net)
        if nt is None:
            missing.add(net)
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(q[0]), pcbnew.FromMM(q[1])))
        t.SetWidth(W)
        t.SetLayer(LAY[int(L)])
        t.SetNet(nt)
        b.Add(t)
        nseg += 1
    else:
        _, net, x, y = it
        nt = netmap.get(net)
        if nt is None:
            missing.add(net)
            continue
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(VIA_D)
        v.SetDrill(VIA_DRILL)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(nt)
        b.Add(v)
        nvia += 1

if missing:
    print("!! 找不到网络:", sorted(missing))
pcbnew.SaveBoard(PCB, b)
print(f"写入 {nseg} 段 / {nvia} 孔 -> {PCB}")
