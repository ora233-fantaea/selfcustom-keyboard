#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双层栅格 A* 布线器（0.1mm 栅格 / 0.2mm 线宽 / 0.2mm 间距）

设计原则（2026-11-24 重写）
---------------------------
1. 障碍按**真实几何**栅格化：焊盘用外框、钻孔用圆、开槽与板边用矩形，
   统一外扩 CLEAR + TRACE_W/2，不用「中心点 + 常数偏移」那种近似。
2. 已布走线按**线段距离**占用栅格（不是只标记路径节点），
   外扩量保证异网间距 >= CLEAR。
3. 占用带网络号（int16），同网可以贴着自己走，异网一律不允许。
4. 进入焊盘时只解锁**该焊盘自己的外扩区**（0.3mm），
   不再像旧版那样一次性解锁 pad+0.8mm —— 那是短路的主因。
5. Edge.Cuts（开槽 / 板框）按 EDGE_CLEAR + 线宽一半 外扩，与 KiCad DRC 一致。
"""
import heapq
import time

import numpy as np

NL = 4                     # 铜层数：0=F.Cu 1=In1.Cu 2=In2.Cu 3=B.Cu
SIG = (0, 2, 3)            # 走线层；In1 保留为完整 GND 平面
GRID = 0.1                 # 0.1mm：1.27mm 间距的 SOIC 才有足够通道
HEUR_W = 2.0               # 加权 A*：f = g + W*h，牺牲最优性换搜索速度（路径仍合法）
CLEAR = 0.2                 # 铜-铜间距
TRACE_W = 0.15              # 线宽（信号线，0.2 间距下可省出通道）
VIA_D, VIA_DRILL = 0.6, 0.3
EDGE_CLEAR = 0.5            # 板边/开槽到铜的间距（KiCad 默认）
VIA_COST = 24.0

# 0.2mm 栅格是离散的：外扩量要加一点余量，否则边界格中心可能落在
# 「刚好 0.2」处，被 DRC 判成 0.195 之类
EPS = 0.02
INFLATE = CLEAR + TRACE_W / 2.0 + EPS          # 0.33：铜障碍外扩
OCC_INFLATE = CLEAR + TRACE_W + EPS            # 0.43：走线占用外扩
EDGE_INFLATE = EDGE_CLEAR + TRACE_W / 2.0 + EPS  # 0.63：板边/开槽
HOLE_INFLATE = 0.25 + TRACE_W / 2.0 + EPS      # 0.38：孔-铜间距（KiCad 默认 0.25）
VIA_INFLATE = CLEAR + VIA_D / 2.0 + TRACE_W / 2.0 + EPS   # 走线要绕开过孔铜皮

SQ2 = 2.0 ** 0.5


class Grid:
    def __init__(self, w, h):
        self.nx = int(round(w / GRID)) + 1
        self.ny = int(round(h / GRID)) + 1
        self.w, self.h = w, h
        self.blocked = np.zeros((NL, self.ny, self.nx), dtype=bool)
        self.occ = np.zeros((NL, self.ny, self.nx), dtype=np.int16)
        self.shape_cnt = np.zeros((NL, self.ny, self.nx), dtype=np.uint8)  # 阻挡形状计数
        self.static_blk = np.zeros((NL, self.ny, self.nx), dtype=bool)    # 板边/开槽等静障
        self.own = {}                                                    # id(pad) -> 自身覆盖计数
        self.via_used = np.zeros((NL, self.ny, self.nx), dtype=bool)   # 过孔-过孔最小间距

    # ---------------- 索引 ----------------
    def ix(self, x):
        return int(round(x / GRID))

    def iy(self, y):
        return int(round(y / GRID))

    # ---------------- 栅格化基础 ----------------
    def _slice(self, x1, y1, x2, y2):
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        i0 = max(0, int(np.floor(x1 / GRID + 0.5)))
        i1 = min(self.nx - 1, int(np.ceil(x2 / GRID - 0.5)))
        j0 = max(0, int(np.floor(y1 / GRID + 0.5)))
        j1 = min(self.ny - 1, int(np.ceil(y2 / GRID - 0.5)))
        if i1 < i0:
            i0 = i1 = max(0, min(self.nx - 1, self.ix((x1 + x2) / 2)))
        if j1 < j0:
            j0 = j1 = max(0, min(self.ny - 1, self.iy((y1 + y2) / 2)))
        return i0, i1, j0, j1

    def rect(self, x1, y1, x2, y2, layers=tuple(range(NL)), inflate=0.0, value=True, count=False):
        i0, i1, j0, j1 = self._slice(x1 - inflate, y1 - inflate, x2 + inflate, y2 + inflate)
        for L in layers:
            self.blocked[L, j0:j1 + 1, i0:i1 + 1] = value
            if count:
                self.shape_cnt[L, j0:j1 + 1, i0:i1 + 1] += 1
            elif value:
                self.static_blk[L, j0:j1 + 1, i0:i1 + 1] = True

    def disc(self, cx, cy, r, layers=tuple(range(NL)), inflate=0.0, value=True, count=False):
        R = r + inflate
        i0, i1, j0, j1 = self._slice(cx - R, cy - R, cx + R, cy + R)
        xs = (np.arange(i0, i1 + 1) * GRID - cx)[None, :]
        ys = (np.arange(j0, j1 + 1) * GRID - cy)[:, None]
        m = (xs * xs + ys * ys) <= R * R
        for L in layers:
            sub = self.blocked[L, j0:j1 + 1, i0:i1 + 1]
            sub[m] = value
            if count:
                self.shape_cnt[L, j0:j1 + 1, i0:i1 + 1][m] += 1
            elif value:
                self.static_blk[L, j0:j1 + 1, i0:i1 + 1][m] = True

    def margin(self, m):
        self.blocked[:, :self.iy(m) + 1, :] = True
        self.blocked[:, self.iy(self.h - m):, :] = True
        self.blocked[:, :, :self.ix(m) + 1] = True
        self.blocked[:, :, self.ix(self.w - m):] = True
        self.static_blk[:, :self.iy(m) + 1, :] = True
        self.static_blk[:, self.iy(self.h - m):, :] = True
        self.static_blk[:, :, :self.ix(m) + 1] = True
        self.static_blk[:, :, self.ix(self.w - m):] = True

    # ---------------- 焊盘 ----------------
    def add_pad(self, p, layers, inflate=INFLATE):
        """按外框把焊盘栅格化；有钻孔的再按圆加一圈。

        同时记录每个格子被「本焊盘自身形状」覆盖的次数（own）：
        rect() 是整片 slice 置位、disc() 是圆掩膜——own 必须用与它们
        完全相同的范围，否则边界会差出半格，焊盘被自己 0.03mm 的
        「护城河」封死（open_pad 永远解不开外圈）。
        """
        if not layers:
            return
        w2 = p["w"] / 2.0 + inflate
        h2 = p["h"] / 2.0 + inflate
        # rect 部分：与 self.rect() 同参数同 slice，整片 +1
        ri0, ri1, rj0, rj1 = self._slice(p["x"] - w2, p["y"] - h2, p["x"] + w2, p["y"] + h2)
        i0, i1, j0, j1 = ri0, ri1, rj0, rj1
        disc_info = None
        dr = p.get("drill", 0)
        if dr > 0:
            # disc 部分：与 self.disc() 同 R 同 slice 同掩膜
            R = dr / 2.0 + max(inflate, HOLE_INFLATE)
            di0, di1, dj0, dj1 = self._slice(p["x"] - R, p["y"] - R, p["x"] + R, p["y"] + R)
            xs = (np.arange(di0, di1 + 1) * GRID - p["x"])[None, :]
            ys = (np.arange(dj0, dj1 + 1) * GRID - p["y"])[:, None]
            m = (xs * xs + ys * ys) <= R * R
            disc_info = (di0, di1, dj0, dj1, m)
            i0, i1 = min(i0, di0), max(i1, di1)
            j0, j1 = min(j0, dj0), max(j1, dj1)
        own = np.zeros((NL, j1 - j0 + 1, i1 - i0 + 1), dtype=np.uint8)
        own[:, rj0 - j0:rj1 - j0 + 1, ri0 - i0:ri1 - i0 + 1] += 1
        if disc_info is not None:
            di0, di1, dj0, dj1, m = disc_info
            own[:, dj0 - j0:dj1 - j0 + 1, di0 - i0:di1 - i0 + 1] += m
        self.own[id(p)] = (i0, i1, j0, j1, own)
        self.rect(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2,
                  p["x"] + p["w"] / 2, p["y"] + p["h"] / 2,
                  layers=layers, inflate=inflate, count=True)
        if dr > 0:
            self.disc(p["x"], p["y"], dr / 2.0, layers=tuple(range(NL)),
                      inflate=max(inflate, HOLE_INFLATE), count=True)

    def pad_window(self, p, layers, inflate=INFLATE):
        """该焊盘「自己的」外扩区；只在这里解锁，避免波及邻居焊盘"""
        return self._slice(p["x"] - p["w"] / 2 - inflate, p["y"] - p["h"] / 2 - inflate,
                           p["x"] + p["w"] / 2 + inflate, p["y"] + p["h"] / 2 + inflate)

    def add_pad_group(self, items, key, inflate=INFLATE):
        """同一焊盘号的多重几何（贴片 + 桥接 + 通孔）当成**一个**焊盘解锁。

        本板 1164 个焊盘记录只对应 707 个 (ref,num)：按键封装的一个触点
        由 3 个重叠形状组成。若各自记 own，shape_cnt 会累加到 3，而每个
        own 只有 1，open_pad 的 cnt==om 永远不成立 —— 焊盘谁也进不去。
        所有 SW 焊盘都是这种，所以 SW->IC 一条都布不通，而单形状的
        IC / 电阻焊盘却完全正常。这是「布线永远差最后一公里」的真根因。
        """
        recs = []
        for p, layers in items:
            if not layers:
                continue
            w2 = p["w"] / 2.0 + inflate
            h2 = p["h"] / 2.0 + inflate
            ri = self._slice(p["x"] - w2, p["y"] - h2, p["x"] + w2, p["y"] + h2)
            din = None
            dr = p.get("drill", 0)
            if dr > 0:
                R = dr / 2.0 + max(inflate, HOLE_INFLATE)
                di = self._slice(p["x"] - R, p["y"] - R, p["x"] + R, p["y"] + R)
                xs = (np.arange(di[0], di[1] + 1) * GRID - p["x"])[None, :]
                ys = (np.arange(di[2], di[3] + 1) * GRID - p["y"])[:, None]
                din = (di, (xs * xs + ys * ys) <= R * R)
            recs.append((p, layers, ri, din))
        if not recs:
            return
        i0 = i1 = j0 = j1 = None
        for _, _, ri, din in recs:
            for a, b in ((ri[0], ri[1]),):
                i0 = a if i0 is None else min(i0, a)
                i1 = b if i1 is None else max(i1, b)
            j0 = ri[2] if j0 is None else min(j0, ri[2])
            j1 = ri[3] if j1 is None else max(j1, ri[3])
            if din:
                di = din[0]
                i0, i1 = min(i0, di[0]), max(i1, di[1])
                j0, j1 = min(j0, di[2]), max(j1, di[3])
        own = np.zeros((NL, j1 - j0 + 1, i1 - i0 + 1), dtype=np.uint8)
        for _, _, ri, din in recs:
            own[:, ri[2] - j0:ri[3] - j0 + 1, ri[0] - i0:ri[1] - i0 + 1] += 1
            if din:
                di, m = din
                own[:, di[2] - j0:di[3] - j0 + 1, di[0] - i0:di[1] - i0 + 1] += m
        self.own[key] = (i0, i1, j0, j1, own)
        for p, layers, ri, din in recs:
            p["_gk"] = key
            self.rect(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2,
                      p["x"] + p["w"] / 2, p["y"] + p["h"] / 2,
                      layers=layers, inflate=inflate, count=True)
            if din:
                self.disc(p["x"], p["y"], p.get("drill", 0) / 2.0, layers=tuple(range(NL)),
                          inflate=max(inflate, HOLE_INFLATE), count=True)

    def open_pad(self, p, layers):
        """只解锁「完全被本焊盘自身形状覆盖」的格子。

        - 同一焊盘号的多重几何已合并计数（见 add_pad_group）；
        - 被其他焊盘形状覆盖（shape_cnt>own）或压在板边/开槽静障（static）的格子
          保持封锁，避免 0.5mm 间距连接器漏通道、或走出板边。"""
        saved = []
        if not layers:
            return saved
        k = p.get("_gk")
        rec = self.own.get(k if k is not None else id(p))
        if rec is None:
            return saved
        i0, i1, j0, j1, own = rec
        for L in layers:
            sub = self.blocked[L, j0:j1 + 1, i0:i1 + 1].copy()
            saved.append((L, i0, i1, j0, j1, sub))
            cnt = self.shape_cnt[L, j0:j1 + 1, i0:i1 + 1]
            st = self.static_blk[L, j0:j1 + 1, i0:i1 + 1]
            om = own[L]
            unlock = (om > 0) & (cnt == om) & (~st)
            self.blocked[L, j0:j1 + 1, i0:i1 + 1] = np.where(unlock, False, sub)
        return saved

    def restore(self, saved):
        for L, i0, i1, j0, j1, sub in saved:
            self.blocked[L, j0:j1 + 1, i0:i1 + 1] = sub

    # ---------------- 走线占用 ----------------
    def occupy(self, a, b, net_id, layer, inflate=OCC_INFLATE):
        """按线段距离占用栅格（含端点），异网不可再用"""
        (x1, y1), (x2, y2) = a, b
        i0, i1, j0, j1 = self._slice(min(x1, x2) - inflate, min(y1, y2) - inflate,
                                     max(x1, x2) + inflate, max(y1, y2) + inflate)
        xs = np.arange(i0, i1 + 1) * GRID
        ys = np.arange(j0, j1 + 1) * GRID
        px = xs[None, :]
        py = ys[:, None]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            d2 = (px - x1) ** 2 + (py - y1) ** 2
        else:
            t = ((px - x1) * dx + (py - y1) * dy) / L2
            t = np.clip(t, 0.0, 1.0)
            d2 = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
        m = d2 <= inflate * inflate
        sub = self.occ[layer, j0:j1 + 1, i0:i1 + 1]
        sub[m & (sub == 0)] = net_id

    def mark_via(self, ix, iy_, net_id):
        r = int(np.ceil(VIA_INFLATE / GRID))
        i0, i1 = max(0, ix - r), min(self.nx - 1, ix + r)
        j0, j1 = max(0, iy_ - r), min(self.ny - 1, iy_ + r)
        for L in range(NL):
            sub = self.occ[L, j0:j1 + 1, i0:i1 + 1]
            sub[sub == 0] = net_id
            self.via_used[L, j0:j1 + 1, i0:i1 + 1] = True

    # ---------------- 过孔可用性 ----------------
    def build_via_mask(self):
        r = int(np.ceil(VIA_INFLATE / GRID))
        out = self.blocked.copy()
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                out |= np.roll(np.roll(self.blocked, dy, axis=1), dx, axis=2)
        self.via_block = out

    # ---------------- A* ----------------
    def _init_astar(self):
        self._g = np.full((NL, self.ny, self.nx), np.inf, dtype=np.float32)
        self._stamp = np.zeros((NL, self.ny, self.nx), dtype=np.int32)
        self._came = np.full((NL, self.ny, self.nx), -1, dtype=np.int32)
        self._mark = 0

    def astar(self, start, goal, net_id, budget=600_000, margin_mm=14.0, deadline=None):
        if not hasattr(self, "_g"):
            self._init_astar()
        self._mark += 1
        mk = self._mark
        sx, sy, sl = self.ix(start[0]), self.iy(start[1]), start[2]
        gx, gy, gl = self.ix(goal[0]), self.iy(goal[1]), goal[2]
        nx, ny = self.nx, self.ny
        if not (0 <= sx < nx and 0 <= sy < ny and 0 <= gx < nx and 0 <= gy < ny):
            return None

        m = int(round(margin_mm / GRID))
        bx0 = max(0, min(sx, gx) - m); bx1 = min(nx - 1, max(sx, gx) + m)
        by0 = max(0, min(sy, gy) - m); by1 = min(ny - 1, max(sy, gy) + m)

        g_arr, st_arr, cm_arr = self._g, self._stamp, self._came
        blk, occ, vb = self.blocked, self.occ, self.via_block

        def key(L, y, x):
            return (L * ny + y) * nx + x

        g_arr[sl, sy, sx] = 0.0
        st_arr[sl, sy, sx] = mk
        cm_arr[sl, sy, sx] = -1
        h0 = max(abs(sx - gx), abs(sy - gy))
        pq = [(h0, 0.0, sl, sy, sx)]
        n = 0
        DIRS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2))
        while pq:
            f, g, L, y, x = heapq.heappop(pq)
            if st_arr[L, y, x] != mk or g > g_arr[L, y, x] + 1e-6:
                continue
            if L == gl and y == gy and x == gx:
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
            if deadline is not None and (n & 4095) == 0 and time.monotonic() > deadline:
                return None
            for dx, dy, c in DIRS:
                ax, ay = x + dx, y + dy
                if ax < bx0 or ax > bx1 or ay < by0 or ay > by1:
                    continue
                if blk[L, ay, ax]:
                    continue
                o = occ[L, ay, ax]
                if o != 0 and o != net_id:
                    continue
                if dx and dy:      # 对角不允许切角
                    if blk[L, y, ax] or blk[L, ay, x]:
                        continue
                    oa = occ[L, y, ax]
                    ob = occ[L, ay, x]
                    if (oa != 0 and oa != net_id) or (ob != 0 and ob != net_id):
                        continue
                ng = g + c
                if st_arr[L, ay, ax] != mk or ng < g_arr[L, ay, ax]:
                    st_arr[L, ay, ax] = mk
                    g_arr[L, ay, ax] = ng
                    cm_arr[L, ay, ax] = key(L, y, x)
                    hh = max(abs(ax - gx), abs(ay - gy))
                    heapq.heappush(pq, (ng + HEUR_W * hh, ng, L, ay, ax))
            # 换层：贯穿孔（F<->In1<->In2<->B 一次打穿），所有铜层都要让开
            vr = 3      # 0.3mm：孔-孔最小间距 0.25 + 余量
            if self.via_used[L, max(0, y - vr):y + vr + 1,
                             max(0, x - vr):x + vr + 1].any():
                vr = -1
            if vr > 0 and not vb[:, y, x].any() and not blk[:, y, x].any():
                ok = True
                r = 5      # 过孔铜皮 0.3 + 间距 0.2 = 0.5mm，占用检查半径必须够
                for LL in range(NL):
                    sub = occ[LL, max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
                    if np.any((sub != 0) & (sub != net_id)):
                        ok = False
                        break
                if ok:
                    for ol in SIG:
                        if ol == L:
                            continue
                        ng = g + VIA_COST
                        if st_arr[ol, y, x] != mk or ng < g_arr[ol, y, x]:
                            st_arr[ol, y, x] = mk
                            g_arr[ol, y, x] = ng
                            cm_arr[ol, y, x] = key(L, y, x)
                            hh = max(abs(x - gx), abs(y - gy))
                            heapq.heappush(pq, (ng + HEUR_W * hh, ng, ol, y, x))
        return None


def path_to_geom(grid, path):
    """栅格路径 -> [(layer, [(x,y),...]), ...] + 过孔坐标列表"""
    if not path:
        return [], []
    groups, vias = [], []
    cur = path[0][2]
    pts = [(path[0][0] * GRID, path[0][1] * GRID)]
    prev = path[0]
    for node in path[1:]:
        if node[2] != cur:
            groups.append((cur, pts))
            vias.append((prev[0] * GRID, prev[1] * GRID))
            cur = node[2]
            pts = [(node[0] * GRID, node[1] * GRID)]
        else:
            pts.append((node[0] * GRID, node[1] * GRID))
        prev = node
    groups.append((cur, pts))

    out = []
    for L, ps in groups:
        simp = [ps[0]]
        for i in range(1, len(ps) - 1):
            ax, ay = simp[-1]
            bx, by = ps[i]
            cx, cy = ps[i + 1]
            if (bx - ax) * (cy - by) - (by - ay) * (cx - bx) == 0:
                continue
            simp.append(ps[i])
        simp.append(ps[-1])
        out.append((L, simp))
    return out, vias
