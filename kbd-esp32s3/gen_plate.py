#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成独立定位板(plate)：按主 PCB 板框与键位孔位，plate-mount 卫星轴开孔。

输出:
  - kbd-plate.kicad_pcb   定位板板文件(Edge.Cuts: 板框/键孔/卫星孔/M3孔/避让窗)
  - kbd-plate.dxf         Edge.Cuts 层 DXF，发厂激光切割/CNC 用
  - plate_preview.png     预览图

坐标与主 PCB 完全一致(板左上原点，X 右 Y 下，mm)。
卫星轴按用户确认: 空格 8u(133.35mm)，仅 2u 以上大键，plate-mount。
"""
import ast
import os
import sys

sys.path.append("/usr/lib/python3/dist-packages")
import pcbnew as pcb

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- 1. 从 kbd_design.py 提取配列/常量 ----------
def load_layout():
    src = open(os.path.join(HERE, "kbd_design.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    env = {}
    want = ("U", "ORIGIN_X", "ORIGIN_Y", "MARGIN_X", "MARGIN_BOT", "LAYOUT")

    def names_of(t):
        if isinstance(t, ast.Name):
            return [t.id]
        if isinstance(t, ast.Tuple):
            return [e.id for e in t.elts if isinstance(e, ast.Name)]
        return []

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        ns = [n for n in names_of(tgt) if n in want]
        if not ns:
            continue
        val = ast.literal_eval(node.value)
        vals = val if isinstance(val, tuple) else (val,)
        for name, v in zip(names_of(tgt), vals):
            if name in want:
                env[name] = v
    return env


env = load_layout()
U = env["U"]
OX, OY = env["ORIGIN_X"], env["ORIGIN_Y"]
MX_, MB_ = env["MARGIN_X"], env["MARGIN_BOT"]
LAYOUT = env["LAYOUT"]

max_row_u = max(sum(w for _, w in row) for row in LAYOUT)
board_w = OX + max_row_u * U + MX_
board_h = OY + len(LAYOUT) * U + MB_

# 键位中心
keys = []
knum = 0
for r, row in enumerate(LAYOUT):
    cursor = 0.0
    cy = OY + r * U
    for label, w in row:
        cx = OX + (cursor + w / 2.0) * U
        knum += 1
        keys.append({"n": knum, "label": label, "w": w, "cx": cx, "cy": cy})
        cursor += w

# 卫星轴半距(键中心->housing 中心)
STD_HALF = {2.0: 11.9, 2.25: 11.9, 2.75: 11.9,
            6.25: 50.0, 7.0: 57.15, 8.0: 66.675}


def rec_half(k):
    if k["w"] == 8.25:
        return STD_HALF[8.0]  # 用户确认空格按 8u
    if k["w"] in STD_HALF:
        return STD_HALF[k["w"]]
    return (k["w"] - 1.0) / 2.0 * U


big = [k for k in keys if k["w"] >= 2.0]

# ---------- 2. 建定位板板文件 ----------
board = pcb.BOARD()


def mm(v):
    return pcb.FromMM(v)


def seg(x1, y1, x2, y2, width=0.1):
    s = pcb.PCB_SHAPE(board)
    s.SetShape(pcb.SHAPE_T_SEGMENT)
    s.SetStart(pcb.VECTOR2I(mm(x1), mm(y1)))
    s.SetEnd(pcb.VECTOR2I(mm(x2), mm(y2)))
    s.SetLayer(pcb.Edge_Cuts)
    s.SetWidth(mm(width))
    board.Add(s)


def rect(x0, y0, x1, y1, width=0.1):
    seg(x0, y0, x1, y0, width)
    seg(x1, y0, x1, y1, width)
    seg(x1, y1, x0, y1, width)
    seg(x0, y1, x0, y0, width)


def circle(cx, cy, r, width=0.1):
    c = pcb.PCB_SHAPE(board)
    c.SetShape(pcb.SHAPE_T_CIRCLE)
    c.SetCenter(pcb.VECTOR2I(mm(cx), mm(cy)))
    c.SetEnd(pcb.VECTOR2I(mm(cx + r), mm(cy)))  # 半径点
    c.SetLayer(pcb.Edge_Cuts)
    c.SetWidth(mm(width))
    board.Add(c)


def polygon(rings, width=0.1):
    """rings: list of [(x,y),...] 外环。每个环单独建一个多边形图元。"""
    for ring in rings:
        pts = list(ring)
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        ps = pcb.SHAPE_POLY_SET()
        ps.NewOutline()
        for x, y in pts:
            ps.Append(mm(x), mm(y))
        s = pcb.PCB_SHAPE(board)
        s.SetShape(pcb.SHAPE_T_POLY)
        s.SetPolyShape(ps)
        s.SetLayer(pcb.Edge_Cuts)
        s.SetWidth(mm(width))
        board.Add(s)


# 2.1 板外框
rect(0, 0, board_w, board_h, 0.15)

# 2.2 + 2.3 键位孔与卫星轴孔
#   小键: 14x14 方孔
#   2u/2.25u 大键: 14mm 轴孔左右各连一个 6.65x12.3 housing 孔，
#                 中间用窄通道连通(Cherry plate-mount 一体开孔)，否则 housing 卡不进去
#   空格(8u, 卫星孔距中心 66.675mm 远): 轴孔与两卫星孔各自独立
from shapely.geometry import box
from shapely.ops import unary_union

KEY_HOLE = 14.0
STAB_W, STAB_H = 6.65, 12.3
NECK_W = 5.0   # 连通颈宽(y 方向)
stab_holes = []
big_refs = {k["n"]: k for k in big}

for k in keys:
    cx, cy = k["cx"], k["cy"]
    h = KEY_HOLE / 2.0
    if k["n"] not in big_refs:
        rect(cx - h, cy - h, cx + h, cy + h, 0.1)
        continue

    half = rec_half(k)
    parts = [box(cx - h, cy - h, cx + h, cy + h)]  # 中心轴孔
    for sx in (cx - half, cx + half):
        # housing 开口(横向 6.65, 纵向 12.3，关于键中心上下对称)
        parts.append(box(sx - STAB_W / 2.0, cy - STAB_H / 2.0,
                         sx + STAB_W / 2.0, cy + STAB_H / 2.0))
        stab_holes.append((k["label"], sx, cy))
        # 2u 级(半距<20mm): 用颈连通轴孔与 housing 孔
        if half < 20.0:
            x0 = min(cx + h, sx + STAB_W / 2.0)
            x1 = max(cx - h, sx - STAB_W / 2.0)
            if x1 > x0:
                parts.append(box(x0, cy - NECK_W / 2.0, x1, cy + NECK_W / 2.0))

    merged = unary_union(parts)
    polys = merged.geoms if hasattr(merged, "geoms") else [merged]
    rings = []
    for p in polys:
        ring = list(p.exterior.coords)
        rings.append([(x, y) for x, y in ring])
    polygon(rings, 0.1)

# 2.4 四角 M3 安装孔 Ø3.2（与主 PCB 对齐）
for hx, hy in [(5, 5), (board_w - 5, 5), (5, board_h - 5), (board_w - 5, board_h - 5)]:
    circle(hx, hy, 1.6, 0.1)

# 2.5 开发板本体检出窗（模块 63.30 x 25.40，x 137.25..200.55 / y 2.20..27.60，留 1.5mm 余量）
rect(136, 1, 202, 30, 0.1)

plate_path = os.path.join(HERE, "kbd-plate.kicad_pcb")
pcb.SaveBoard(plate_path, board)

# ---------- 3. 导出 DXF（Edge.Cuts 层） ----------
import subprocess
import glob as _glob
import tempfile
import shutil

dxf_path = os.path.join(HERE, "kbd-plate.dxf")
# KiCad 的 --output 是目录；导出到临时目录再拷回统一文件名
for old in _glob.glob(os.path.join(HERE, "kbd-plate-*.dxf")) + [dxf_path]:
    if os.path.isdir(old):
        shutil.rmtree(old)
    elif os.path.exists(old):
        os.remove(old)
with tempfile.TemporaryDirectory() as td:
    r = subprocess.run(
        ["kicad-cli", "pcb", "export", "dxf", "--layers", "Edge.Cuts",
         "--output", td, plate_path],
        check=False, capture_output=True, text=True,
    )
    made = _glob.glob(os.path.join(td, "*.dxf"))
    if made:
        shutil.copy(made[0], dxf_path)
print("DXF:", "OK" if os.path.exists(dxf_path) else "FAILED", r.stderr.strip()[:120])

# ---------- 4. PNG 预览 ----------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

fig, ax = plt.subplots(figsize=(15, 9))
ax.add_patch(Rectangle((0, 0), board_w, board_h, fill=False,
                       edgecolor="#111", linewidth=1.6))

# 键孔(小键方孔；大键用与卫星孔合并后的轮廓)
from matplotlib.patches import Polygon as MplPolygon

for k in keys:
    cx, cy = k["cx"], k["cy"]
    h = KEY_HOLE / 2.0
    is_big = k["n"] in big_refs
    if is_big:
        half = rec_half(k)
        parts = [box(cx - h, cy - h, cx + h, cy + h)]
        for sx in (cx - half, cx + half):
            parts.append(box(sx - STAB_W / 2.0, cy - STAB_H / 2.0,
                             sx + STAB_W / 2.0, cy + STAB_H / 2.0))
            if half < 20.0:
                x0 = min(cx + h, sx + STAB_W / 2.0)
                x1 = max(cx - h, sx - STAB_W / 2.0)
                if x1 > x0:
                    parts.append(box(x0, cy - NECK_W / 2.0, x1, cy + NECK_W / 2.0))
        mg = unary_union(parts)
        for p in (mg.geoms if hasattr(mg, "geoms") else [mg]):
            ax.add_patch(MplPolygon(list(p.exterior.coords),
                                    facecolor="#f5c26b", edgecolor="#333", linewidth=0.7))
    else:
        ax.add_patch(Rectangle(
            (cx - h, cy - h), KEY_HOLE, KEY_HOLE,
            facecolor="#dfe6ef", edgecolor="#333", linewidth=0.7,
        ))
    ax.text(cx, cy, k["label"], ha="center", va="center",
            fontsize=6, color="#111")

# 卫星孔红色标注(空格独立孔、大键中心)，便于识别
for label, sx, sy in stab_holes:
    ax.add_patch(Rectangle(
        (sx - STAB_W / 2.0, sy - STAB_H / 2.0), STAB_W, STAB_H,
        facecolor="#c0392b", edgecolor="#7b1c13", linewidth=0.6, alpha=0.85,
    ))

# M3
for hx, hy in [(5, 5), (board_w - 5, 5), (5, board_h - 5), (board_w - 5, board_h - 5)]:
    ax.add_patch(Circle((hx, hy), 1.6, facecolor="white", edgecolor="#111", linewidth=1.0))

# 避让窗
ax.add_patch(Rectangle((136, 1), 66, 29, fill=False,
                       edgecolor="#2c3e50", linewidth=1.2, linestyle="--"))
ax.text(169, 16.5, "DEV-KIT cutout", ha="center", va="center",
        fontsize=7, color="#2c3e50")

ax.set_title(f"Switch plate  |  {board_w:.1f} x {board_h:.1f} mm  |  1.5mm FR4/aluminium  |  unit: mm",
             fontsize=11, pad=10)
ax.text(0, board_h + 6,
        "Orange = stabilized key (>=2u)    Red = plate-mount stab housing opening (6.65x12.3)    "
        "Dashed = dev-kit clearance",
        fontsize=8, color="#333")
ax.set_xlim(-5, board_w + 5)
ax.set_ylim(board_h + 14, -8)
ax.set_aspect("equal")
ax.axis("off")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "plate_preview.png"), dpi=170, bbox_inches="tight")
plt.close(fig)

print(f"OK -> kbd-plate.kicad_pcb / kbd-plate.dxf / plate_preview.png")
print(f"板框 {board_w:.1f} x {board_h:.1f} mm, 键孔 {len(keys)}, 卫星孔 {len(stab_holes)}, M3 x4, 避让窗 x1")
for label, sx, sy in stab_holes:
    print(f"  {label:6s} stab X={sx:.2f} Y={sy:.2f}")
