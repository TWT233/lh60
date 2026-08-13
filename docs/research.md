# LH60 v2 调研与数据笔记

## 1. Choc 矮轴尺寸标准

| 项目 | Choc V1 (PG1350) | Choc V2 (PG1353) |
|---|---|---|
| 外壳尺寸 | 15 × 15 mm | 15 × 15 mm（相同） |
| 定位板开孔 | 14 × 14 mm | 14 × 14 mm（与 MX 通用） |
| 总高 | 约 11.5 mm | 约 12.1 mm（略高） |
| PCB 中心孔 | 3.0 mm（中心柱 3.4） | 5.0 mm（中心柱 5.0） |
| 针脚 | 5 pin（含 2 固定脚） | 3 pin（无固定脚，需定位板） |
| 轴心 | Choc 专用矩形 | MX 十字 |
| 键程 | 预行程 1.5 / 总行程 3.0 mm | 预行程 1.3 / 总行程 3.2 mm |

- 键距没有强制标准：常规用 19.05×19.05；Kailh Choc 键帽按 **18×17**（宽×高）。
- 来源：deskthority（PG1350/PG1353）、Kailh 资料、beekeeb/kbd.news 对比。

## 2. PH60Slim-Choc 量产参考（commit 4ddc0fc）

- 60% ANSI 矮轴成品，用 kiswitch `SW_Hotswap_Kailh_Choc_V1V2_Plated_*`（镀金过孔版）。
- 矮轴卫星轴为 **plate-mount**，PCB 无需卫星轴封装，定位板开槽即可。
- 大键（Backspace/Enter/LShift/RShift）开关**旋转 90°**，6.25u 空格不转。
- 键距 19.05（本板改为 18）。
- BOM：61 轴 + 4×2u + 1×6.25u 卫星轴；6 个 M2 安装孔。
- 本地路径：`C:\Users\TWT23\Documents\kbd\.ref-ph60`

## 3. 旧 lh60 矩阵分析（已从 PCB 完整提取）

- 尺寸 285×94.6 mm、2 层、USB-C 底边出线；5 行 × 14 列矩阵，**79 个键座**。
- 共享规则（二极管=节点）：
  - 2u Backspace 与分裂右半（Del）共享 `ROW1/COL14`；分裂左半走空闲 `ROW5/COL6`。
  - ANSI Enter 与 ISO Enter 共享 `ROW3/COL14`。
  - LShift 2.25u 与分裂 1.25u 共享 `ROW4/COL2`；分裂 Fn 1u 独立 `ROW4/COL1`。
  - ANSI RShift 2.75u / 分裂 1.75u / ISO `\` 共享 `ROW4/COL13`；↑1u 与 ISO RShift 1.75u 共享 `ROW4/COL14`。
  - 空格 3u 与 6.25u 共享 `ROW5/COL4`；底排 Fn/Alt/Win 两套位置共享 `ROW5/COL11–13`。
- 新板按同样思路简化为 68 节点（见 layout-v2.md）。

## 4. Waveshare RP2040-Tiny

- 尺寸：23.5 × 18 × 2.1 mm；半孔主边，可直接焊载体板。
- 引出 20 GPIO：GPIO0–15、GPIO26–29；另有 3V3、GND、VSYS。
- 板上 8 针 FPC 座（分体式 USB）：接 USB-C 转接板，信号含 D+/D−、VSYS、GND、RUN、BOOT 等（以 Adapter V1.1 原理图为准）。
- 官方资料：
  - [RP2040-Tiny 原理图](https://files.waveshare.com/upload/7/7a/RP2040-Tiny_Schematic.pdf)
  - [V1.1 原理图](https://files.waveshare.com/upload/7/7f/RP2040-Tiny_V1.1_SCH.pdf)
  - [Adapter V1.1 原理图](https://files.waveshare.com/upload/3/35/RP2040-Tiny-Adapter_V1.1-SCH.pdf)
- 本地下载：`C:\Users\TWT23\Documents\kbd\.tmp-tiny-sch.pdf` / `.tmp-tiny-adapter-sch.pdf`

## 5. 社区库（已入库，来源/提交/许可证见 lib/README.md）

| 目录 | 来源 | 用途 |
|---|---|---|
| `lib/kiswitch/` | kiswitch/kiswitch（aefcf65，2024-11-28） | **Choc V1/V2 双兼容热插拔座**、MX 开关等 |
| `lib/MX_Alps_Hybrid/` | ai03（cdbfc72） | MX/Alps 开关封装 |
| `lib/Type-C.pretty/` | ai03（fecd1a9） | USB-C 连接器 |
| `lib/random-keyboard-parts.pretty/` | ai03（b0bedf4） | SOD-123、复位键等 |

> 已按提交号去掉 3D 模型以控制仓库体积；需要时可按提交号从上游取回。

## 6. 网络/工具备注

- 联网命令走代理 `localhost:45326`（HTTP_PROXY/HTTPS_PROXY/ALL_PROXY）。
- KiCad 10 已安装：`C:\Users\TWT23\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`（可做 DRC/导出验证）。
