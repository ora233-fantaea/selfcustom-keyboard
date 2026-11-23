# ESP32-S3 客制化键盘设计方案 —— 可行性验证报告

> 验证日期：2026-11-23
> 验证性质：**仅做技术可行性核查与资料整理**，不涉及原理图、PCB、结构设计或固件编写。
> 对应基线：`ESP32-S3客制化键盘设计方案.md`（2026-11-23 版）

---

## 0. 总体结论

方案的技术路线**整体成立**：ESP32-S3 原生 USB HID、74HC165 级联读键、MX/Choc V1 双轴兼容、EC11 编码器、SPI 长条屏，均有官方资料或成熟先例支撑。文档对 1000Hz 回报率边界的判断（不做 8000/16000Hz）是准确的。

但有 **1 个隐藏风险** 和 **3 个需要在下一阶段重点落实** 的点：

| 级别 | 问题 | 结论 |
|---|---|---|
| 🔴 隐藏风险 | USB-OTG 与 USB-Serial-JTAG 共用同一内部 PHY，做原生 HID 时下载/调试口会冲突 | 文档未提及，直接影响开发板选型和开发流程，详见 §2.1 |
| 🟡 重点落实 | 开发板必须把 GPIO19/20（D-/D+）以原生 USB 形式引出 | 文档 §3.1 已意识到，验证属实，需落实到具体型号 |
| 🟡 重点落实 | 双轴座同一键位存在机械干涉风险 | 有先例但工程难度中等，单键验证板（文档阶段一）是必要步骤 |
| 🟡 重点落实 | 75 路独立信号 + 上拉电阻 + 10 片 165 的布线密度 | 电气可行，物理布局是主要挑战 |

---

## 1. 逐项可行性验证

| 文档章节 | 方案要点 | 验证结论 | 关键依据 |
|---|---|---|---|
| §3 主控与 USB | ESP32-S3 原生 USB 做 Keyboard + Raw HID 复合设备 | ✅ 可行 | 官方 USB Device Stack 基于 TinyUSB，明确支持 HID、复合设备、Vendor-Specific（Raw HID），最多 6 个端点 [1][2] |
| §2 USB 边界 | 1000Hz 目标，不做 8000/16000Hz | ✅ 判断正确 | USB 2.0 全速中断传输最小间隔 1ms，即 1000Hz 理论上限；实测 ESP32-S3 在 1000Hz 下追加延迟 <500µs [3] |
| §3.3 无线扩展 | BLE/Wi-Fi 后续扩展 | ✅ 可行 | S3 片内集成 BLE + 2.4GHz Wi-Fi；但 §3 的 USB PHY 冲突同样影响调试方式 |
| §4 74HC165 级联 | 10 片覆盖 75 键，每键独立输入，无矩阵无二极管 | ✅ 可行，成熟方案 | 8 位并转串，级联只需 3~4 个 GPIO；75 键→10 片（向上取整）计算正确 [4][5] |
| §4.2 电气要求 | 3.3V 供电、100nF 去耦、明确上拉/下拉、软件去抖 | ✅ 合理 | 74HC 工作范围 2~6V，3.3V 兼容；外部上拉推荐 10kΩ，避免用内部上拉 [4][6] |
| §5 MX/Choc V1 双轴 | 同一 PCB 每个键位放两种热插拔座，19.05mm 间距 | ✅ 可行，有商业先例 | Boardsource Lily58/Corne 用 universal footprint 同时支持 MX/Choc v1/v2，统一 19.05mm；另有开源混合封装库 [7][8] |
| §5.3 单键验证板 | 全尺寸前先做单键双轴验证 | ✅ 强烈支持 | Choc V1 中心固定柱比 MX 小、但多两个辅助固定柱，焊盘/定位孔/键帽差异必须实物验证 [8] |
| §6 编码器 | EC11/EC12 直连 GPIO，不接 165 级联链 | ✅ 可行，决策正确 | A/B 正交解码用中断+状态机，成熟方案；不串入级联链可避免快速旋转漏边沿 [9][10] |
| §7 SPI 长条屏 | Raw HID 回传系统信息，ESP32-S3 绘制，不阻塞输入 | ✅ 可行 | esp_lcd + DMA 是常规做法；注意显示任务优先级不要设最高，否则输入/Wi-Fi 任务饥饿 [11][12] |
| §8 外壳/定位板 | PETG 首版 + 7075-T6 CNC 正式版 | ✔️ 常规工程做法 | 属材料/结构常识范畴，非本轮联网核查重点；分体设计、独立定位板、热熔铜螺母思路合理 |

---

## 2. 重点风险详解

### 2.1 🔴 USB PHY 冲突（文档未覆盖，最需要提前决策）

这是本次核查中发现的、文档完全没有提到但对开发影响最大的点：

- ESP32-S3 内部有 **两个 USB 控制器**：`USB-OTG` 和 `USB-Serial-JTAG`，二者 **共用同一个内部全速 PHY，同一时刻只能一个工作** [1][13]。
- 用 TinyUSB 初始化 HID 设备时，PHY 会自动切换到 USB-OTG；此时原本用于下载/日志的 USB-Serial-JTAG 通道就不可用了。
- 后果：**固件跑起来进入原生 HID 后，不能再直接用这个 USB 口下载新固件**，需要按 BOOT 键手动进下载模式，或烧录 eFuse 把调试切到传统 JTAG。
- 若确实需要"USB HID + 串口调试"同时在线，只能上 **外部 USB PHY**（额外占用至少 6 个 GPIO，增加 BOM 和布线）[1][13]。

**对本项目的影响与建议：**

1. 文档 §3.1 已强调"不要把 USB 转串口口当 HID 口"——方向正确，但还要进一步：**确认开发板的原生 USB 排针确实接在 GPIO19/20 上**，且知道该口一旦被 HID 占用后调试方式如何变化。
2. 首版验证阶段（文档阶段二）建议保留串口日志通道，可考虑：暂时用 UART0（GPIO43/44）转串口做日志，USB 专用于 HID；或接受"按 BOOT 键下载"的开发节奏。
3. 选型时确认开发板是 **双 USB-C**（一路 USB-Serial-JTAG、一路 CH340/CP2102 串口）还是 **单 USB-C**，这直接决定调试体验。

### 2.2 🟡 双轴兼容的工程边界

- "同一键位放两种热插拔座"在电气上没问题，但 **MX 与 Choc V1 的定位柱结构不同**：MX 中心柱较大；Choc V1 中心柱较小，但增加两个辅助固定柱 [8]。
- 好消息：现有 universal footprint 已能在 19.05mm 间距下兼容 MX + Choc v1（甚至 v2），商业产品已量产 [7]，开源 KiCad 库也有 `SW_MX_Kailh_Choc_V1V2_THT_Hybrid` 这类混合封装 [8]。
- 文档选择"不做 Choc V2"是合理的范围控制，但采用现成 universal footprint 时通常顺带就支持了，属于"额外收益"，不必刻意回避。
- 文档强调的实物验证（插拔、焊盘/定位孔不冲突、无机械干涉、热插拔可靠性）是**正确且必要**的，建议照阶段一执行。

### 2.3 🟡 布线密度

75 键独立输入意味着：75 根按键信号线 + 约 75 个上拉电阻 + 10 片 74HC165 分布在板上（对比矩阵方案只需行+列约 17 根线）。电气上完全可行，但 **PCB 布局比矩阵方案拥挤**。文档阶段二"先做 8 键验证板"的规划是对的，建议把"布线密度与 165 摆放位置"也纳入验证目标。

---

## 3. ESP32-S3 引脚 / GPIO / I2C 详细资料

> 来源以乐鑫官方文档为主 [14][15][16]。注意：本项目用成品开发板， flash/PSRAM/晶振/射频等核心电路已在板上，主 PCB 只需处理接口层；但若未来自行设计裸机，本节 §3.2~§3.3 的限制直接适用。

### 3.1 引脚总览

| 项目 | 参数 |
|---|---|
| 物理 GPIO 数 | 45 个：GPIO0~GPIO21 + GPIO26~GPIO48（GPIO22~25 不存在） |
| 可用作通用 IO | 每个 GPIO 均可通过 GPIO 交换矩阵映射内部外设信号 |
| ADC | 20 路 12 位：ADC1_CH0~9 = GPIO1~10；ADC2_CH0~9 = GPIO11~20 |
| 触摸传感器 | 14 路：GPIO1~GPIO14（TOUCH1~14，其中仅 GPIO14 可驱动屏蔽电极） |
| SPI | 4 个（SPI0/1 供 flash，SPI2/SPI3 供外设） |
| UART | 3 个，UART0 默认 GPIO43(TX)/GPIO44(RX) |
| I2C | 2 个控制器（I2C0/I2C1） |
| PWM | 8 通道 LED PWM，任意输出 GPIO 可用 |
| 中断 | 所有 GPIO 均可配置为中断 |

### 3.2 使用限制引脚（关键）

| 类别 | 引脚 | 说明 / 对本项目的影响 |
|---|---|---|
| **Strapping 引脚** | GPIO0、GPIO3、GPIO45、GPIO46 | 上电/复位时电平决定启动模式与 VDD_SPI 电压。复位后恢复普通 IO，但**上电瞬间不要接会被外部电路拉到错误电平的负载**，见 §4.3 |
| **Flash / PSRAM 占用** | GPIO26~GPIO32 | 常规四线 flash/PSRAM 占用，**不推荐他用** |
| **八线 PSRAM 额外占用** | GPIO33~GPIO37 | 使用 ESP32-S3R8/R8V 等八线 PSRAM 模组时这些脚也被占用；选带 PSRAM 的模组时要避开 |
| **USB 专用** | GPIO19(D-)、GPIO20(D+) | 默认用于 USB-JTAG/USB-OTG；配置为普通 GPIO 会禁用 USB-JTAG |
| **UART0** | GPIO43(TX)、GPIO44(RX) | 默认下载与 log 口，U0TXD 建议串 499Ω 抑制谐波 |

### 3.3 I2C 详情

| 参数 | 说明 |
|---|---|
| 控制器数量 | 2 个（I2C0 / I2C1），每个可主可从 |
| 引脚映射 | **无固定硬件默认脚**，通过 GPIO 交换矩阵可映射到几乎任意 GPIO；Arduino 生态约定 SDA=GPIO8、SCL=GPIO9，ESP-IDF 由 `sda_io_num`/`scl_io_num` 自行指定 [15] |
| 速度 | 标准模式 100kHz / 快速模式 400kHz；主机 SCL 不应超过 400kHz |
| 上拉电阻 | 开漏需外部上拉，推荐 1~10kΩ，常用 2~5kΩ；内部上拉在高速下不足以拉高总线。**避开被 strapping/flash 占用的脚** |
| 本项目相关性 | 文档方案里屏幕走 SPI，I2C 目前非核心；若副屏或传感器改走 I2C，可直接用此结论 |

> 说明：网络上常见的"I2C 默认 SDA=GPIO8/SCL=GPIO9"来自 Arduino-esp32 框架约定，并非芯片硬件强制 [16]。以你最终选用的框架和开发板原理图为准。

### 3.4 本项目引脚规划建议（非定稿，供下一阶段参考）

在成品开发板排针条件下，避开 strapping(0/3/45/46)、USB(19/20)、UART0(43/44)、flash/PSRAM(26~37) 后，推荐如下分配：

| 功能 | 建议引脚 | 理由 |
|---|---|---|
| 74HC165 级联（CLK / DATA / LOAD） | GPIO12 / GPIO13 / GPIO14 | 可直接复用 SPI2 的 SCK/MISO，硬件 SPI 读取更快 |
| 编码器 A / B / SW | GPIO4 / GPIO5 / GPIO6 | 均支持中断，避开特殊脚 |
| SPI 屏 SCK / MOSI / CS / DC / RST / BLK | GPIO47 / GPIO48 / GPIO41 / GPIO42 / GPIO1 / GPIO2 | 全部落在确认安全区，规避八线 PSRAM 风险 |
| USB D- / D+ | GPIO19 / GPIO20（固定） | 硬件固定，不可改 |
| 日志 UART（可选） | GPIO43 / GPIO44 | 与 USB HID 并行使用，缓解 §2.1 调试冲突 |

> ⚠️ 上表仅为可行性阶段的候选方案。实际分配必须在确定**具体开发板型号**（哪些 GPIO 真正引到排针）和**是否带八线 PSRAM**后重新核对。

---

## 4. PCB 线路设计要点（验证阶段资料清单）

> 来源：乐鑫《硬件设计指南》原理图检查清单 [13][17]。本项目用成品开发板，大部分核心电路（40MHz 晶振、flash、射频匹配、LDO）已在板上，主 PCB 重点是**接口与外围**；下列"核心电路"条目供自行设计裸机时参考。

### 4.1 USB 接口

- D+ = GPIO20，D- = GPIO19，走 90Ω 差分（USB 2.0 规范通用要求，乐鑫指南未单列数值）。
- D+/D- 线上**预留串联电阻**（初值 22Ω 或 33Ω）和对地电容（初始可不贴），器件**靠近芯片端**放置 [13]。
- 注意 USB_D+ 上电时会输出电平，高电平驱动较强；为获得稳定初始态，建议加外部上拉 [13]。
- 自供电设备需通过分压电阻或比较器监测 VBUS（分压使 4.4V→0.75×Vdd），且**任何 ESP32-S3 引脚都不耐 5V** [2]。
- USB 接口附近预留 ESD 保护（文档 §3.2 已规划，正确）。

### 4.2 电源与去耦

- 单电源 3.3V，输出电流 **≥500mA**；总电源入口加 ESD 器件 + **≥10µF** 大电容 [17]。
- 数字电源脚（VDD3P3_CPU、VDD3P3_RTC）附近各加 **0.1µF**；VDD_SPI 加 0.1µF + 1µF（勿过大）。
- 模拟电源 VDD3P3 走线上加 **10µF**（可搭配 1µF），并加 LC 滤波，电感额定电流 ≥500mA。
- 副屏背光：如文档 §7.1 所述单独核算电流，屏电源脚附近加 10µF + 100nF，SCLK/MOSI 走线尽量短 [12]。

### 4.3 Strapping 与复位

- GPIO0 预留上拉电阻，**不要加大电容**，否则可能进下载模式。
- GPIO0、GPIO3、GPIO45、GPIO46 上电时电平有约束（GPIO0+GPIO46 共同决定启动模式；GPIO45 决定 VDD_SPI 电压）。
- EN/CHIP_PU 复位：推荐 RC = 10kΩ + 1µF，走线尽量短，上电稳定时间 ≥50µs [17]。

### 4.4 外围与信号完整性

- **74HC165 级联**：CLK、LOAD、级联 DATA 走线尽量短、避免过绕；源端预留小阻值串阻位置（文档 §4.2 已规划，正确）。按键上拉用外部 10kΩ，勿依赖内部上拉。
- **SPI 屏**：SPI_CLK 加串联电阻（或磁珠）+ 对地电容改善 EMC，RC/LC 靠近芯片/模组脚放置 [17]。
- **未用 GPIO**：高阻且无内部上下拉的脚，外加上下拉或在软件初始化时开启内部上下拉，避免额外功耗。
- **地平面**：官方检查清单未给出完整地平面规则，建议按常规多层板 practices（完整地平面、差分线参考平面连续、晶振下方避免走线）在 layout 阶段自行把关。

---

## 5. 需要在下一阶段补充/修正的点

1. **确定开发板具体型号**（文档 §13 待确认项）：重点核对 ① GPIO19/20 是否引到排针且为原生 USB；② 双 USB 还是单 USB；③ 是否带八线 PSRAM（影响 GPIO33~37 可用性）；④ 板载 USB 转串口芯片型号。
2. **明确 USB 调试策略**：接受"按 BOOT 下载"，还是保留 UART0 日志通道，或上外部 PHY。这会影响原理图接口预留。
3. **Raw HID 复合设备描述符**：TinyUSB 支持，但 HID + Vendor 接口的报告描述符需在固件阶段设计，属已知可行但需工作量。
4. **编码器型号参数**：不同 EC11 型号的 detents（15/18/20/30）与 pulses per turn（9/15/20）不同，固件解码阈值需按实物调整 [10]。
5. **副屏任务优先级**：保持在中等偏低，用 DMA + 局部刷新，传输中让出 CPU，确保 1000Hz 按键扫描与 HID 上报不被阻塞 [11][12]。

---

## 6. 参考来源

[1] Espressif, USB Device Stack (ESP32-S3) — https://docs.espressif.com/projects/esp-idf/zh_CN/release-v6.0/esp32s3/api-reference/peripherals/usb_device.html
[2] Espressif, USB Device Driver (en) — https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32s3/api-reference/peripherals/usb_device.html
[3] USB Passthrough benchmark (1000Hz latency) — https://blog.arfevrier.fr/usb-passthrough-for-keyboard-and-mouse-using-two-esp32/
[4] Makerguides, More Inputs With 74HC165 — https://www.makerguides.com/?p=13788/
[5] 瀚文键盘 74HC165 级联设计（75键→10片） — https://blog.csdn.net/weixin_28256233/article/details/158130157
[6] 74HC165 并转串读取按键（上拉/去抖） — https://blog.csdn.net/weixin_29867767/article/details/154966373
[7] Boardsource Lily58 SMT（universal footprint, MX/Choc v1/v2, 19.05mm） — https://boardsource.xyz/blogs/guides/wireless-smt-lily58-docs
[8] siderakb/key-switches.pretty 混合封装兼容性表 — https://github.com/siderakb/key-switches.pretty/blob/master/README.md
[9] DavidAntliff/esp32-rotary-encoder（EC11 状态机解码） — https://github.com/DavidAntliff/esp32-rotary-encoder
[10] EC11 rotary encoder with ESP32（抖动与型号差异） — https://lcdultrapro.com/parts/ec11-encoder
[11] ESP32-S3 驱动 ST7789 + FreeRTOS 刷屏优化 — https://blog.csdn.net/weixin_29188043/article/details/164159947
[12] ESP32-S3 驱动 ST7789：DMA/局部刷新/背光供电 — https://blog.csdn.net/weixin_42520573/article/details/170653071
[13] Espressif, ESP32-S3 USB PHY 介绍 — https://docs.espressif.com/projects/esp-iot-solution/zh_CN/release-v2.0/usb/usb_overview/usb_phy.html
[14] Espressif, GPIO & RTC GPIO (ESP32-S3) — https://docs.espressif.com/projects/esp-idf/zh_CN/release-v6.0/esp32s3/api-reference/peripherals/gpio.html
[15] Espressif, I2C Driver (ESP32-S3) — https://docs.espressif.com/projects/esp-idf/zh_CN/stable/esp32s3/api-reference/peripherals/i2c.html
[16] ESP32-S3 DevKitC Pinout Guide — https://randomnerdtutorials.com/esp32-s3-devkitc-pinout-guide/
[17] Espressif, ESP32-S3 硬件设计指南 - 原理图设计 — https://docs.espressif.com/projects/esp-hardware-design-guidelines/zh_CN/latest/esp32s3/schematic-checklist.html
