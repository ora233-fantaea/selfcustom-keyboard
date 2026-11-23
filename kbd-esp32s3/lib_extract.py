#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""符号提取与引脚解析工具，供 gen_sch.py 使用"""
import re, os

SYM_DIR = "/usr/share/kicad/symbols"

def _top_symbol_block(libfile, symname):
    s = open(os.path.join(SYM_DIR, libfile), encoding="utf-8").read()
    m = re.search(r'\t\(symbol "' + re.escape(symname) + r'"', s)
    if not m:
        raise RuntimeError(f"符号未找到: {symname} @ {libfile}")
    i = m.start() + 1
    depth = 0
    for j in range(i, len(s)):
        if s[j] == '(': depth += 1
        elif s[j] == ')':
            depth -= 1
            if depth == 0:
                return s[i:j+1]
    raise RuntimeError("符号块不完整")

def get_symbol(libid, libfile, symname, rename_to=None, force_value=None):
    """返回 (libid, 完整定义块, 引脚列表[(num,name,x,y,angle)])"""
    block = _top_symbol_block(libfile, symname)
    # 若 extends，展开父符号
    ext = re.search(r'\(extends "([^"]+)"', block)
    if ext:
        parent = ext.group(1)
        block = _top_symbol_block(libfile, parent)
        # 用目标符号名重命名：顶层名 + 所有子单元名(父名_后缀)
        target = rename_to or symname
        # 子单元形如 "74LS165_1_0" / "74LS165_0_1"
        block = re.sub(r'"' + re.escape(parent) + r'(_\d+_\d+)"',
                       lambda m: '"' + target + m.group(1) + '"', block)
        # 顶层符号名
        block = re.sub(r'\(symbol "' + re.escape(parent) + r'"',
                       f'(symbol "{target}"', block, count=1)
        # 更新 Value 属性
        if force_value:
            block = re.sub(r'(\(property "Value" )"[^"]*"', rf'\1"{force_value}"', block, count=1)
    # 重命名为带库前缀的 lib_id
    block = re.sub(r'\(symbol "[^"]+"', f'(symbol "{libid}"', block, count=1)
    pins = parse_pins(block)
    return libid, block, pins

def parse_pins(block):
    """解析符号块内所有引脚，返回 [(number, name, x, y, angle)]（符号局部坐标，y向上为正）"""
    pins = []
    # 逐个提取 (pin ...) 块
    for m in re.finditer(r'\(pin\s+\w+\s+\w+', block):
        i = m.start()
        depth = 0
        for j in range(i, len(block)):
            if block[j] == '(': depth += 1
            elif block[j] == ')':
                depth -= 1
                if depth == 0:
                    pb = block[i:j+1]; break
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)', pb)
        num = re.search(r'\(number\s+"([^"]+)"', pb)
        name = re.search(r'\(name\s+"([^"]+)"', pb)
        if at and num and name:
            pins.append((num.group(1), name.group(1),
                         float(at.group(1)), float(at.group(2)), float(at.group(3))))
    return pins

if __name__ == "__main__":
    for libid, lf, sn, rn in [
        ("Device_74HC:74HC165", "74xx.kicad_sym", "74HC165", "74HC165"),
        ("Switch:SW_Push", "Switch.kicad_sym", "SW_Push", None),
        ("Device:R", "Device.kicad_sym", "R", None),
        ("Device:C", "Device.kicad_sym", "C", None),
        ("power:VCC", "power.kicad_sym", "VCC", None),
        ("power:GND", "power.kicad_sym", "GND", None),
        ("Connector_Generic:Conn_01x10", "Connector_Generic.kicad_sym", "Conn_01x10", None),
        ("Connector_Generic:Conn_01x04", "Connector_Generic.kicad_sym", "Conn_01x04", None),
    ]:
        lid, blk, pins = get_symbol(libid, lf, sn, rename_to=rn, force_value="74HC165" if rn else None)
        print(f"{libid}: {len(pins)} 引脚 -> {[(p[0],p[1],p[2],p[3]) for p in pins]}")
