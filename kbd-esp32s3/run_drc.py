#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调用 KiCad 官方 kicad-cli 跑 DRC，并按类型汇总

用法:
    python run_drc.py                      # 默认 kbd-esp32s3.kicad_pcb
    python run_drc.py xxx.kicad_pcb        # 指定板文件

kicad-cli 查找顺序:
    $KICAD_CLI  ->  ../_tools/KiCad/bin/kicad-cli.exe（免安装解包的位置） ->  PATH
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [
    os.environ.get("KICAD_CLI", ""),
    os.path.join(HERE, "..", "..", "_tools", "KiCad", "bin", "kicad-cli.exe"),
    os.path.join(HERE, "..", "..", "..", "_tools", "KiCad", "bin", "kicad-cli.exe"),
    "kicad-cli",
]

TYPES = {
    "clearance": "铜箔间距",
    "hole_clearance": "孔-铜间距",
    "courtyards_overlap": "占位框重叠",
    "silk_over_copper": "丝印压焊盘",
    "silk_overlap": "丝印重叠",
    "unconnected_items": "未连接",
    "shorting_items": "短路",
    "track_width": "线宽",
    "via_diameter": "过孔尺寸",
    "drill_out_of_range": "钻孔超范围",
    "edge_clearance": "板边间距",
}


def find_cli():
    for c in CANDIDATES:
        if not c:
            continue
        if os.path.isabs(c):
            if os.path.exists(c):
                return c
        elif subprocess.run(["where", c], capture_output=True).returncode == 0:
            return c
    return None


def main(board="kbd-esp32s3.kicad_pcb"):
    cli = find_cli()
    if not cli:
        print("找不到 kicad-cli。设置环境变量 KICAD_CLI 指向它，或放到 ../_tools/KiCad/bin/")
        return 2
    rpt = os.path.splitext(board)[0] + ".drc.rpt"
    r = subprocess.run([cli, "pcb", "drc", "--format", "report", "-o", rpt, board],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    if "加载失败" in out or "failed to load" in out.lower():
        print(f"KiCad 无法加载 {board}\n{out.strip()}")
        return 1
    if not os.path.exists(rpt):
        print("DRC 未产出报告:\n" + out.strip())
        return 1

    txt = open(rpt, encoding="utf-8").read()
    items = re.findall(r"^\[(\w+)\]: ([^\n]*)", txt, re.M)
    counts = {}
    for t, _ in items:
        counts[t] = counts.get(t, 0) + 1

    print(f"DRC: {board}")
    print("=" * 62)
    total = 0
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        total += n
        print(f"  {TYPES.get(t, t):<14} {n:>5}   [{t}]")
    print("-" * 62)
    print(f"  合计 {total} 条")
    print(f"  报告 {rpt}")
    return 0 if counts.get("shorting_items", 0) == 0 else 3


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
