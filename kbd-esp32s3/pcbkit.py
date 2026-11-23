#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KiCad S 表达式读写工具（保留字符串引号语义）"""
import re


class Str(str):
    """标记为带引号的字符串"""
    __slots__ = ()


_TOKEN_RE = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text):
    stack = [[]]
    for m in _TOKEN_RE.finditer(text):
        lp, rp, s, atom = m.groups()
        if lp:
            stack.append([])
        elif rp:
            node = stack.pop()
            stack[-1].append(node)
        elif s is not None:
            stack[-1].append(Str(s))
        elif atom is not None:
            stack[-1].append(atom)
    return stack[0]


def _emit(node, out, indent, pretty):
    if not isinstance(node, list):
        if isinstance(node, Str):
            out.append('"' + node.replace('\\', '\\\\').replace('"', '\\"') + '"')
        else:
            out.append(node)
        return
    out.append('(')
    first = True
    for i, child in enumerate(node):
        if i == 0:
            _emit(child, out, indent, pretty)
            first = False
            continue
        if pretty and (isinstance(child, list) or True):
            out.append('\n' + '\t' * indent)
        else:
            out.append(' ')
        _emit(child, out, indent + 1, pretty)
    out.append(')')


def dumps(node, pretty=True, indent=1):
    out = []
    _emit(node, out, indent, pretty)
    return ''.join(out)


def find_all(node, kw):
    return [c for c in node if isinstance(c, list) and c and c[0] == kw]


def get(node, kw):
    for c in node:
        if isinstance(c, list) and c and c[0] == kw:
            return c
    return None


def get_all(node, kw):
    return [c for c in node if isinstance(c, list) and c and c[0] == kw]


def set_child(node, kw, new):
    """替换或追加子节点"""
    for i, c in enumerate(node):
        if isinstance(c, list) and c and c[0] == kw:
            node[i] = new
            return new
    node.append(new)
    return new


def f(x):
    return float(x)
