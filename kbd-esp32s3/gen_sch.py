#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 ESP32-S3 客制化键盘原理图：74HC165 级联读键（非矩阵方案）
"""
import uuid
from lib_extract import get_symbol

def uid():
    return str(uuid.uuid4())

# ============ 1. 提取符号 ============
SYMS = {}
def add(libid, lf, sn, rename=None, fval=None):
    lid, block, pins = get_symbol(libid, lf, sn, rename_to=rename, force_value=fval)
    SYMS[libid] = (block, pins)
    return pins

add("74xx:74HC165", "74xx.kicad_sym", "74HC165", "74HC165", "74HC165")
add("Switch:SW_Push", "Switch.kicad_sym", "SW_Push")
add("Device:R", "Device.kicad_sym", "R")
add("Device:C", "Device.kicad_sym", "C")
add("power:VCC", "power.kicad_sym", "VCC")
add("power:GND", "power.kicad_sym", "GND")
add("power:PWR_FLAG", "power.kicad_sym", "PWR_FLAG")
add("Device:RotaryEncoder_Switch", "Device.kicad_sym", "RotaryEncoder_Switch")
add("Connector_Generic:Conn_01x10", "Connector_Generic.kicad_sym", "Conn_01x10")
add("Connector_Generic:Conn_01x04", "Connector_Generic.kicad_sym", "Conn_01x04")

# lib_symbols 段
lib_symbols = "\n".join("\t\t" + blk.replace("\n", "\n\t\t") for blk, _ in SYMS.values())

# ============ 2. 元件实例 ============
instances = []
net_labels = []   # (label, x, y)
no_connects = []  # (x, y) 悬空引脚标记

def add_symbol(libid, ref, value, x, y, footprint="", pins_map=None):
    """放置符号实例。pins_map: {pin_num: net_name} 用于生成引脚标签"""
    block, pins = SYMS[libid]
    inst_uuid = uid()
    pin_uuids = "\n".join(f'\t\t\t(pin "{p[0]}"\n\t\t\t\t(uuid "{uid()}"))' for p in pins)
    props = ""
    for pname, pval in [("Reference", ref), ("Value", value), ("Footprint", footprint), ("Datasheet", "")]:
        py = y + (6 if pname == "Reference" else -6)
        props += f'''\t\t\t(property "{pname}" "{pval}"
\t\t\t\t(at {x} {py} 0)
\t\t\t\t(effects (font (size 1.27 1.27)){' (hide yes)' if pname in ('Footprint','Datasheet') else ''})
\t\t\t)
'''
    s = f'''\t(symbol
\t\t(lib_id "{libid}")
\t\t(at {x} {y} 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "{inst_uuid}")
{props}{pin_uuids}
\t\t(instances
\t\t\t(project "kbd-esp32s3"
\t\t\t\t(path "/{ROOT_UUID}"
\t\t\t\t\t(reference "{ref}")
\t\t\t\t\t(unit 1)
\t\t\t\t)
\t\t\t)
\t\t)
)'''
    instances.append(s)
    # 生成引脚标签（放在引脚连接点：符号y轴向上，原理图向下取负）
    if pins_map:
        for p in pins:
            num, name, px, py, ang = p
            ax = x + px
            ay = y - py
            if num in pins_map and pins_map[num]:
                net_labels.append((pins_map[num], ax, ay))
            elif num in pins_map and pins_map[num] is None:
                # None 表示该引脚明确悬空，加 no_connect
                no_connects.append((ax, ay))

def add_label(net, x, y):
    net_labels.append((net, x, y))

# ============ 3. 布局设计 ============
ROOT_UUID = uid()

# 纸张 A3 (420 x 297)，坐标范围 x:0-420, y:0-297
# 10 片 74HC165 分两行，每行 5 片，横向排列
# 每片 8 键

KEY_COUNT = 75
CHIPS = 10

# 74HC165 起始位置（两行）
chip_positions = []
for i in range(CHIPS):
    row = i // 5
    col = i % 5
    # 所有坐标对齐到 1.27mm 网格（0.254 的整数倍），消除 ERC off_grid
    cx = 76.2 + col * 63.5
    cy = 76.2 + row * 152.4
    chip_positions.append((cx, cy))

# 生成按键编号 -> 网络名映射
def key_net(n):
    return f"K{n:02d}"

# 每片的 8 个输入引脚（D0:D7 对应 pin 11,12,13,14,3,4,5,6）
DATA_PINS = ["11", "12", "13", "14", "3", "4", "5", "6"]

key_idx = 1
for i, (cx, cy) in enumerate(chip_positions):
    ref = f"U{i+1}"
    # 该片的引脚->网络映射
    pmap = {
        "1": "SH_LD",     # PL
        "2": "CLK",       # CP
        "15": "GND",      # CE 低有效，接地使能
        "16": "VCC",
        "8": "GND",
        # 级联：第 i 片的 DS 接第 (i-1) 片的 Q7，共用网络 CHAIN_i；第0片 DS 接地
        "10": f"CHAIN_{i}" if i > 0 else "GND",
        "9": f"CHAIN_{i+1}",  # Q7 输出，最后一片 CHAIN_10 -> ESP32 DATA
        "7": None,            # ~Q7 反相输出不用，明确悬空
        # 空余输入接地
    }
    # 8 个数据输入
    for j, pin in enumerate(DATA_PINS):
        if key_idx <= KEY_COUNT:
            pmap[pin] = key_net(key_idx)
            key_idx += 1
        else:
            pmap[pin] = "GND"  # 空余固定低电平
    add_symbol("74xx:74HC165", ref, "74HC165", cx, cy,
               "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm", pmap)

    # 该片的 100nF 去耦电容（放在 VCC/GND 附近）
    capx = cx + 19.05
    capy = cy - 20.32
    add_symbol("Device:C", f"C{i+1}", "100nF", capx, capy,
               "Capacitor_SMD:C_0603_1608Metric",
               {"1": "VCC", "2": "GND"})
    # 电源符号
    add_symbol("power:VCC", f"#PWRV{i+1}", "VCC", capx, capy + 7.62, "", {"1": "VCC"})
    add_symbol("power:GND", f"#PWRG{i+1}", "GND", capx, capy - 7.62, "", {"1": "GND"})

    # 8 个按键 + 上拉电阻（放在芯片左侧）
    for j in range(8):
        knum = i * 8 + j + 1
        if knum > KEY_COUNT:
            break
        ky = cy + 12.7 - j * 5.08   # 竖直排布，3.81=1.27×3，网格对齐
        kx = cx - 30.48
        # 上拉电阻：一端 VCC，一端 KEY
        add_symbol("Device:R", f"R{knum}", "10k", kx - 6.35, ky,
                   "Resistor_SMD:R_0603_1608Metric",
                   {"1": "VCC", "2": key_net(knum)})
        # 按键：一端 KEY，一端 GND
        add_symbol("Switch:SW_Push", f"SW{knum}", f"KEY{knum}", kx + 6.35, ky,
                   "Button_Switch_Keyboard:SW_Cherry_MX_1.00u_PCB",
                   {"1": key_net(knum), "2": "GND"})

# 级联链：前级 Q7 -> 后级 DS (CHAIN_IN)
# 用全局标签：CHAIN_OUT_n 连接到下一片的 CHAIN_IN
# 需要把每片的 CHAIN_OUT 与下一片的 CHAIN_IN 用同名网络；
# 这里简化：所有中间节点用唯一网络 CHAIN_n
for i in range(CHIPS - 1):
    add_label(f"CHAIN_{i+1}", chip_positions[i][0] + 12.7, chip_positions[i][1] - 15.24)
    add_label(f"CHAIN_{i+1}", chip_positions[i+1][0] - 12.7, chip_positions[i+1][1] - 15.24)

# 修正：上面 Q7->DS 用 CHAIN_n，但 add_symbol 里已给 Q7=CHAIN_OUT_n、DS=CHAIN_IN
# 为简化，改用统一策略：把所有 CHAIN_OUT_n 与 CHAIN_{n} 视为不同网络是不连通的。
# 因此这里重新用 wire 连接更可靠的做法见下：直接让 Q7 与下一片 DS 同名。
# —— 由于 add_symbol 已固定标签，我们改为在后面用 wires 连接实际引脚坐标。

# ============ 4. 连接器：ESP32 接口 & 编码器接口 ============
# ESP32 接口 (10pin): CLK, SH_LD, DATA(CHAIN_OUT_10), VCC, GND, ENC_A, ENC_B, ENC_SW, 3V3, GND
add_symbol("Connector_Generic:Conn_01x04", "J_ESP32_A", "ESP32-CTRL",
           20.32, 60.96, "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
           {"1": "CLK", "2": "SH_LD", "3": "CHAIN_10", "4": "GND"})
add_symbol("Connector_Generic:Conn_01x04", "J_ESP32_B", "ESP32-ENC",
           20.32, 101.6, "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
           {"1": "ENC_A", "2": "ENC_B", "3": "ENC_SW", "4": "VCC"})

# EC11 带按压编码器本体
add_symbol("Device:RotaryEncoder_Switch", "ENC1", "EC11-Encoder",
           45.72, 109.22, "Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm",
           {"A": "ENC_A", "B": "ENC_B", "C": "GND", "S1": "ENC_SW", "S2": "GND"})

# ============ 5. PWR_FLAG（满足 ERC 电源驱动检查）============
add_symbol("power:PWR_FLAG", "#FLG_VCC", "PWR_FLAG", 50.8, 41.91, "", {"1": "VCC"})
add_symbol("power:PWR_FLAG", "#FLG_GND", "PWR_FLAG", 50.8, 58.42, "", {"1": "GND"})

# ============ 6. 普通标签（引脚连线）============
labels_s = "\n".join(
    f'''\t(label "{net}"
\t\t(at {x} {y} 0)
\t\t(effects (font (size 1.016 1.016)) (justify left bottom))
\t\t(uuid "{uid()}")
\t)''' for net, x, y in net_labels
)

# ============ 6b. no_connect 标记 ============
nc_s = "\n".join(
    f'''\t(no_connect
\t\t(at {x} {y})
\t\t(uuid "{uid()}")
\t)''' for x, y in no_connects
)

# ============ 7. 组装 sch ============
body = "\n".join(instances) + "\n" + labels_s + "\n" + nc_s
sch = f'''(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "{ROOT_UUID}")
\t(paper "A3")
\t(lib_symbols
{lib_symbols}
\t)
''' + body + '''
\t(embedded_fonts no)
)'''

open("kbd-esp32s3.kicad_sch", "w", encoding="utf-8").write(sch)
print(f"原理图已生成: 元件 {len(instances)} 个(含标签), 引脚标签 {len(net_labels)} 个")
print(f"按键: {KEY_COUNT}, 74HC165: {CHIPS} 片")
