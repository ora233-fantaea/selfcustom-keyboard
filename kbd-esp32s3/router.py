#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双层栅格 A* 布线器（0.2mm 栅格，0.2mm 线宽，0.2mm 间距）

- 障碍：焊盘(按铜层)、NPTH 钻孔、Edge.Cuts 开槽、板边
- 同层移动代价 1，换层(过孔)代价 24
- 已布走线在栅格上按 1 格(0.2mm)外扩占用，保证线间距 >= 0.2mm
"""
import heapq
import math
import numpy as np

GRID = 0.2
CLEAR = 0.2
TRACE_W = 0.2
VIA_COST = 24.0
INFLATE = CLEAR + TRACE_W / 2.0      # 0.3mm


class Grid:
    def __init__(self, w, h):
        self.nx = int(round(w / GRID)) + 1
        self.ny = int(round(h / GRID)) + 1
        self.blocked = np.zeros((2, self.ny, self.nx), dtype=bool)
        self.w, self.h = w, h

    def ix(self, x):
        return int(round(x / GRID))

    def iy(self, y):
        return int(round(y / GRID))

    def _rect(self, layer, x1, y1, x2, y2):
        i0, i1 = self.ix(x1), self.ix(x2)
        j0, j1 = self.iy(y1), self.iy(y2)
        i0 = max(0, i0); j0 = max(0, j0)
        i1 = min(self.nx - 1, i1); j1 = min(self.ny - 1, j1)
        if i1 >= i0 and j1 >= j0:
            self.blocked[layer, j0:j1 + 1, i0:i1 + 1] = True

    def rect(self, x1, y1, x2, y2, layers=(0, 1), pad=0.0):
        for L in layers:
            self._rect(L, x1 - pad, y1 - pad, x2 + pad, y2 + pad)

    def disc(self, cx, cy, r, layers=(0, 1), value=True):
        i0, i1 = self.ix(cx - r), self.ix(cx + r)
        j0, j1 = self.iy(cy - r), self.iy(cy + r)
        for L in layers:
            for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
                yy = (j * GRID - cy)
                for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                    xx = (i * GRID - cx)
                    if xx * xx + yy * yy <= r * r:
                        self.blocked[L, j, i] = value

    def margin(self, m):
        self.blocked[:, :max(0, self.iy(m)), :] = True
        self.blocked[:, min(self.ny, self.iy(self.h - m)):, :] = True
        self.blocked[:, :, :max(0, self.ix(m))] = True
        self.blocked[:, :, min(self.nx, self.ix(self.w - m)):] = True

    # ---------------- A* ----------------
    def _init_astar(self):
        if not hasattr(self, "_g"):
            self._g = np.full((2, self.ny, self.nx), np.inf, dtype=np.float32)
            self._stamp = np.zeros((2, self.ny, self.nx), dtype=np.int32)
            self._came = np.full((2, self.ny, self.nx), -1, dtype=np.int64)
            self._mark = 0

    def astar(self, start, goal, budget=200_000, occupied=None, margin_mm=14.0):
        """start/goal = (x, y, layer) 世界坐标(mm)；返回节点列表或 None"""
        self._init_astar()
        self._mark += 1
        mk = self._mark
        sx, sy, sl = self.ix(start[0]), self.iy(start[1]), start[2]
        gx, gy, gl = self.ix(goal[0]), self.iy(goal[1]), goal[2]
        nx, ny = self.nx, self.ny
        if not (0 <= sx < nx and 0 <= sy < ny and 0 <= gx < nx and 0 <= gy < ny):
            return None

        # 搜索框
        m = int(round(margin_mm / GRID))
        bx0 = max(0, min(sx, gx) - m); bx1 = min(nx - 1, max(sx, gx) + m)
        by0 = max(0, min(sy, gy) - m); by1 = min(ny - 1, max(sy, gy) + m)

        g_arr, st_arr, cm_arr = self._g, self._stamp, self._came
        blk = self.blocked
        occ = occupied if occupied is not None else self.blocked

        def k(L, y, x):
            return (L * ny + y) * nx + x

        sidx = k(sl, sy, sx)
        g_arr[sl, sy, sx] = 0.0
        st_arr[sl, sy, sx] = mk
        cm_arr[sl, sy, sx] = -1
        pq = [(abs(sx - gx) + abs(sy - gy), 0.0, sl, sy, sx)]
        n = 0
        while pq:
            f, g, L, y, x = heapq.heappop(pq)
            if st_arr[L, y, x] != mk or g > g_arr[L, y, x] + 1e-6:
                continue
            if L == gl and y == gy and x == gx:
                # 回溯
                path = []
                cy_, cx_, cl_ = y, x, L
                while True:
                    path.append((cx_, cy_, cl_))
                    pidx = cm_arr[cl_, cy_, cx_]
                    if pidx < 0:
                        break
                    cl_, rem = divmod(pidx, ny * nx)
                    cy_, cx_ = divmod(rem, nx)
                return path[::-1]
            n += 1
            if n > budget:
                return None
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ax, ay = x + dx, y + dy
                if ax < bx0 or ax > bx1 or ay < by0 or ay > by1:
                    continue
                if blk[L, ay, ax] or occ[L, ay, ax]:
                    continue
                ng = g + 1.0
                if st_arr[L, ay, ax] != mk or ng < g_arr[L, ay, ax]:
                    st_arr[L, ay, ax] = mk
                    g_arr[L, ay, ax] = ng
                    cm_arr[L, ay, ax] = k(L, y, x)
                    heapq.heappush(pq, (ng + abs(ax - gx) + abs(ay - gy), ng, L, ay, ax))
            ol = 1 - L
            if not blk[ol, y, x] and not occ[ol, y, x]:
                ng = g + VIA_COST
                if st_arr[ol, y, x] != mk or ng < g_arr[ol, y, x]:
                    st_arr[ol, y, x] = mk
                    g_arr[ol, y, x] = ng
                    cm_arr[ol, y, x] = k(L, y, x)
                    heapq.heappush(pq, (ng + abs(x - gx) + abs(y - gy), ng, ol, y, x))
        return None

    def occupy(self, path, layer_by_node=True, pad=1):
        """把路径标记为占用（对同层外扩 pad 格）"""
        for (x, y, L) in path:
            i0, i1 = max(0, x - pad), min(self.nx - 1, x + pad)
            j0, j1 = max(0, y - pad), min(self.ny - 1, y + pad)
            self.blocked[L, j0:j1 + 1, i0:i1 + 1] = True


def path_to_geom(grid, path):
    """把栅格路径转成 [(layer, [(x,y),...]), ...] 与过孔列表"""
    groups = []
    vias = []
    cur_layer = path[0][2]
    pts = [(path[0][0] * GRID, path[0][1] * GRID)]
    prev = path[0]
    for node in path[1:]:
        if node[2] != cur_layer:
            groups.append((cur_layer, pts))
            vias.append((prev[0] * GRID, prev[1] * GRID))
            cur_layer = node[2]
            pts = [(node[0] * GRID, node[1] * GRID)]
        else:
            pts.append((node[0] * GRID, node[1] * GRID))
        prev = node
    groups.append((cur_layer, pts))

    # 合并共线点
    out = []
    for L, ps in groups:
        simp = [ps[0]]
        for i in range(1, len(ps) - 1):
            ax, ay = simp[-1]
            bx, by = ps[i]
            cx_, cy_ = ps[i + 1]
            if (bx - ax) * (cy_ - by) - (by - ay) * (cx_ - bx) == 0:
                continue
            simp.append(ps[i])
        simp.append(ps[-1])
        out.append((L, simp))
    return out, vias
