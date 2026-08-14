# LH60 术语表

> 随设计迭代持续补充；本会话由 `grill-with-docs` 工作流生成。

## 配列（Layout）

键盘按键的几何排布（位置、尺寸、行偏移），与键位语义（哪个键是什么功能）无关。本板只关心**几何**：无刻键帽，标签仅为占位。

## 60%

宽度 15 个键单元（15u）的标准键盘布局。本板 1u = 18 mm（横向），即整板键区 270 mm 宽。

## 热插拔座（Hot-swap socket）

预先焊在 PCB 背面的座子，用户把轴直接插入即可，无需焊接。本板当前主线是
Gateron LP / KS-33 PTH 镀铜座；普通 1U 可用 `Gateron-LP-or-ChocV1-Hotswap-Socket-1U`
兼容 Gateron LP 与 Choc V1。Choc V2 不纳入该双座封装。

## 0 焊接

指**最终用户**到手后不焊接：工厂完成座子、二极管、主控、USB 的装配，用户插轴、装键帽即用。不排除工厂焊接，也不排除用户为换配列而更换定位板。

## 矩阵节点（Matrix node）

矩阵中"一个 (行, 列)"交叉点，对应**一颗二极管**。多个物理座子可以共享一个节点（同一逻辑键的不同配列位置），此时它们接同一颗二极管。

## 共享节点

互斥的配列选项（如 2u Backspace 与分裂右半 1u）接同一节点，用户选哪种装配都不会出现矩阵冲突。

## 旋转避让（Rotated footprint）

把热插拔座封装旋转 0°/180°（倒置/正置）以交错焊盘。180° 旋转要求轴同步旋转（南北朝向），90° 不可行（轴针脚与座子孔位不对齐）。

> ⚠️ 本会话拷问发现：旋转只能解决焊盘交错，**无法解决座体/轴孔重叠**。
> 实测两座共存最小中心距：kiswitch V1/V2 座 同向 14.76 mm / 180° 13.22 mm；
> Kailh CPG151101S11（KaiHua contact）同向 16.20 mm / 180° 12.16 mm。
> 当前 KLE 冲突区中心距 9.0–11.25 mm，全部低于下限（见 ADR-0002、grill-002）。

## 冲突区（Conflict zone）

同一行内互斥配列选项（如 2u Backspace 与分裂 1u+1u）的座子中心距小于共存下限的区域；
这些区域内两套座子无法同时存在于同一块 PCB。

## Gateron LP（KS-33）

Kailh Choc 之外的另一种 15×15 mm 矮轴家族（Gateron 低剖面），MX 兼容轴心、标准键距 19.05 mm。
与 Choc 引脚布局不同；当前用自有 1U 双座封装与 Choc V1 兼容。Gateron LP 与
Choc V1/V2 hybrid 不能同中心叠加，原因是 Choc V2 角落定位脚会撞 Gateron PTH 孔。

## 键距（Key pitch）

相邻 1u 键中心距。本板已定 **19.05×19.05 mm（MX 键帽生态，15u = 285.75 mm）**；
Choc 紧凑生态的 18×17 mm（MBK/CFX/LDSA）不采用。KLE 单位（u）与 mm 换算按 19.05 执行。

## 卫星轴（Stabilizer）

大键（≥2u）键帽的平衡机构。Choc 矮轴生态用 **plate-mount**（装在定位板上），PCB 无需封装，但定位板必须按配列开槽。

## 定位板（Plate）

固定轴体的板件，也是卫星轴的载体。多配列意味着**每套配列需要一块对应的定位板**（3D 打印/CNC/激光切割）。

## 分裂（Split）

把一个大键拆成两个小键的配列选项，例如：2u Backspace → 1u+1u；2.25u Enter → 1u Fn + 1.25u Enter；2.25u LShift → 1u Fn + 1.25u Shift。

## Choc V1 / V2

Kailh 矮轴两代：V1（PG1350，5 针含固定脚、Choc 专用轴心）、V2（PG1353，3 针、MX 十字轴心）。外壳同为 15×15 mm、定位板开孔 14×14，键帽互不通用。双兼容座同时吃两种。
在 Choc-only 设计中可用 V1/V2 hybrid footprint 兼容两代；在本板的 Gateron+Choc
1U 双座中只支持 Choc V1，不支持 Choc V2。

## 18×17

Choc 键帽生态的紧凑键距标准：横向 18 mm × 纵向 17 mm（MBK/Chocfox/LDSA）。MX 轴是 19.05×19.05，两者不能混在同一块板上。

## RP2040-Tiny

Waveshare 的 RP2040 最小模块（23.5×18×2.1 mm），引出 20 个 GPIO（GPIO0–15 + GPIO26–29），半孔主边、可直接贴载体板；USB 用板上 8 针 FPC 分体引出。

## KLE

keyboard-layout-editor.com 的配列 JSON 格式；同一行多个数组表示互斥的配列选项（几何上重叠的备选键）。

## ADR

Architecture Decision Record：记录一个决策的背景、选项、结论与后果，随设计沉淀。
