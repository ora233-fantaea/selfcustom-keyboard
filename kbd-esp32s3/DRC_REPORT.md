# KiCad 与官方 DRC 报告

## 一、KiCad 是怎么装上的

**官方安装器装不上**：`kicad-9.0.9-x86_64.exe` 是 NSIS 打包，静默安装（`/S`）在非交互环境需要 UAC 提权，退出码 1。

**改用免安装解包**（不需要管理员权限）：

```bash
7z x -y kicad-9.0.9-x86_64.exe -oKiCad
KiCad/bin/kicad-cli.exe version     # -> 9.0.9
KiCad/bin/python.exe -c "import pcbnew; print(pcbnew.Version())"   # -> 9.0.9
```

位置：`D:\workbuddy-temp\spaces\2026_11_23_22-26-20\_tools\KiCad\`（915 MB，在工作目录下，未纳入版本库）

`kicad-cli` 负责 DRC / 导出，`KiCad/bin/python.exe` 带 `pcbnew` 绑定，可以直接跑 `gen_plate.py`。
另外给这个 python 装了 `shapely`、`matplotlib`（定位板开孔合并与预览需要）。

## 二、解包后暴露的四个 Bug

装上 KiCad 后第一件事就是跑 DRC，结果**直接报「电路板加载失败」**——
也就是说我们之前生成的所有 `.kicad_pcb`，KiCad 根本打不开，而自研的宽松解析器发现不了。
二分定位到四处：

| # | 问题 | 现象 | 修复 |
|---|---|---|---|
| 1 | `(version 20250114)` 比本机 KiCad 的格式版本 `20241229` 新 | KiCad 判定「文件来自更高版本」，**静默返回 null** | 改为 `20241229` |
| 2 | `(generator_version 9.0)` 没加引号 | `9.0` 以数字开头的裸符号无法解析 | 改为 `"9.0"`（`generator` 同理） |
| 3 | `(pad np_thru_hole ...)` 焊盘编号是空字符串而不是空引用 | `_emit` 把空原子直接吞掉，编号丢失，整块板解析失败 | 改用 `K.Str("")` |
| 4 | 布线器把层号 `0/1` 写进 `(layer ...)` | `(layer "0")` 不是合法层名，**布线后的文件全部打不开** | 加 `LAYER_NAME = {0:"F.Cu", 1:"B.Cu"}` 映射 |

第 1 条最阴——KiCad 不报错、不抛异常，`LoadBoard()` 只返回 `None`，靠猜是猜不出来的。

第 4 条是这次顺带挖出来的：`autoroute.py` 里 `path_to_geom()` 返回的是层索引，
直接塞进 `(layer ...)` 就成了 `(layer "0")`。也就是说**之前所有「已布线」的文件，KiCad 一个都打不开**，
134/183 那个数字只在自研解析器里成立。

## 三、官方 DRC 结果（未布线版）

```
kicad-cli pcb drc kbd-esp32s3.kicad_pcb
```

| 类型 | 条数 | 定性 |
|---|---|---|
| 未连接 `unconnected_items` | 463 | 未布线，预期内 |
| 丝印压焊盘 `silk_over_copper` | 65 | 外观问题，板厂会自动裁掉丝印 |
| 丝印重叠 `silk_overlap` | 44 | 同上 |
| 铜箔间距 `clearance` | 18 | **全部在 J_USB 内部**：0.5mm 间距连接器的焊盘间隙 0.15mm，封装固有 |
| 占位框重叠 `courtyards_overlap` | 18 | 0603 上拉电阻落在按键 19.05 方形键帽占位框内（键帽在板外，非实体冲突） |

**已归零的两类（这轮修掉的）**：

| 类型 | 修前 | 修后 | 原因与修法 |
|---|---|---|---|
| `hole_clearance` | 127 | **0** | Ø3.0 热插拔孔的外盘 3.6mm 离 Ø1.7 定位柱孔只剩 0.19mm（要求 0.25）。外盘缩到 3.4mm，环宽仍有 0.2mm，间距变 0.29mm |
| `courtyards_overlap` | 74 | 18 | 0603 的占位框宽 2.96mm，而电阻列距设成了 2.90mm，相邻两个压 0.06mm。列距改 3.06mm，并在片内居中 |

## 四、布线版 DRC：把自研校验器的结论推翻了

修好层名之后，`kbd-esp32s3_routed_wip.kicad_pcb` 终于能被 KiCad 打开，DRC 结果很难看：

| 类型 | 条数 | 说明 |
|---|---|---|
| `shorting_items` | **199** | 走线压到异网焊盘 |
| `solder_mask_bridge` | 199 | 阻焊桥，与上一条同源 |
| `track_dangling` | 199 | 走线末端悬空（未布完） |
| `copper_edge_clearance` | 89 | 走线离开槽边 0.425mm < 0.5 要求——**布线器完全不知道开槽存在** |
| `tracks_crossing` | 10 | V5/GND 与灯链在 B.Cu 交叉 |
| 其余（丝印/占位框） | 127 | 同未布线版 |

**必须纠正我之前的说法**：自研 `verify_pcb.py` 报的是「2 处短路」，实际是 199 处。
抽查一条即可确认 DRC 没错：

```
K30 走线终点 (63.60, 153.20)，线宽 0.2 -> 边缘到 153.10
U2 焊盘 4 (K56)  y 152.565..153.165
=> 实际重叠 0.065mm，是真短路
```

漏检原因很具体：`verify_pcb.py` 只算「走线 vs 焊盘中心/外框」，且焊盘按矩形外扩 0.3mm 做栅格化，
对 2.05×0.6 这种细长 SOIC 焊盘，四角与边缘的侵占测不出来；它更不会把 Edge.Cuts 开槽当成障碍。

结论：**自动布线器目前不可用**，要在三处补课才能继续——

1. 障碍栅格按焊盘真实形状（含圆角/长条）光栅化，而不是中心点 + 常数外扩；
2. 把全部 Edge.Cuts 内轮廓作为禁布区，并按 0.5mm 板边间距外扩；
3. 走线之间除占用位图外，还要按 0.2mm 间距做线段级干涉检查（`tracks_crossing` 那 10 条就是这么漏的）。

## 五、复跑方式

```bash
python run_drc.py                       # 默认 kbd-esp32s3.kicad_pcb
python run_drc.py kbd-esp32s3_routed_wip.kicad_pcb
```

脚本会自动找 `../_tools/KiCad/bin/kicad-cli.exe`（也可用环境变量 `KICAD_CLI` 指定），
按类型汇总并落一份 `.drc.rpt`。

## 六、定位板

`gen_plate.py` 之前一直是坏的：它从 `gen_pcb.py` 里用 AST 抠 `U / ORIGIN_X / LAYOUT` 等常量，
但重构后这些常量已搬到 `kbd_design.py`，所以一跑就 `KeyError: 'U'`。
已改为从 `kbd_design.py` 读取，并用 KiCad 自带 python 重新生成：

- `kbd-plate.kicad_pcb` / `kbd-plate.dxf`：避让窗按模块本体 63.30×25.40 放宽到 `x[136,202] y[1,30]`
- DRC：**0 条违规**
- 卫星轴坐标复核：LShift 34.53 / 58.33、Space 108.34 / 241.69（Y 116.20 / 135.25），与 `stabilizer_plate_holes.md` 修正后一致
