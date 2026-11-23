# ESP32-S3 客制化键盘

一个基于 **Waveshare ESP32-S3-DEV-KIT-N16R8-M** 的 75% 客制化键盘工程，采用 **74HC165 级联移位寄存器**读键（非矩阵扫描），仅兼容 **Cherry MX 及兼容轴**。

> 状态：**原理图 + PCB 实质设计完成，尚未全布线**（属于可继续开发的骨架，非可投产图纸）。
> 更新日期：2026-11-23

## 特性

- **主控**：ESP32-S3-DEV-KIT-N16R8-M（16MB Flash / 8MB PSRAM），原生 USB HID。
- **读键方案**：10 片 74HC165 级联，每键独立输入 + 10kΩ 上拉，无矩阵、无二极管。
- **配列**：精确 75 键 / 6 行，方向键为标准**倒 T** 布局，Space 8.25u。
- **轴体**：75 个纯 MX 热插拔轴座（`SW_MX_HotSwap_PTH`）。
- **卫星轴**：plate-mount，4 个大键（Bksp / Enter / LShift / Space）。
- **定位板**：已建好，含键孔 / 卫星轴一体孔 / M3 孔 / 开发板避让窗，可发厂切割。
- **校验**：电气短路 **0**、走线交叉 **0**，原理图与 PCB 网络全部匹配。

## 目录结构

| 路径 | 说明 |
|---|---|
| [`kbd-esp32s3/`](kbd-esp32s3/) | KiCad 工程主体（原理图、PCB、定位板、生成脚本、预览图） |
| [`kbd-esp32s3/README.md`](kbd-esp32s3/README.md) | **工程详细文档**：电路、配列、元件、Pinout、网络、DRC、剩余边界 |
| [`ESP32-S3客制化键盘设计方案.md`](ESP32-S3客制化键盘设计方案.md) | 设计方案与选型（含主控选型、可行性结论） |
| [`ESP32-S3键盘方案_可行性验证报告.md`](ESP32-S3键盘方案_可行性验证报告.md) | 联网验证报告：GPIO / I2C / USB / PCB 设计规范 |

## 关键文件速览

- `kbd-esp32s3/kbd-esp32s3.kicad_sch` — 原理图（74HC165 级联读键）
- `kbd-esp32s3/kbd-esp32s3.kicad_pcb` — PCB（75 键 + 纯 MX 轴座 + 网络分配）
- `kbd-esp32s3/kbd-plate.dxf` — 定位板切割文件（发厂用）
- `kbd-esp32s3/pcb_preview.png` — PCB 2D 预览
- `kbd-esp32s3/render_keyboard.png` — 成品渲染图

完整的工程文件清单、电路说明、开发板 Pinout、卫星轴坐标和验证状态见 **[工程详细文档](kbd-esp32s3/README.md)**。

## 复现

工程文件由脚本生成，可在 `kbd-esp32s3/` 下重跑（需要 KiCad 9 的 `pcbnew` Python 模块）：

```bash
cd kbd-esp32s3
python3 gen_sch.py          # 原理图
python3 gen_pcb.py          # PCB（会覆盖 .kicad_pcb）
python3 gen_stabilizers.py  # 卫星轴开孔坐标表 + 示意图
python3 gen_plate.py        # 定位板 + DXF
python3 render_keyboard.py  # 成品渲染图
```

## 下一步

- 在 KiCad GUI 中完成 **397 条飞线**的布线（按键扫描线 / 电源 / 时钟 / 编码器 / USB）。
- 补副屏（SPI 长条屏）接口、外壳配合、实物焊接验证。
- 详情见 [工程详细文档 · 剩余边界](kbd-esp32s3/README.md#剩余边界下一步)。
