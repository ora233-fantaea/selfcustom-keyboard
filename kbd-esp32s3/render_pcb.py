#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染 PCB 预览：板框 / 开槽 / 焊盘 / 走线 / 过孔"""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.collections import LineCollection
import board_geom as BG

path = sys.argv[1] if len(sys.argv) > 1 else "kbd-esp32s3.kicad_pcb"
out = sys.argv[2] if len(sys.argv) > 2 else "pcb_preview.png"
zoom = sys.argv[3] if len(sys.argv) > 3 else None

g = BG.load(path)
ox, oy, ex, ey, _ = g["outline"]

fig, ax = plt.subplots(figsize=(20, 10.2))
ax.add_patch(Rectangle((ox, oy), ex - ox, ey - oy, fill=False, ec="#111", lw=1.4))

for s in g["slots"]:
    ax.add_patch(Rectangle((s[0], s[1]), s[2] - s[0], s[3] - s[1],
                           fc="#c0392b", ec="none", zorder=6))

for p in g["pads"]:
    if p["drill"] > 0:
        ax.add_patch(Circle((p["x"], p["y"]), p["drill"] / 2, fill=False,
                            ec="#2c7fb8", lw=0.6, zorder=7))
    lays = BG.copper_layers(p)
    color = "#e8a33d" if "B.Cu" in lays and "F.Cu" not in lays else "#f2c14e"
    ax.add_patch(Rectangle((p["x"] - p["w"] / 2, p["y"] - p["h"] / 2), p["w"], p["h"],
                           fc=color, ec="none", alpha=0.95, zorder=5))

for layer, col in (("F.Cu", "#1f9d55"), ("B.Cu", "#8e44ad")):
    segs = [[(t["x1"], t["y1"]), (t["x2"], t["y2"])] for t in g["tracks"] if t["layer"] == layer]
    if segs:
        ax.add_collection(LineCollection(segs, colors=col, linewidths=0.55, zorder=4))

for v in g["vias"]:
    ax.add_patch(Circle((v["x"], v["y"]), v["d"] / 2, fc="#bdc3c7", ec="#555",
                        lw=0.4, zorder=8))

if zoom:
    x1, y1, x2, y2 = [float(t) for t in zoom.split(",")]
    ax.set_xlim(x1, x2)
    ax.set_ylim(y2, y1)
else:
    ax.set_xlim(ox - 3, ex + 3)
    ax.set_ylim(ey + 3, oy - 3)

ax.set_aspect("equal")
ax.axis("off")
ax.set_title(f"{path}  |  tracks {len(g['tracks'])}  vias {len(g['vias'])}  "
             f"slots {len(g['slots'])}  |  green=F.Cu purple=B.Cu", fontsize=10)
fig.tight_layout()
fig.savefig(out, dpi=150, facecolor="white")
print("saved", out)
