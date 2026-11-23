#!/usr/bin/env python3
"""
卫星轴(plate-mount)定位板开孔数据生成器。

从 gen_pcb.py 的 LAYOUT 安全提取配列与常量(不执行其 PCB 生成副作用)，
计算所有 >=2u 大键的卫星轴 housing 中心(= 定位板开孔中心)坐标，
输出:
  - stabilizer_plate_holes.md  定位板开孔坐标表
  - stabilizer_layout.png      定位板孔位示意图

坐标系与 KiCad 一致: 板左上角为原点 (0,0)，X 向右，Y 向下，单位 mm。
"""
import ast
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- 1. 从 gen_pcb.py 安全提取 U / ORIGIN / LAYOUT ----------
def load_layout():
    src = open(os.path.join(HERE, "gen_pcb.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    env = {}
    want = ("U", "ORIGIN_X", "ORIGIN_Y", "LAYOUT")

    def names_of(tgt):
        if isinstance(tgt, ast.Name):
            return [tgt.id]
        if isinstance(tgt, ast.Tuple):
            return [e.id for e in tgt.elts if isinstance(e, ast.Name)]
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
    return env["U"], env["ORIGIN_X"], env["ORIGIN_Y"], env["LAYOUT"]


U, OX, OY, LAYOUT = load_layout()

# ---------- 2. 计算所有键中心 ----------
keys = []
knum = 0
for r, row in enumerate(LAYOUT):
    cursor = 0.0
    cy = OY + r * U
    for label, w in row:
        cx = OX + (cursor + w / 2.0) * U
        knum += 1
        keys.append({"n": knum, "label": label, "w": w, "cx": cx, "cy": cy, "row": r})
        cursor += w

max_row_u = max(sum(w for _, w in row) for row in LAYOUT)
board_w = OX + max_row_u * U + 8.0
board_h = OY + len(LAYOUT) * U + 40.0

# ---------- 3. 卫星轴标准孔距(stem center to center) ----------
# Cherry MX 官方: 2u/2.25u/2.75u=23.8, 3u=38.1, 6.25u=100, 7u=114.3, 8u=133.35
STD_HALF = {
    2.0: 11.9,
    2.25: 11.9,
    2.75: 11.9,
    3.0: 19.05,
    6.25: 50.0,
    7.0: 57.15,
    8.0: 66.675,
}


def stab_half(w):
    """理论孔位: 键中心到单个卫星轴 housing 中心的距离(mm)。"""
    if w in STD_HALF:
        return STD_HALF[w]
    # 非标键宽: 通用规则 = 两端各内缩 0.5u
    return (w - 1.0) / 2.0 * U


def rec_half(k):
    """推荐开孔半距: 8.25u 空格按 8u 卫星轴(133.35mm)开孔，其余用理论值。"""
    if k["w"] == 8.25:
        return STD_HALF[8.0]
    return stab_half(k["w"])


# ---------- 4. 筛选 >=2u 大键 ----------
big = [k for k in keys if k["w"] >= 2.0]

# ---------- 5. 生成 Markdown 坐标表 ----------
md = []
md.append("# 卫星轴（plate-mount）定位板开孔坐标\n")
md.append("> 安装方式：**定位板卡扣（plate-mount）**，卫星轴 housing 卡在定位板上，")
md.append("> **PCB 上无需开孔、无需改板**。本表给出定位板需要开的孔中心坐标。\n")
md.append("坐标系：板左上角为原点 (0,0)，X 向右、Y 向下，单位 mm；与 `gen_pcb.py` / KiCad 一致。\n")
md.append("Cherry plate-mount housing 开孔尺寸：每个位置约 **6.65mm(宽) × 12.3mm(高)** 矩形开口，")
md.append("以表中 (X,Y) 为中心；板厚建议 1.5mm。\n")
md.append("## 开孔坐标（仅 2u 以上）\n")
md.append("| 键 | 键宽 | 键中心 (X,Y) | 卫星轴间距 | 左孔 (X,Y) | 右孔 (X,Y) | 规格 |")
md.append("|---|---|---|---|---|---|---|")
for k in big:
    h = rec_half(k)
    lx = k["cx"] - h
    rx = k["cx"] + h
    spec = f"{k['w']}u stab / {2*h:.2f}mm"
    if k["w"] == 8.25:
        spec = "8u stab(推荐) / 133.35mm ※见下方注意"
    md.append(
        f"| {k['label']} (K{k['n']:02d}) | {k['w']}u | ({k['cx']:.2f}, {k['cy']:.2f}) | "
        f"{2*h:.2f}mm | ({lx:.2f}, {k['cy']:.2f}) | ({rx:.2f}, {k['cy']:.2f}) | {spec} |"
    )

# 8.25u 空格特殊说明
space = next(k for k in big if k["w"] == 8.25)
h8 = STD_HALF[8.0]
h825 = stab_half(8.25)
md.append("\n## ⚠ 关于 8.25u 空格（重要）\n")
md.append("Cherry 标准卫星轴**没有 8.25u** 档位，市售只有 2u / 6.25u / 7u / 8u。\n")
md.append("- **推荐**：按 **8u 卫星轴（孔距 133.35mm）** 开孔，居中于空格中心 "
          f"({space['cx']:.2f}, {space['cy']:.2f})，即 "
          f"X = {space['cx']-h8:.2f} 与 {space['cx']+h8:.2f}；"
          "多数 8.25u 键帽按此孔位设计。\n")
md.append(f"- 若你的键帽按「两端各内缩 0.5u」规则开孔，孔距为 **{2*h825:.2f}mm**，"
          f"即 X = {space['cx']-h825:.2f} 与 {space['cx']+h825:.2f}；"
          "但此规格无对应成品卫星轴线，需自制或改键帽。\n")
md.append("- **下单键帽前务必实测/确认其卫星轴孔距**，两种孔位相差约 "
          f"{2*h825-2*h8:.2f}mm，混用会卡不住或装不上。\n")

md.append("\n## 采购清单（卫星轴）\n")
md.append("| 规格 | 数量 | 用途 |")
md.append("|---|---|---|")
md.append("| 2u plate-mount 卫星轴 | 3 | Bksp(2u) / Enter(2.25u) / LShift(2.25u) |")
md.append("| 8u plate-mount 卫星轴 | 1 | Space(8.25u)，孔距 133.35mm |")
md.append("\n> 注：2u / 2.25u / 2.75u 三种键宽共用同一 2u 卫星轴（孔距 23.8mm）。\n")

md.append("## 复现\n")
md.append("```bash\npython3 gen_stabilizers.py\n```\n")
md.append("数据源：`gen_pcb.py` 的 `LAYOUT`；孔距依据 Cherry MX 官方 catalogue "
          "与 [XemStudio](https://xemstudio.com/objects/cherry-mx-plate-mount-stabilizer-cutouts) / "
          "[HilPCB 规范](https://mechkbguide.com/posts/keyboard-stabilizers-explained/)。\n")

with open(os.path.join(HERE, "stabilizer_plate_holes.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md))

# ---------- 6. 生成定位板孔位示意图 ----------
fig, ax = plt.subplots(figsize=(15, 9))

# 板框
ax.add_patch(Rectangle((0, 0), board_w, board_h, fill=False,
                       edgecolor="#444", linewidth=1.2, linestyle="--"))

# 所有键框
for k in keys:
    x0 = OX + (sum(w for _, w in LAYOUT[k["row"]][:0]))  # 占位，实际用中心反推
    w_mm = k["w"] * U
    x0 = k["cx"] - w_mm / 2.0
    y0 = k["cy"] - U / 2.0
    is_big = k["w"] >= 2.0
    ax.add_patch(Rectangle(
        (x0, y0), w_mm, U,
        facecolor="#f5c26b" if is_big else "#eef2f7",
        edgecolor="#222", linewidth=0.8,
    ))
    ax.text(k["cx"], k["cy"], k["label"], ha="center", va="center",
            fontsize=6.5, color="#111")

# 卫星轴孔位（红框 = 推荐开孔）
STAB_COLOR = "#c0392b"
for k in big:
    h = rec_half(k)
    for sx in (k["cx"] - h, k["cx"] + h):
        # housing 开口示意 6.65 x 12.3
        ax.add_patch(Rectangle(
            (sx - 6.65 / 2.0, k["cy"] - 12.3 / 2.0), 6.65, 12.3,
            facecolor="none", edgecolor=STAB_COLOR, linewidth=1.6,
        ))
        ax.add_patch(Circle((sx, k["cy"]), 1.2, color=STAB_COLOR, zorder=5))
        ax.plot([sx - 1.8, sx + 1.8], [k["cy"], k["cy"]], color=STAB_COLOR, lw=0.8)
        ax.plot([sx, sx], [k["cy"] - 1.8, k["cy"] + 1.8], color=STAB_COLOR, lw=0.8)

# 8.25u 空格: 叠加理论 138.1mm 孔位(虚线)作对比
h825 = stab_half(8.25)
for sx in (space["cx"] - h825, space["cx"] + h825):
    ax.add_patch(Circle((sx, space["cy"]), 2.2, facecolor="none",
                        edgecolor="#2c3e50", linewidth=1.2, linestyle="--", zorder=4))

ax.set_title("Stabilizer plate-mount hole map  |  plate origin (0,0) = board top-left  |  unit: mm",
             fontsize=11, pad=12)
ax.text(0, board_h + 6,
        "Orange = stabilized key (>=2u)    Red box/cross = housing opening center (USE these X,Y)    "
        "Dark dashed circle = 8.25u theoretical 138.1mm alt (4.76mm off, see md).",
        fontsize=8, color="#333")
ax.set_xlim(-5, board_w + 5)
ax.set_ylim(board_h + 14, -8)
ax.set_aspect("equal")
ax.axis("off")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "stabilizer_layout.png"), dpi=170, bbox_inches="tight")
plt.close(fig)

print("OK -> stabilizer_plate_holes.md / stabilizer_layout.png")
print(f"大键数: {len(big)}, 卫星轴孔位数: {len(big)*2}")
for k in big:
    h = rec_half(k)
    print(f"  {k['label']:6s} {k['w']:>5}u  center=({k['cx']:.2f},{k['cy']:.2f})  "
          f"holes X={k['cx']-h:.2f} / {k['cx']+h:.2f}")
