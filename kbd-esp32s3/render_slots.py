#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 kbd-esp32s3.kicad_pcb 读取真实 Edge.Cuts，绘制标注清晰的开槽/布局图。"""
import sys
sys.path.append('/usr/lib/python3/dist-packages')
import pcbnew as pcb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

B = pcb.LoadBoard('kbd-esp32s3.kicad_pcb')

def mm(v): return pcb.ToMM(v)

fig, ax = plt.subplots(figsize=(15, 7.4))
ax.set_facecolor('#fafbfc')

# 1) Edge.Cuts 线段：板框 vs 内部槽
segs = []
for d in B.GetDrawings():
    if d.GetLayer() != pcb.Edge_Cuts:
        continue
    if d.GetShape() != pcb.SHAPE_T_SEGMENT:
        continue
    s, e = d.GetStart(), d.GetEnd()
    segs.append((mm(s.x), mm(s.y), mm(e.x), mm(e.y)))

# 板框 = 最外围 4 条长边；其余为槽
board_segs = [g for g in segs
              if (abs(g[0]-g[2]) > 300 or abs(g[1]-g[3]) > 150)]
slot_segs = [g for g in segs if g not in board_segs]

for x1, y1, x2, y2 in board_segs:
    ax.plot([x1, x2], [y1, y2], color='#1a1a1a', lw=2.0, zorder=3)
for x1, y1, x2, y2 in slot_segs:
    ax.plot([x1, x2], [y1, y2], color='#c0392b', lw=1.2, zorder=4)

# 2) 轴座：中心孔 + 焊盘（简化为圆点）
for fp in B.GetFootprints():
    ref = fp.GetReference()
    cx, cy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
    if ref.startswith('SW'):
        ax.add_patch(Rectangle((cx-8.5, cy-8.5), 17, 17,
                               facecolor='#dfe6ef', edgecolor='#b0bccb',
                               lw=0.5, zorder=1))
        ax.add_patch(Circle((cx, cy), 2.0, facecolor='#333', zorder=2))
    elif ref.startswith('R'):
        ax.add_patch(Rectangle((cx-1.2, cy-0.7), 2.4, 1.4,
                               facecolor='#7f8c8d', edgecolor='none', zorder=2))
    elif ref.startswith('U'):
        ax.add_patch(Rectangle((cx-5, cy-3.7), 10, 7.4,
                               facecolor='#2c3e50', edgecolor='none', zorder=2))

ax.set_xlim(-5, 343)
ax.set_ylim(170, -6)
ax.set_aspect('equal')
ax.axis('off')
ax.set_title('PCB slot layout (red=slits/Edge.Cuts, gray=switch, dark=74HC165)',
             fontsize=13, pad=10)

# 图例
ax.plot([], [], color='#c0392b', lw=1.5, label='Anti-resonance slits (Edge.Cuts)')
ax.plot([], [], color='#1a1a1a', lw=2, label='Board outline')
ax.legend(loc='lower center', ncol=2, frameon=False, fontsize=9)

out = 'pcb_slots_annotated.png'
plt.tight_layout()
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
print('已生成:', out)
