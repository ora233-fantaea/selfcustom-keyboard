#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kbd-esp32s3 几何与网络分配的唯一真相源（gen_pcb / gen_sch / gen_plate 共用）

设计要点（2026-11-23 重做）
---------------------------
1. 开槽：在 4 排字母区（行 1~4）的行间边界上做 2.0mm 宽贯通铣槽，
   覆盖整个键区宽度（x 26..311），仅保留：
     - 左右两条边缘脊（x<26 / x>311），作为纵向布线主干
     - 每条槽上 4 个 8mm「布线门」（gateway），用于中部网络下穿
   槽与槽之间没有窄颈，槽两端不落在焊盘/钻孔附近。
2. 网络分配：75 个单键网络按 X 坐标排序后每 8 个一组分配给 10 片 74HC165，
   使每片芯片服务一个纵向窄带，走线以纵向为主，避免长距离横向穿越。
3. 芯片仍位于底部芯片带，不侵入行间净空。
"""
import math

U = 19.05
ORIGIN_X, ORIGIN_Y = 25.0, 40.0
MARGIN_X, MARGIN_BOT = 8.0, 10.0

LAYOUT = [
    # Row0 功能行
    [("Esc", 1), ("F1", 1), ("F2", 1), ("F3", 1), ("F4", 1), ("F5", 1), ("F6", 1),
     ("F7", 1), ("F8", 1), ("F9", 1), ("F10", 1), ("F11", 1), ("F12", 1)],
    # Row1 数字行
    [("`", 1), ("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1),
     ("8", 1), ("9", 1), ("0", 1), ("-", 1), ("=", 1), ("Bksp", 2)],
    # Row2 Q 行
    [("Tab", 1.5), ("Q", 1), ("W", 1), ("E", 1), ("R", 1), ("T", 1), ("Y", 1), ("U", 1),
     ("I", 1), ("O", 1), ("P", 1), ("[", 1), ("]", 1), ("\\", 1.5)],
    # Row3 A 行
    [("Caps", 1.75), ("A", 1), ("S", 1), ("D", 1), ("F", 1), ("G", 1), ("H", 1), ("J", 1),
     ("K", 1), ("L", 1), (";", 1), ("'", 1), ("Enter", 2.25)],
    # Row4 Z 行
    [("LShift", 2.25), ("Z", 1), ("X", 1), ("C", 1), ("V", 1), ("B", 1), ("N", 1), ("M", 1),
     (",", 1), (".", 1), ("/", 1), ("RShift", 1.75), ("Up", 1)],
    # Row5 底行
    [("LCtrl", 1.25), ("LWin", 1.25), ("LAlt", 1.25), ("Space", 8.25),
     ("Fn", 1), ("Left", 1), ("Down", 1), ("Right", 1)],
]

MAX_ROW_U = max(sum(w for _, w in row) for row in LAYOUT)
BOARD_W = ORIGIN_X + MAX_ROW_U * U + MARGIN_X
BOARD_H = ORIGIN_Y + len(LAYOUT) * U + MARGIN_BOT
KEY_FIELD_X0 = ORIGIN_X                     # 25.0
KEY_FIELD_X1 = ORIGIN_X + MAX_ROW_U * U      # 329.8（仅行4/5 到这么远）

# ---------- 键位 ----------
KEYS = []          # dict: n, label, w, cx, cy, row
_n = 0
for _r, _row in enumerate(LAYOUT):
    _cur = 0.0
    _cy = ORIGIN_Y + _r * U
    for _label, _w in _row:
        _cx = ORIGIN_X + (_cur + _w / 2.0) * U
        _n += 1
        KEYS.append(dict(n=_n, label=_label, w=_w, cx=_cx, cy=_cy, row=_r))
        _cur += _w
assert len(KEYS) == 75

KEYS_BY_ROW = {r: [k for k in KEYS if k["row"] == r] for r in range(len(LAYOUT))}

# ---------- 芯片与网络分配 ----------
CHIP_COUNT = 10
IC_Y = ORIGIN_Y + (len(LAYOUT) - 1) * U + 18.25     # 153.5：底部让出 5.8mm 给灯带与横向总线
IC_X0, IC_X1 = ORIGIN_X + 12.0, BOARD_W - 20.0
IC_PITCH = (IC_X1 - IC_X0) / (CHIP_COUNT - 1)
IC_XS = [IC_X0 + i * IC_PITCH for i in range(CHIP_COUNT)]

# 按 cx 排序，每 8 个一组 -> 每片芯片服务一个纵向窄带
_ORDER = sorted(KEYS, key=lambda k: (k["cx"], k["cy"]))
GROUPS = [_ORDER[i * 8:(i + 1) * 8] for i in range(CHIP_COUNT)]

# 网络名仍绑定物理键号，保证 SW01..SW75 / K01..K75 一一对应不变
def key_net(knum):
    return f"K{knum:02d}"

DATA_PINS = ["11", "12", "13", "14", "3", "4", "5", "6"]

# chip_index -> [(pin, keynum)]，空位为 None（接 GND）
CHIP_INPUTS = []
for i in range(CHIP_COUNT):
    row = []
    for j in range(8):
        if j < len(GROUPS[i]):
            row.append((DATA_PINS[j], GROUPS[i][j]["n"]))
        else:
            row.append((DATA_PINS[j], None))
    CHIP_INPUTS.append(row)

# ---------- 开槽 ----------
SLOT_W = 2.0
# 槽覆盖的 X 范围（键区中部），两侧留边缘脊
SLOT_X0, SLOT_X1 = 26.0, 311.0
GATEWAY_W = 8.0
# 每条槽的布线门中心（x）与所在边界
CUT_ROWS = [2, 3, 4, 5]                       # 边界 = 第 r-1 行与第 r 行之间
GATEWAYS = {
    2: [96.0, 168.0, 240.0],
    3: [72.0, 128.0, 184.0, 240.0],
    4: [64.0, 116.0, 168.0, 220.0, 272.0],
    5: [88.0, 120.0, 152.0, 216.0, 248.0, 280.0],   # 载荷 67 网：6 门 x ~14 线
}

def cut_y(r):
    """第 r-1 行与第 r 行之间的边界 Y"""
    return ORIGIN_Y + r * U - U / 2.0

def slot_rects():
    """返回所有开槽矩形 [(x1,y1,x2,y2), ...]，单位 mm。

    每条边界上的槽被 GATEWAYS 切成若干段；段端点与门边界严格对齐，
    不产生任何 <2mm 的窄颈。
    """
    out = []
    for r in CUT_ROWS:
        yc = cut_y(r)
        y1, y2 = yc - SLOT_W / 2.0, yc + SLOT_W / 2.0
        gates = sorted(GATEWAYS[r])
        segs = []
        cur = SLOT_X0
        for gx in gates:
            g1, g2 = gx - GATEWAY_W / 2.0, gx + GATEWAY_W / 2.0
            if g1 - cur > 1.0:
                segs.append((cur, g1))
            cur = g2
        if SLOT_X1 - cur > 1.0:
            segs.append((cur, SLOT_X1))
        for a, b in segs:
            out.append((a, y1, b, y2))
    return out


# ---------- 主控模块：Waveshare ESP32-S3-DEV-KIT-N16R8-M ----------
# 数据来源（2026-11-23 核对）：
#   官方机械图 ESP32-S3-DEV-KIT-N8R8_20260110.dxf / .pdf
#   官方原理图 ESP32-S3-DEV-KIT-N8R8-schematic.pdf（P1/P2 均标注 "Header 22"）
#   官方尺寸标注：板体 63.30 x 25.40，两排排针中心距 21.80，
#                 排针中心距板边 1.80，首针距板端 5.05(左) / 4.91(右)，
#                 四角安装孔 4-Ø2.0（M1.4 螺丝）
# 结论：每排 22 针（不是 20 针），针距 2.54，两排中心距 21.80
MOD_PITCH = 2.54
MOD_PINS_PER_ROW = 22
MOD_ROW_SPACING = 21.80
MOD_LEN, MOD_WID = 63.30, 25.40
MOD_EDGE_TO_PIN = 1.80
MOD_END_MARGIN_USB, MOD_END_MARGIN_ANT = 5.05, 4.91   # 左(USB 端) / 右(天线端)
MOD_HOLE_D = 2.0

MOD_X0 = BOARD_W / 2.0 - MOD_LEN / 2.0        # 137.25：模块左缘（USB 端）
MOD_X1 = MOD_X0 + MOD_LEN                     # 200.55
MOD_Y0 = 4.0 - MOD_EDGE_TO_PIN                # 2.20：模块上缘
MOD_Y1 = MOD_Y0 + MOD_WID                     # 27.60
P1_Y, P2_Y = MOD_Y0 + MOD_EDGE_TO_PIN, MOD_Y0 + MOD_EDGE_TO_PIN + MOD_ROW_SPACING   # 4.0 / 25.8
# 模块 pin 1 在天线端（3V3），引脚号自右向左递增
PIN1_X = MOD_X1 - MOD_END_MARGIN_ANT          # 195.64


def mod_pin_x(n):
    """模块第 n 针的世界 X 坐标（n=1 在最右）"""
    return PIN1_X - (n - 1) * MOD_PITCH


MOD_HOLES = [(MOD_X0 + MOD_EDGE_TO_PIN, P1_Y), (MOD_X1 - MOD_EDGE_TO_PIN, P1_Y),
             (MOD_X0 + MOD_EDGE_TO_PIN, P2_Y), (MOD_X1 - MOD_EDGE_TO_PIN, P2_Y)]

# 引脚定义 = (丝印标签, 网络名或 None)
# P1 自上排左->右的丝印：G 5V 14 13 12 11 10 9 46 3 8 18 17 16 15 7 6 5 4 RST 3V3 3V3
# P2 自下排左->右的丝印：G G 19 20 21 47 48 45 0 35 36 37 38 39 40 41 42 2 1 RX TX G
P1_PINOUT = {
    1: ("3V3", "VCC"), 2: ("3V3", "VCC"), 3: ("RST", None),
    4: ("4", "CLK"), 5: ("5", "SH_LD"), 6: ("6", "CHAIN_10"),
    7: ("7", "ENC_A"), 8: ("15", "ENC_B"), 9: ("16", "ENC_SW"),
    10: ("17", "LED_DATA"),
    11: ("18", None), 12: ("8", None), 13: ("3", None), 14: ("46", None),
    15: ("9", None), 16: ("10", None), 17: ("11", None), 18: ("12", None),
    19: ("13", None), 20: ("14", None),
    21: ("5V", "V5"), 22: ("G", "GND"),
}
P2_PINOUT = {
    1: ("G", "GND"),
    2: ("TX", None), 3: ("RX", None), 4: ("1", None), 5: ("2", None),
    6: ("42", None), 7: ("41", None), 8: ("40", None), 9: ("39", None),
    10: ("38", None),           # 板上 WS2812B 占用，勿用
    11: ("37", None), 12: ("36", None), 13: ("35", None),   # WROOM-1 上为 NC
    14: ("0", None), 15: ("45", None), 16: ("48", None), 17: ("47", None),
    18: ("21", None), 19: ("20", "USB_D+"), 20: ("19", "USB_D-"),
    21: ("G", "GND"), 22: ("G", "GND"),
}


# ---------- 预留灯光：板边 underglow ----------
LED_COUNT = 20
LED_Y = 161.4                 # 底边灯带中心（B.Cu）
LED_X0, LED_X1 = 26.0, 315.0
LED_PITCH = (LED_X1 - LED_X0) / (LED_COUNT - 1)
LED_XS = [LED_X0 + i * LED_PITCH for i in range(LED_COUNT)]
# 焊盘几何对齐官方库 LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm（±1.75 / ±0.875，焊盘 1.6x0.85）
LED_PAD_DX, LED_PAD_DY = 1.75, 0.875
# pad1=VDD(5V) 2=DOUT 3=GND 4=DIN  (SK6812MINI-E)
LED_NET_VDD = "V5"
LED_NET_GND = "GND"


def led_net_out(i):
    """第 i 颗灯的 DOUT 网络名；最后一颗输出到测试点"""
    return f"LED_D{i}"


LED_IN_NET = "LED_DATA"       # 来自 J_P1.9 (GPIO17)
