# 封装库（2026-11-23 引入）

工程原先**没有任何封装库**：所有封装都是内联（inline）写死在 `.kicad_pcb` 里，
由 `gen_pcb.py` 从 `kbd-esp32s3_v1_template.kicad_pcb` 复制。这样虽然自包含，
但没法核对尺寸、也没法在 KiCad 里替换。这里补上两个权威来源。

## 目录

| 目录 | 来源 | 用途 |
|---|---|---|
| `kicad-official/` | KiCad 官方库 `kicad-footprints`（GitLab `kicad/libraries`，master） | 排针、SOIC、0603、USB-C、EC11、安装孔、SK6812、Cherry MX 标准件 |
| `MX_Alps_Hybrid/` | ai03-2725/MX_Alps_Hybrid（GitHub，master） | MX / Alps / Kailh Choc 轴座，含 hotswap 与多单位大键 |

共 306 个 `.kicad_mod`，2.1 MB。

## kicad-official 具体包含

| 库 | 封装 |
|---|---|
| Button_Switch_Keyboard | SW_Cherry_MX_1.00u/2.00u/2.25u/6.25u_PCB、SW_Cherry_MX_1.00u_Plate |
| Connector_PinHeader_2.54mm | PinHeader_1x20 / 1x22_P2.54mm_Vertical |
| Package_SO | SOIC-16W_7.5x10.3mm_P1.27mm |
| Resistor_SMD / Capacitor_SMD | R_0603_1608Metric / C_0603_1608Metric |
| MountingHole | MountingHole_3.2mm_M3、MountingHole_2mm |
| Rotary_Encoder | RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm |
| Connector_USB | USB_C_Receptacle_GCT_USB4085 |
| LED_SMD | LED_SK6812MINI_PLCC4_3.5x3.5mm_P1.75mm、LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount |
| TestPoint | TestPoint_Plated_Hole_D2.0mm |

## 用法

`kbd-esp32s3/fp-lib-table` 已把这两个库挂进工程。用 KiCad 打开 `kbd-esp32s3.kicad_pro`
后，符号/封装浏览器里即可直接调用（前缀 `ko:` 与 `mx:`）。

## 已核对结论

`check_libs.py` 会把板上每个封装与库文件逐焊盘比对（旋转/平移不变的两两间距特征）：

- **完全一致**：PinHeader_1x22、SOIC-16W、R/C 0603、EC11、USB4085、MountingHole_3.2mm
- **MX 轴座**：孔位与 `MXOnly-1U-NoLED` 的两两间距**完全相同**（本封装是 180° 放置，
  电气对称，不影响装配）；孔径按热插拔放大为 3.0mm
- **库中无同名**：`SW_MX_HotSwap_PTH`（自绘热插拔）、`LED_SK6812MINI-E`（自绘）、
  主控模块本体轮廓（自绘机械占位）

> 注意：库文件只用于核对与替换，不参与 `gen_pcb.py` 的生成流程——
> 生成器仍以 `kbd_design.py` 的常量为唯一真相源，保证脚本可重跑。
