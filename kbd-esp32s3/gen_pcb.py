#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新生成 kbd-esp32s3 PCB：新开槽方案 + 空间化网络分配

封装几何直接从旧版 kbd-esp32s3.kicad_pcb 中复用（保证与定位板/卫星轴一致），
不依赖 KiCad 库，也不需要 pcbnew。旧版生成器保留为 gen_pcb_v1_legacy.py。
"""
import copy
import os
import uuid
import json

import pcbkit as K
import kbd_design as D

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "kbd-esp32s3_v1_template.kicad_pcb")


def load_templates():
    root = K.parse(open(SRC, encoding="utf-8").read())[0]
    tpl = {}
    for fp in K.find_all(root, "footprint"):
        lib = fp[1]
        if lib not in tpl:
            tpl[lib] = copy.deepcopy(fp)
    return root, tpl


def strip_fp(fp):
    for c in K.get_all(fp, "uuid"):
        fp.remove(c)
    for pad in K.get_all(fp, "pad"):
        n = K.get(pad, "net")
        if n is not None:
            pad.remove(n)
        for c in K.get_all(pad, "uuid"):
            pad.remove(c)
    for p in K.get_all(fp, "property"):
        for c in K.get_all(p, "uuid"):
            p.remove(c)
    return fp


ROOT, TPL = load_templates()


def new_uuid():
    return K.Str(str(uuid.uuid4()))


# ---------------------------------------------------------------- 网络表
NETS = [""]
NET_ID = {"": 0}


def add_net(name):
    if name not in NET_ID:
        NET_ID[name] = len(NETS)
        NETS.append(name)
    return NET_ID[name]


for k in D.KEYS:
    add_net(D.key_net(k["n"]))
for extra in (["GND", "VCC", "CLK", "SH_LD"] + [f"CHAIN_{i}" for i in range(1, 11)]
              + ["ENC_A", "ENC_B", "ENC_SW", "USB_D+", "USB_D-"]):
    add_net(extra)


# ---------------------------------------------------------------- 板对象
BOARD = ["kicad_pcb", ["version", "20250114"], ["generator", "pcbnew"],
         ["generator_version", "9.0"],
         ["general", ["thickness", "1.6"], ["legacy_teardrops", "no"]],
         ["paper", "A3"]]
for kw in ("layers", "setup"):
    node = K.get(ROOT, kw)
    if node is not None:
        BOARD.append(copy.deepcopy(node))

BOARD.append(["net", "0", K.Str("")])
for i, nm in enumerate(NETS):
    if i:
        BOARD.append(["net", str(i), K.Str(nm)])


def place(lib, ref, value, x, y, rot=0, pad_nets=None):
    fp = strip_fp(copy.deepcopy(TPL[lib]))
    new_at = ["at", f"{x:.4f}", f"{y:.4f}"]
    if rot:
        new_at.append(f"{rot:g}")
    K.set_child(fp, "at", new_at)
    fp.append(["uuid", new_uuid()])

    for p in K.get_all(fp, "property"):
        if p[1] == "Reference":
            p[2] = K.Str(ref)
        elif p[1] == "Value":
            p[2] = K.Str(value)
    for t in K.get_all(fp, "fp_text"):
        if t[1] == "reference":
            t[2] = K.Str(ref)
        elif t[1] == "value":
            t[2] = K.Str(value)

    if pad_nets:
        for pad in K.get_all(fp, "pad"):
            num = pad[1]
            if num in pad_nets:
                nm = pad_nets[num]
                if nm:
                    K.set_child(pad, "net", ["net", str(NET_ID[nm]), K.Str(nm)])
    BOARD.append(fp)
    return fp


# ---- 75 轴座 ----
for k in D.KEYS:
    kn = D.key_net(k["n"])
    place("SW_MX_HotSwap_PTH", f"SW{k['n']:02d}", k["label"], k["cx"], k["cy"], 0,
          {"1": kn, "2": "GND"})

# ---- 10 片 74HC165 + 去耦 + 上拉（上拉集中到芯片旁，把行间净空全部让给布线）----
for i in range(D.CHIP_COUNT):
    pmap = {"1": "SH_LD", "2": "CLK", "15": "GND", "16": "VCC", "8": "GND",
            "10": ("GND" if i == 0 else f"CHAIN_{i}"),
            "9": f"CHAIN_{i+1}", "7": None}
    for pin, knum in D.CHIP_INPUTS[i]:
        pmap[pin] = D.key_net(knum) if knum else "GND"
    place("SOIC-16W_7.5x10.3mm_P1.27mm", f"U{i+1}", "74HC165", D.IC_XS[i], D.IC_Y, 0, pmap)
    place("C_0603_1608Metric", f"C{i+1}", "100nF", D.IC_XS[i] + 12.0, D.IC_Y - 1.0, 0,
          {"1": "VCC", "2": "GND"})
    # 该片 8 路输入的上拉：2 行 × 4 列，压在芯片正上方
    for j, (pin, knum) in enumerate(D.CHIP_INPUTS[i]):
        if knum is None:
            continue
        rx = D.IC_XS[i] - 4.35 + (j % 4) * 2.90
        ry = D.IC_Y - 9.55 + (j // 4) * 2.40
        place("R_0603_1608Metric", f"R{knum:02d}", "10k", rx, ry, 0,
              {"1": "VCC", "2": D.key_net(knum)})

# ---- 排针 / 编码器 / USB ----
HDR_PIN1_X = D.BOARD_W / 2 - 24
place("PinHeader_1x20_P2.54mm_Vertical", "J_P1", "DEV-KIT-P1", HDR_PIN1_X, 4.0, 90,
      {"1": "VCC", "3": "CLK", "4": "SH_LD", "5": "CHAIN_10",
       "6": "ENC_A", "7": "ENC_B", "8": "ENC_SW"})
place("PinHeader_1x20_P2.54mm_Vertical", "J_P2", "DEV-KIT-P2", HDR_PIN1_X, 25.8, 90,
      {"1": "GND"})
place("RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm", "ENC1", "EC11",
      D.BOARD_W - 20, D.ORIGIN_Y + 8, 0,
      {"A": "ENC_A", "B": "ENC_B", "C": "GND", "S1": "ENC_SW", "S2": "GND"})
place("USB_C_Receptacle_GCT_USB4085", "J_USB", "USB-C", 12.0, 16.0, 0,
      {"A4": "VCC", "A9": "VCC", "B4": "VCC", "B9": "VCC",
       "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
       "A6": "USB_D+", "A7": "USB_D-", "B6": "USB_D+", "B7": "USB_D-"})

for hx, hy in [(5, 5), (D.BOARD_W - 5, 5), (5, D.BOARD_H - 5), (D.BOARD_W - 5, D.BOARD_H - 5)]:
    place("MountingHole_3.2mm_M3", f"H{int(hx)}_{int(hy)}", "M3", hx, hy, 0, None)


# ---------------------------------------------------------------- Edge.Cuts
def edge_seg(x1, y1, x2, y2):
    BOARD.append(["gr_line", ["start", f"{x1:.4f}", f"{y1:.4f}"],
                  ["end", f"{x2:.4f}", f"{y2:.4f}"],
                  ["stroke", ["width", "0.1"], ["type", "default"]],
                  ["layer", K.Str("Edge.Cuts")], ["uuid", new_uuid()]])


W, H = D.BOARD_W, D.BOARD_H
edge_seg(0, 0, W, 0); edge_seg(W, 0, W, H)
edge_seg(W, H, 0, H); edge_seg(0, H, 0, 0)

SLOTS = D.slot_rects()
for x1, y1, x2, y2 in SLOTS:
    edge_seg(x1, y1, x2, y1); edge_seg(x2, y1, x2, y2)
    edge_seg(x2, y2, x1, y2); edge_seg(x1, y2, x1, y1)


# ---------------------------------------------------------------- 保存
def write(path, extra_nodes=()):
    for n in extra_nodes:
        BOARD.append(n)
    BOARD.append(["embedded_fonts", "no"])
    txt = K.dumps(BOARD, pretty=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    return path


if __name__ == "__main__":
    out = os.path.join(HERE, "kbd-esp32s3.kicad_pcb")
    write(out)
    print(f"OK -> {out}")
    print(f"  板框 {W:.2f} x {H:.2f} mm | 封装 {len(K.find_all(BOARD, 'footprint'))} 个"
          f" | 开槽段 {len(SLOTS)} 条 | 网络 {len(NETS) - 1} 个")
    json.dump({"slots": SLOTS, "nets": NETS, "ic_xs": D.IC_XS, "ic_y": D.IC_Y},
              open(os.path.join(HERE, "_board_meta.json"), "w"))
