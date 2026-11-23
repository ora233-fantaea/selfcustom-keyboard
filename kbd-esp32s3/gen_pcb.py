#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 pcbnew Python API 生成键盘 PCB：真实75键配列 + 纯 MX 热插拔轴座 + 完整网络分配"""
import sys, os
sys.path.append('/usr/lib/python3/dist-packages')
import pcbnew as pcb

board = pcb.BOARD()

U = 19.05  # 键距(mm)

def mm(v):
    return pcb.FromMM(v)

def load_fp(lib, name):
    """加载封装：直接用 .pretty 目录路径"""
    candidates = [
        f"/usr/share/kicad/footprints/{lib}.pretty",
        f"/root/.local/share/kicad/9.0/footprints/{lib}.pretty",
        f"/root/.local/share/kicad/9.0/footprints/MX_Alps_Hybrid.pretty/{lib}.pretty",
    ]
    for d in candidates:
        if os.path.isdir(d):
            fp = pcb.FootprintLoad(d, name)
            if fp is not None:
                return fp
    return None

def place(lib, name, ref, x, y, value="", nets=None, rot=0):
    """放置封装，nets={pad编号: 网络名}，rot=旋转角度"""
    fp = load_fp(lib, name)
    if fp is None:
        print(f"  [警告] 封装未找到: {lib}:{name}")
        return None
    fp.SetReference(ref)
    fp.SetValue(value or name)
    fp.SetPosition(pcb.VECTOR2I(mm(x), mm(y)))
    if rot:
        fp.SetOrientationDegrees(rot)
    if nets:
        for pad in fp.Pads():
            num = pad.GetNumber()
            if num in nets and nets[num]:
                pad.SetNet(get_net(nets[num]))
    board.Add(fp)
    return fp

# ===== 网络管理 =====
_nets = {}
def get_net(name):
    if name not in _nets:
        n = pcb.NETINFO_ITEM(board, name)
        board.Add(n)
        _nets[name] = n
    return _nets[name]

def pad_pos(fp, num):
    """取封装某个电气焊盘的绝对坐标"""
    for pad in fp.Pads():
        if pad.GetNumber() == num:
            p = pad.GetPosition()
            return (pcb.ToMM(p.x), pcb.ToMM(p.y))
    return None

def wire(netname, pts, width=0.25, layer=None):
    """画一连串线段，分配网络"""
    n = get_net(netname)
    layer = layer if layer is not None else pcb.F_Cu
    for a, b in zip(pts, pts[1:]):
        t = pcb.PCB_TRACK(board)
        t.SetStart(pcb.VECTOR2I(mm(a[0]), mm(a[1])))
        t.SetEnd(pcb.VECTOR2I(mm(b[0]), mm(b[1])))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(n)
        board.Add(t)

# ============================================================
# 1. 真实 75 键配列（6 行，单位 u）
#    格式: (标签, 宽度u)。脚本自动计算中心坐标并编号 K01~K75
# ============================================================
LAYOUT = [
    # Row0 功能行 (13)
    [("Esc",1),("F1",1),("F2",1),("F3",1),("F4",1),("F5",1),("F6",1),
     ("F7",1),("F8",1),("F9",1),("F10",1),("F11",1),("F12",1)],
    # Row1 数字行 (14)
    [("`",1),("1",1),("2",1),("3",1),("4",1),("5",1),("6",1),("7",1),
     ("8",1),("9",1),("0",1),("-",1),("=",1),("Bksp",2)],
    # Row2 Q 行 (13)
    [("Tab",1.5),("Q",1),("W",1),("E",1),("R",1),("T",1),("Y",1),("U",1),
     ("I",1),("O",1),("P",1),("[",1),("]",1),("\\",1.5)],
    # Row3 A 行 (13)
    [("Caps",1.75),("A",1),("S",1),("D",1),("F",1),("G",1),("H",1),("J",1),
     ("K",1),("L",1),(";",1),("'",1),("Enter",2.25)],
    # Row4 Z 行 (13)
    [("LShift",2.25),("Z",1),("X",1),("C",1),("V",1),("B",1),("N",1),("M",1),
     (",",1),(".",1),("/",1),("RShift",1.75),("Up",1)],
    # Row5 底行 (8)
    [("LCtrl",1.25),("LWin",1.25),("LAlt",1.25),("Space",8.25),
     ("Fn",1),("Left",1),("Down",1),("Right",1)],
]

# 板框与原点
ORIGIN_X, ORIGIN_Y = 25.0, 52.0   # 顶部留白 52mm 供开发板双排针接口
MARGIN_X, MARGIN_TOP, MARGIN_BOT = 8.0, 30.0, 40.0
max_row_u = max(sum(w for _, w in row) for row in LAYOUT)
board_w = ORIGIN_X + max_row_u * U + MARGIN_X
board_h = ORIGIN_Y + len(LAYOUT) * U + MARGIN_BOT

# 板框
outline = [(0,0),(board_w,0),(board_w,board_h),(0,board_h),(0,0)]
for i in range(len(outline)-1):
    seg = pcb.PCB_SHAPE(board)
    seg.SetShape(pcb.SHAPE_T_SEGMENT)
    seg.SetStart(pcb.VECTOR2I(mm(outline[i][0]), mm(outline[i][1])))
    seg.SetEnd(pcb.VECTOR2I(mm(outline[i+1][0]), mm(outline[i+1][1])))
    seg.SetLayer(pcb.Edge_Cuts)
    seg.SetWidth(mm(0.1))
    board.Add(seg)

# 安装孔（四角 M3）
for hx, hy in [(5,5),(board_w-5,5),(5,board_h-5),(board_w-5,board_h-5)]:
    place("MountingHole", "MountingHole_3.2mm_M3", f"H{int(round(hx))}_{int(round(hy))}", hx, hy, "M3")

# ============================================================
# 2. 放置 75 个轴座 + 75 个上拉电阻，并分配网络
# ============================================================
key_info = []  # (knum, label, cx, cy)
knum = 0
for r, row in enumerate(LAYOUT):
    cursor = 0.0
    cy = ORIGIN_Y + r * U
    for label, w in row:
        cx = ORIGIN_X + (cursor + w/2.0) * U
        knum += 1
        knet = f"K{knum:02d}"
        key_info.append((knum, label, cx, cy, knet))
        # 纯 MX 热插拔轴座(仅兼容 Cherry MX 及兼容轴): pad1=开关信号, pad2=接地
        place("key-switches", "SW_MX_HotSwap_PTH",
              f"SW{knum:02d}", cx, cy, label,
              nets={"1": knet, "2": "GND"})
        # 上拉电阻 10k: pad1=VCC, pad2=按键网络
        # 放在轴座右侧偏上，避开中心轴孔
        place("Resistor_SMD", "R_0603_1608Metric",
              f"R{knum:02d}", cx + 7.6, cy - 7.6, "10k",
              nets={"1": "VCC", "2": knet})
        cursor += w

assert knum == 75, f"键数错误: {knum}"

# ============================================================
# 3. 10 片 74HC165 级联，贴近对应键位组
#    U1 管 K01-K08 ... U10 管 K73-K75(+5空余接地)
#    74HC165 引脚: D0-7=11,12,13,14,3,4,5,6; DS=10; Q7=9;
#                 ~PL=1; CP=2; ~CE=15; VCC=16; GND=8; ~Q7=7
# ============================================================
D_PINS = ["11","12","13","14","3","4","5","6"]
ics = []  # 保存封装引用用于布线
ic_y = board_h - 18
for i in range(10):
    ic_x = ORIGIN_X + 12 + i * ((max_row_u * U - 24) / 9)
    nets_map = {
        "1": "SH_LD",      # ~PL
        "2": "CLK",        # CP
        "15": "GND",       # ~CE 常使能
        "16": "VCC",
        "8": "GND",
        "10": "GND" if i == 0 else f"CHAIN_{i}",   # DS 级联输入
        "9": f"CHAIN_{i+1}",                        # Q7 级联输出（末片 CHAIN_10 -> ESP32 DATA）
        # pin7 ~Q7 悬空，不分配网络
    }
    # 8 路并行输入
    for j, pin in enumerate(D_PINS):
        kidx = i*8 + j + 1
        nets_map[pin] = f"K{kidx:02d}" if kidx <= 75 else "GND"
    fp = place("Package_SO", "SOIC-16W_7.5x10.3mm_P1.27mm",
               f"U{i+1}", ic_x, ic_y, "74HC165", nets=nets_map)
    ics.append(fp)
    # 每片 100nF 去耦电容
    place("Capacitor_SMD", "C_0603_1608Metric",
          f"C{i+1}", ic_x + 7, ic_y - 8, "100nF",
          nets={"1": "VCC", "2": "GND"})

# ============================================================
# 4. ESP32-S3-DEV-KIT-N16R8-M 板对板接口
#    依据微雪官方尺寸图与原理图：
#    - 两条独立 1x20 排针(P1/P2)，针距 2.54mm
#    - 两排中心距 21.80mm（不是 2x20 一体排母！）
#    - 板外形 63.30 x 25.40mm
#    - P1(左排): 3V3,EN,IO4,IO5,IO6,IO7,IO15,IO16,IO17,IO18,
#               IO8,IO3,IO46,IO9,IO10,IO11,IO12,IO13,IO14,5V
#    - P2(右排): GND,TXD(43),RXD(44),IO1,IO2,IO42,IO41,IO40,IO39,IO38,
#               IO37,IO36,IO35,IO0,IO45,IO48,IO47,IO21,IO20(D+),IO19(D-)
# ============================================================
HDR_ROW_GAP = 21.80          # 两排针中心距(mm)
HDR_PIN1_X = board_w/2 - 24  # pin1 左端 x
HDR_P1_Y = 5.0               # P1 排 y（顶部留白内）
HDR_P2_Y = HDR_P1_Y + HDR_ROW_GAP  # P2 排 y = 26.8，键盘首行 y=52，不冲突

# P1 排针网络（1-20）
p1_nets = {
    "1":"VCC", "2":"NC", "3":"GPIO4", "4":"GPIO5", "5":"GPIO6",
    "6":"GPIO7", "7":"GPIO15", "8":"GPIO16", "9":"GPIO17", "10":"GPIO18",
    "11":"GPIO8", "12":"GPIO3", "13":"NC", "14":"GPIO9", "15":"GPIO10",
    "16":"GPIO11", "17":"GPIO12", "18":"GPIO13", "19":"GPIO14", "20":"NC",
}
# P2 排针网络（1-20）；把本项目信号映射到实际 GPIO 针脚
p2_nets = {
    "1":"GND", "2":"NC", "3":"NC", "4":"GPIO1", "5":"GPIO2",
    "6":"GPIO42", "7":"GPIO41", "8":"GPIO40", "9":"GPIO39", "10":"GPIO38",
    "11":"GPIO37", "12":"GPIO36", "13":"GPIO35", "14":"GPIO0", "15":"GPIO45",
    "16":"GPIO48", "17":"GPIO47", "18":"GPIO21", "19":"NC", "20":"NC",
}
j_p1 = place("Connector_PinHeader_2.54mm", "PinHeader_1x20_P2.54mm_Vertical",
             "J_P1", HDR_PIN1_X, HDR_P1_Y, "DEV-KIT-P1",
             nets=p1_nets, rot=90)
j_p2 = place("Connector_PinHeader_2.54mm", "PinHeader_1x20_P2.54mm_Vertical",
             "J_P2", HDR_PIN1_X, HDR_P2_Y, "DEV-KIT-P2",
             nets=p2_nets, rot=90)

# 项目信号 -> 开发板 GPIO（用标签网络名保持一致，便于飞线）
# CLK->GPIO4(P1.3), SH_LD->GPIO5(P1.4), CHAIN_10(DATA)->GPIO6(P1.5)
# ENC_A->GPIO7(P1.6), ENC_B->GPIO15(P1.7), ENC_SW->GPIO16(P1.8)
# 覆盖为项目网络名（覆盖上面占位 GPIO 名）
for padnum, net in {"3":"CLK", "4":"SH_LD", "5":"CHAIN_10",
                    "6":"ENC_A", "7":"ENC_B", "8":"ENC_SW"}.items():
    for pad in j_p1.Pads():
        if pad.GetNumber() == padnum:
            pad.SetNet(get_net(net))

enc_x, enc_y = board_w - 20, ORIGIN_Y + 8
place("Rotary_Encoder", "RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm",
      "ENC1", enc_x, enc_y, "EC11",
      nets={"A":"ENC_A","B":"ENC_B","C":"GND","S1":"ENC_SW","S2":"GND"})

usb_x, usb_y = board_w - 20, board_h - 45
place("Connector_USB", "USB_C_Receptacle_GCT_USB4085",
      "J_USB", usb_x, usb_y, "USB-C",
      nets={"A4":"VBUS","A9":"VBUS","B4":"VBUS","B9":"VBUS",
            "A1":"GND","A12":"GND","B1":"GND","B12":"GND",
            "A6":"USB_D+","A7":"USB_D-","B6":"USB_D+","B7":"USB_D-",
            "A5":"CC1","B5":"CC2"})

# ============================================================
# 5. 关键网络布线
#    策略：SOIC-16 引脚间距仅 1.27mm，禁止垂直引线穿焊盘。
#    所有引脚先水平引出到芯片两侧的"出口列"（左 x-9 / 右 x+9），
#    再在出口列上纵向汇流。水平引出线走引脚所在 y，互不交叉。
# ============================================================
EXIT_L = 9.0   # 左出口列距芯片中心
EXIT_R = 9.0   # 右出口列距芯片中心

def exit_x(fp, num, side, dist=None):
    """引脚水平引出到出口列，返回出口点坐标。dist 可覆盖默认出口距离"""
    p = pad_pos(fp, num)
    if not p:
        return None
    d = dist if dist is not None else (EXIT_L if side == 'L' else EXIT_R)
    ex = p[0] - d if side == 'L' else p[0] + d
    wire(nets_of(fp, num), [p, (ex, p[1])], 0.25)
    return (ex, p[1])

def nets_of(fp, num):
    for pad in fp.Pads():
        if pad.GetNumber() == num:
            return pad.GetNetname()
    return "NONE"

def add_via(netname, x, y, size=0.7, drill=0.35):
    v = pcb.PCB_VIA(board)
    v.SetPosition(pcb.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(size))
    v.SetDrill(mm(drill))
    v.SetViaType(pcb.VIATYPE_THROUGH)
    v.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
    v.SetNet(get_net(netname))
    board.Add(v)

# 5a. 级联链: 前级 Q7(pin9) -> 后级 DS(pin10)
#     Q7/DS 是 SOIC 右侧相邻引脚(pin9 y+ / pin10 y-)，同层跨接必然交叉。
#     解决: 引脚在 F.Cu 水平引出到出口列 -> 过孔下到 B.Cu -> 背面独立通道连接。
chain_y = ic_y + 11
for i in range(9):
    net = f"CHAIN_{i+1}"
    seg_y = chain_y + i * 0.65        # B.Cu 各段独立通道
    a = exit_x(ics[i], "9", 'R', dist=13)     # Q7 出口 (F.Cu)
    b = exit_x(ics[i+1], "10", 'R', dist=9)   # DS 出口 (F.Cu)
    if a and b:
        add_via(net, a[0], a[1])               # Q7 过孔
        add_via(net, b[0], b[1])               # DS 过孔
        wire(net, [a, (a[0], seg_y), (b[0], seg_y), b], 0.3, layer=pcb.B_Cu)

# 5b. CHAIN_10: 末片 Q7(右列) 引出并打过孔到背面，长距离到 ESP32 DATA 留待布线阶段
d_out = exit_x(ics[9], "9", 'R', dist=13)
if d_out:
    add_via("CHAIN_10", d_out[0], d_out[1])

# 说明：CLK/SH_LD/+3V3/GND 及各按键扫描线的完整布线留待 GUI 中自动/手动完成。
#       本阶段已完成全部焊盘网络分配（网络名即飞线依据），仅预布最关键的级联数据链。

pcb.SaveBoard("kbd-esp32s3.kicad_pcb", board)
print(f"PCB 生成完成: {knum} 键(纯 MX 热插拔轴座) + {knum} 上拉电阻 + 10×74HC165 + 10×去耦 + 排母/编码器/USB-C")
print(f"板框: {board_w:.1f} x {board_h:.1f} mm, 网络数: {len(_nets)}")
