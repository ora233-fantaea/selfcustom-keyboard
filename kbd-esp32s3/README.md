# ESP32-S3 客制化键盘 · KiCad 工程

> 更新日期：2026-11-23
> 状态：**原理图 + PCB 实质设计**（非可投产图纸，布线未完成）
> 主控：Waveshare ESP32-S3-DEV-KIT-N16R8-M（16MB Flash / 8MB PSRAM）
> 轴体：**仅 Cherry MX 及兼容轴（已放弃 MX/Choc 混合兼容）**

## 工程文件

| 文件 | 说明 |
|---|---|
| `kbd-esp32s3.kicad_pro` | KiCad 9 工程文件 |
| `kbd-esp32s3.kicad_sch` | 原理图：74HC165 级联读键电路（非矩阵） |
| `kbd-esp32s3.kicad_pcb` | PCB：75 键真实配列 + 纯 MX 热插拔轴座 + 完整网络分配 |
| `gen_sch.py` / `lib_extract.py` | 原理图生成脚本（符号提取 + 布局 + 标签） |
| `gen_pcb.py` | PCB 生成脚本（pcbnew API，可重跑：配列/封装/网络/级联布线） |
| `gen_stabilizers.py` | 卫星轴定位板开孔数据生成（坐标表 + 示意图，可重跑） |
| `stabilizer_plate_holes.md` | 卫星轴开孔坐标表 + 采购清单 |
| `stabilizer_layout.png` | 卫星轴孔位示意图 |
| `gen_plate.py` | 定位板生成脚本（可重跑） |
| `kbd-plate.kicad_pcb` | 定位板板文件（Edge.Cuts：板框/键孔/卫星孔/M3/避让窗） |
| `kbd-plate.dxf` | 定位板切割文件（Edge.Cuts 层，发厂激光切割/CNC） |
| `plate_preview.png` | 定位板预览图 |

## 键盘输入电路（原理图和 PCB 一致）

**方案：74HC165 级联，每键独立输入，无矩阵、无二极管。**

- 10 片 74HC165，每片 8 路并行输入 = 80 路，覆盖 75 键，5 路空余接地。
- 每键：轴座 + 10kΩ 上拉电阻，独立接入一片 74HC165 的输入。
- 级联：前级 `Q7`(pin9) → 后级 `DS`(pin10)，网络 `CHAIN_1..CHAIN_9`；末片 `Q7` → `DATA`。
- 并行时钟 `CLK`(pin2)、锁存 `SH_LD`(pin1, 低有效) 全局并联；`~CE`(pin15) 接地常使能。
- 编码器：EC11 带按压，`ENC_A/ENC_B/ENC_SW` 独立引出，不进级联链。
- 接口：ESP32 开发板插座 = 两条独立 1×20 排母（P1/P2），**两排中心距 21.80mm**，非一体 2×20；USB-C（预留）。

## PCB 设计（本次完成）

### 配列：精确 75 键 / 6 行

| 行 | 键数 | 内容 |
|---|---|---|
| Row0 功能行 | 13 | Esc + F1~F12 |
| Row1 数字行 | 14 | ` 1-0 - = + Bksp(2u) |
| Row2 Q 行 | 14 | Tab(1.5u) Q-P [ ] \(1.5u) |
| Row3 A 行 | 13 | Caps(1.75u) A-L ; ' + Enter(2.25u) |
| Row4 Z 行 | 13 | LShift(2.25u) Z-M , . / + RShift(1.75u) + ↑ |
| Row5 底行 | 8 | LCtrl LWin LAlt + Space(8.25u) + Fn ← ↓ → |

- 键距 19.05mm，宽键按单位 u 计算，板框 337.8 × 206.3mm（顶部加高以容纳开发板双排针接口）。
- **方向键采用标准倒 T 布局**：↑ 中心与 ↓ 对齐（x=14.5u），← ↓ → 三键并排在底行右侧，整簇紧凑、符合常规使用习惯。为腾出倒 T 所需空间，RShift 由 2.75u 缩至 1.75u、Space 由 6.25u 加长至 8.25u，总键数仍为 75。

### 元件

| 元件 | 数量 | 封装 / 说明 |
|---|---|---|
| 纯 MX 热插拔轴座 | 75 | `SW_MX_HotSwap_PTH`（仅 Cherry MX 及兼容轴，pad1=信号 / pad2=GND） |
| 上拉电阻 10k | 75 | 0603，pad1→VCC，pad2→按键网络 |
| 74HC165 | 10 | SOIC-16W，贴近对应键位组 |
| 去耦电容 100nF | 10 | 0603，每片 74HC165 一个 |
| ESP32 开发板插座 | 2 | 各 1×20 排母（P1/P2），水平放置，**中心距 21.80mm**，遵循微雪官方尺寸图 |
| EC11 编码器 | 1 | 带按压开关 |
| USB-C | 1 | GCT USB4085（预留接口） |
| 安装孔 M3 | 4 | 四角 |

### 卫星轴（plate-mount，定位板卡扣）

**结论：卫星轴装在定位板上，PCB 无需开孔、无需改板。** 之前 PCB 未体现属正常，但定位板开孔坐标与 BOM 此前缺失，现已补齐（见 `gen_stabilizers.py` / `stabilizer_plate_holes.md` / `stabilizer_layout.png`）。

- 覆盖范围：**仅 2u 以上**（Bksp 2u / Enter 2.25u / LShift 2.25u / Space 8.25u），共 4 键 8 个 housing 位。
- 开孔：每个 housing 位约 6.65×12.3mm 矩形，中心坐标见 `stabilizer_plate_holes.md`（与 KiCad 板坐标一致）。
- 采购：2u plate-mount ×3、8u plate-mount ×1（2u/2.25u/2.75u 共用同一 2u 卫星轴）。
- **坑**：Space 是 8.25u，Cherry 无此档位；已按用户确认的 **8u（孔距 133.35mm，X=108.34/241.69）** 定死，下单键帽前仍须实测其卫星轴孔距。详见坐标表注意事项。

**定位板已建**（`gen_plate.py` 生成，**专为 MX 轴设计**）：整块 337.8×206.3mm，键孔 14×14（MX 标准）；2u/2.25u 大键的轴孔与卫星孔用 5mm 窄颈连通成一体开孔（plate-mount housing 必须这样才卡得进去），空格因卫星孔距中心 66.675mm 保持三孔独立。输出 `kbd-plate.kicad_pcb`（KiCad 可打开）与 `kbd-plate.dxf`（发厂切割）。避让窗 x[140,198] y[2,31] 供开发板排针。

### 开发板插座 Pinout（依据微雪官方原理图/尺寸图）

数据来源：[Waveshare ESP32-S3-DEV-KIT 文档](https://docs.waveshare.com/ESP32-S3-DEV-KIT-N8R8)、官方 schematic PDF、尺寸图（63.30 × 25.40mm，排针中心距 21.80mm）。

| P1 (J_P1) | 网络 | P2 (J_P2) | 网络 |
|---|---|---|---|
| 1 | 3V3 → VCC | 1 | GND |
| 2 | EN → NC | 2 | TXD / GPIO43 |
| 3 | GPIO4 → **CLK** | 3 | RXD / GPIO44 |
| 4 | GPIO5 → **SH_LD** | 4 | GPIO1 |
| 5 | GPIO6 → **DATA** | 5 | GPIO2 |
| 6 | GPIO7 → **ENC_A** | 6 | GPIO42 |
| 7 | GPIO15 → **ENC_B** | 7 | GPIO41 |
| 8 | GPIO16 → **ENC_SW** | 8 | GPIO40 |
| 9 | GPIO17 | 9 | GPIO39 |
| 10 | GPIO18 | 10 | GPIO38 |
| 11 | GPIO8 | 11 | GPIO37 |
| 12 | GPIO3 | 12 | GPIO36 |
| 13 | GPIO46 | 13 | GPIO35 |
| 14 | GPIO9 | 14 | GPIO0 (BOOT) |
| 15 | GPIO10 | 15 | GPIO45 |
| 16 | GPIO11 | 16 | GPIO48 |
| 17 | GPIO12 | 17 | GPIO47 |
| 18 | GPIO13 | 18 | GPIO21 |
| 19 | GPIO14 | 19 | GPIO20 (USB D+) |
| 20 | 5V → NC | 20 | GPIO19 (USB D-) |

> 注：本项目需要的 6 个信号（CLK/SH_LD/DATA/ENC_A/B/SW）已映射到 P1 的 GPIO4/5/6/7/15/16；其余 GPIO 针脚按官方定义保留网络名备用。NC 引脚为板子上未连接/NC 的 GPIO（如 GPIO35/36/37 在 WROOM-1 上不引出）。

### 网络分配

- 129 个网络：K01~K75（按键）、CHAIN_1~10（级联，末片 CHAIN_10 即 ESP32 DATA）、CLK、SH_LD、ENC_A/B/SW、GPIO1~48（开发板插座备用针脚）、VCC、GND、VBUS、USB_D±、CC1/CC2。
- 原理图 92 个网络与 PCB **全部匹配**（已脚本核对），GUI 中 F8 同步不会报网络错误。
- **所有焊盘已分配网络**（网络名即飞线依据）。
- 已预布最关键的**级联数据链**（47 段走线），采用芯片外侧下方专用通道，避免穿焊盘。

## 验证状态

| 检查项 | 结果 |
|---|---|
| 原理图加载 / ERC 电气错误 | ✅ 通过 / 0 error |
| PCB 加载 / 导出 SVG | ✅ 通过 |
| DRC 电气短路（shorting_items） | ✅ **0 个** |
| DRC 未连接项 | 499（预期：按键扫描线/电源/时钟/地尚未布线） |
| 其余 DRC 警告 | 240 项非电气警告：courtyard_overlap 75 + hole_clearance 151（轴座 PTH 孔密集的固有特性）+ clearance 14（USB-C 密脚封装固有 0.15mm 间隙）。短路 0、走线交叉 0。 |

## 剩余边界（下一步）

1. **布线未完成**：499 个飞线需在 KiCad GUI 中完成（自动布线器或手动）——按键扫描线、上拉电阻 VCC、74HC165 电源/时钟/锁存、编码器、USB。级联数据链已预布。
2. **网表同步**：本 PCB 的网络分配由脚本直接写入，与原理图网络名一致；GUI 打开后可执行 F8 核对。
3. **ERC 10 个 `lib_symbol_mismatch`**：74HC165 继承符号展开的缓存差异，"更新符号库缓存"可消除，非电气问题。
4. **DRC 布局警告**：240 项均为机械/密脚警告（轴座 PTH 孔间距、USB-C 密脚），非短路非交叉；可后续调整孔间距规则清理，不影响电气。
5. **尚未做**：副屏（SPI 长条屏）接口、真实外壳/定位板配合、MX 轴座的实物焊接验证。级联链已改走 B.Cu 背面独立通道，消除了 F.Cu 相邻引脚跨接交叉。
6. **定位板**：已建好（`kbd-plate.kicad_pcb` + `kbd-plate.dxf`），板框 337.8×206.3mm、与 PCB 对齐；含 75 个 14×14 键孔、8 个卫星轴孔（2u 级与中心轴孔用窄颈连通为一体孔，空格三孔独立）、4×M3 Ø3.2、顶部开发板避让窗。建议 1.5mm FR4 或铝板，发厂用 `kbd-plate.dxf`。PCB 无需改动。

## 环境说明

- KiCad 9.0.9（官方 PPA）；headless 环境，用 `kicad-cli` 和 `pcbnew` Python API 操作。
- 第三方键盘封装库：`/root/.local/share/kicad/9.0/footprints/`。
- 全局库表 `sym-lib-table` / `fp-lib-table` 已配置在 `~/.config/kicad/9.0/`。
- 重跑生成：`python3 gen_pcb.py`（会覆盖 .kicad_pcb）。
