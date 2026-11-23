"""等距视角键盘成品渲染图 —— 75键配列 + 深色铝坨坨 + 琥珀色点缀（磁带未来主义）"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.transforms import Affine2D
import math

# ---------- 配列（与 gen_pcb.py 完全一致）----------
LAYOUT = [
    [("Esc",1),("F1",1),("F2",1),("F3",1),("F4",1),("F5",1),("F6",1),
     ("F7",1),("F8",1),("F9",1),("F10",1),("F11",1),("F12",1)],
    [("~",1),("1",1),("2",1),("3",1),("4",1),("5",1),("6",1),("7",1),
     ("8",1),("9",1),("0",1),("-",1),("=",1),("Bksp",2)],
    [("Tab",1.5),("Q",1),("W",1),("E",1),("R",1),("T",1),("Y",1),("U",1),
     ("I",1),("O",1),("P",1),("[",1),("]",1),("\\",1.5)],
    [("Caps",1.75),("A",1),("S",1),("D",1),("F",1),("G",1),("H",1),("J",1),
     ("K",1),("L",1),(";",1),("'",1),("Enter",2.25)],
    [("LShift",2.25),("Z",1),("X",1),("C",1),("V",1),("B",1),("N",1),("M",1),
     (",",1),(".",1),("/",1),("RShift",1.75),("Up",1)],
    [("LCtrl",1.25),("LWin",1.25),("LAlt",1.25),("Space",8.25),
     ("Fn",1),("Left",1),("Down",1),("Right",1)],
]
NROW = len(LAYOUT)
MAXU = max(sum(w for _, w in r) for r in LAYOUT)

# ---------- 等距投影 ----------
C = math.cos(math.radians(30))
S = math.sin(math.radians(30))
def iso(x, y, z):
    return ((x - y) * C, -(x + y) * S + z)

# ---------- 配色 ----------
BG       = '#0d1015'
CASE_TOP = '#2c323b'
CASE_X   = '#1f242b'
CASE_Y   = '#171b21'
CASE_ED  = '#454e5b'
KEY_TOP  = '#3b424c'   # 字母键
KEY_X    = '#272d35'
KEY_Y    = '#1e232a'
AMB_TOP  = '#c8892f'   # 琥珀：修饰键
AMB_X    = '#96631f'
AMB_Y    = '#754c17'
RED_TOP  = '#a1442f'   # 暗红：功能行
RED_X    = '#783023'
RED_Y    = '#5d241b'
TXT_LITE = '#e6e2d8'
TXT_DARK = '#1a1408'

def kind(label):
    # F1~F12 与 Esc 判定为功能键（避免误伤字母 F）
    if label == 'Esc' or (label.startswith('F') and label[1:].isdigit()):
        return 'red'
    mods = {'Tab','Caps','LShift','RShift','LCtrl','LWin','LAlt','Fn',
            'Bksp','Enter'}
    if label in mods or label in ('Up','Down','Left','Right'):
        return 'amber'
    return 'key'

def colors(k):
    return {'red':(RED_TOP,RED_X,RED_Y,TXT_LITE),
            'amber':(AMB_TOP,AMB_X,AMB_Y,TXT_DARK),
            'key':(KEY_TOP,KEY_X,KEY_Y,TXT_LITE)}[k]

fig, ax = plt.subplots(figsize=(20, 11), dpi=110)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# 柔和地面阴影（多层半透明椭圆）
from matplotlib.patches import Ellipse
for i in range(14, 0, -1):
    e = Ellipse((0, -(MAXU*0.5)*S - 0.1), width=(MAXU+NROW)*C*0.98 + i*0.15,
                height=(MAXU+NROW)*S*0.55 + i*0.09,
                facecolor='#05070a', alpha=0.035, edgecolor='none', zorder=0)
    ax.add_patch(e)

# ---------- 外壳 ----------
cx0, cx1 = -0.35, MAXU + 0.35
cy0, cy1 = -0.35, NROW + 0.35
ch = 0.5  # 外壳厚度
def poly(pts, fc, ec, lw=0.6, z=1):
    p = Polygon([iso(*q) for q in pts], closed=True, facecolor=fc,
                edgecolor=ec, linewidth=lw, joinstyle='round', zorder=z)
    ax.add_patch(p)
# 外壳三个可见面
poly([(cx1,cy0,0),(cx1,cy1,0),(cx1,cy1,-ch),(cx1,cy0,-ch)], CASE_X, CASE_ED)   # 右侧
poly([(cx0,cy1,0),(cx1,cy1,0),(cx1,cy1,-ch),(cx0,cy1,-ch)], CASE_Y, CASE_ED)   # 前侧
poly([(cx0,cy0,0),(cx1,cy0,0),(cx1,cy1,0),(cx0,cy1,0)], CASE_TOP, CASE_ED, 1.0) # 顶面

# ---------- 键帽 ----------
gap = 0.12
kz0, kz1 = 0.03, 0.30   # 键帽底 / 顶
keys = []
xcur = 0.0
for r, row in enumerate(LAYOUT):
    x = 0.0
    for label, w in row:
        keys.append((label, x, r, w))
        x += w
    xcur = max(xcur, x)

# 按 (X+Y) 升序绘制（远的先画，近的覆盖）
def key_depth(k):
    _, x, r, w = k
    return (x + w/2) + (r + 0.5)

for label, x, r, w in sorted(keys, key=key_depth):
    kx0, kx1 = x + gap/2, x + w - gap/2
    ky0, ky1 = r + gap/2, r + 1 - gap/2
    top, sx, sy, tc = colors(kind(label))
    z = 2 + ((x + w/2) + (r + 0.5)) * 0.01
    # 右侧面 / 前侧面 / 顶面
    poly([(kx1,ky0,kz1),(kx1,ky1,kz1),(kx1,ky1,kz0),(kx1,ky0,kz0)], sx, sx, 0.3, z)
    poly([(kx0,ky1,kz1),(kx1,ky1,kz1),(kx1,ky1,kz0),(kx0,ky1,kz0)], sy, sy, 0.3, z)
    P00 = iso(kx0, ky0, kz1); P10 = iso(kx1, ky0, kz1); P01 = iso(kx0, ky1, kz1); P11 = iso(kx1, ky1, kz1)
    poly([(kx0,ky0,kz1),(kx1,ky0,kz1),(kx1,ky1,kz1),(kx0,ky1,kz1)], top, '#12161c', 0.5, z+0.4)
    # 字符（仿射贴到顶面）
    a = P10[0]-P00[0]; d = P10[1]-P00[1]
    b = P01[0]-P00[0]; e = P01[1]-P00[1]
    c0 = P00[0]; f0 = P00[1]
    trans = Affine2D([[a,b,c0],[d,e,f0],[0,0,1]]) + ax.transData
    fs = 7.2 if len(label) <= 2 else (5.6 if len(label) <= 4 else 4.4)
    ax.text(0.5, 0.5, label, transform=trans, ha='center', va='center',
            color=tc, fontsize=fs, fontfamily='DejaVu Sans', zorder=z+0.6,
            fontweight='bold' if len(label)<=1 else 'normal')

# ---------- 旋钮（F行右侧空位，EC11 编码器）----------
import numpy as np
knx, kny, rad = MAXU - 1.4, 0.5, 0.42
ang = np.linspace(0, 2*math.pi, 40)
ring = [(knx + rad*math.cos(t), kny + rad*math.sin(t), kz1+0.06) for t in ang]
poly(ring, AMB_TOP, '#12161c', 1.0, 20)
poly([(knx + rad*math.cos(t), kny + rad*math.sin(t), kz1-0.12) for t in ang], AMB_X, AMB_X, 0.3, 19)
ax.plot(*iso(knx, kny, kz1+0.07), marker='o', ms=4, color='#12161c', zorder=21)

# ---------- 标题 ----------
ax.text(-(NROW)*C - 0.6, 2.0, 'ESP32-S3  //  75% HOT-SWAP',
        color='#c8892f', fontsize=15, fontfamily='DejaVu Sans Mono',
        fontweight='bold', zorder=30)
ax.text(-(NROW)*C - 0.6, 1.4, 'MX / CHOC V1  DUAL-MOUNT   ·   ESP32-S3 NATIVE USB HID  ·  1000Hz',
        color='#6c7684', fontsize=8.5, fontfamily='DejaVu Sans Mono', zorder=30)
ax.text(MAXU*C + 1.0, -(MAXU+NROW)*S - 1.2, 'CASSETTE FUTURISM EDITION  ·  2026',
        color='#4b5563', fontsize=8, fontfamily='DejaVu Sans Mono', zorder=30, ha='right')

ax.set_aspect('equal')
ax.autoscale_view()
ax.set_xlim(*(ax.get_xlim()[0]-0.8, ax.get_xlim()[1]+0.8))
ax.set_ylim(*(ax.get_ylim()[0]-0.8, ax.get_ylim()[1]+1.2))
ax.axis('off')
plt.tight_layout()
out = '/workspace/kbd-esp32s3/render_keyboard.png'
plt.savefig(out, facecolor=BG, bbox_inches='tight', pad_inches=0.3)
print('已生成:', out)

# ---------- 正俯视配列图（清晰展示方向键倒T）----------
from matplotlib.patches import Rectangle
fig2, ax2 = plt.subplots(figsize=(19, 7.5), dpi=110)
fig2.patch.set_facecolor(BG)
ax2.set_facecolor(BG)
for label, x, r, w in keys:
    top, sx, sy, tc = colors(kind(label))
    kx0, ky0 = x + gap/2, r + gap/2
    kw, kh = w - gap, 1 - gap
    ax2.add_patch(Rectangle((kx0, ky0), kw, kh, facecolor=top,
                            edgecolor='#12161c', linewidth=1.2, zorder=2))
    fs = 11 if len(label) <= 2 else (8.5 if len(label) <= 4 else 6.5)
    ax2.text(kx0+kw/2, ky0+kh/2, label, ha='center', va='center', color=tc,
             fontsize=fs, fontfamily='DejaVu Sans',
             fontweight='bold' if len(label) <= 1 else 'normal', zorder=3)
# 旋钮（F行右侧空位）
ax2.add_patch(plt.Circle((MAXU-1.4, 0.5), 0.42, facecolor=AMB_TOP,
                         edgecolor='#12161c', linewidth=1.2, zorder=2))
ax2.text(MAXU-1.4, 0.5, 'ENC', ha='center', va='center', color=TXT_DARK,
         fontsize=5.5, fontfamily='DejaVu Sans Mono', fontweight='bold', zorder=3)
ax2.set_xlim(-0.5, MAXU+0.5)
ax2.set_ylim(NROW+0.6, -1.3)
ax2.set_aspect('equal')
ax2.axis('off')
ax2.set_title('75% LAYOUT  //  TOP VIEW  -  standard inverted-T arrow cluster',
              color='#c8892f', fontsize=14, fontfamily='DejaVu Sans Mono',
              fontweight='bold', pad=12)
out2 = '/workspace/kbd-esp32s3/layout_topview.png'
plt.savefig(out2, facecolor=BG, bbox_inches='tight', pad_inches=0.3)
print('已生成:', out2)
