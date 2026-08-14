# keysw-siderakb — siderakb/key-switches.pretty（vendored）

来源：https://github.com/siderakb/key-switches.pretty（2026-08 抓取，最新提交 2025-11）
协议：CERN-OHL-P v2（随库附 `LICENSE` 原文）。

本目录收录该库全部封装（33 个 .kicad_mod），未做几何修改；未收录 preview/ 与
scripts/（预览图见上游仓库）。本库无 3D 模型。

## 与 LH60 设计相关的内容

| 封装 | 说明 |
|---|---|
| `SW_Gateron_LowProfile_HotSwap_THT` | Gateron LP（KS-27/KS-33）热插拔座：B.Cu 焊盘 (−8.075,4.7)/(6.275,5.75) + NPTH 定位孔 (−4.4,4.7)/(2.6,5.75) + 中心孔 φ5.25，另有 2 个 THT 引脚 (−2.6,−5.75)/(4.4,−4.7) |
| `SW_Gateron_LowProfile_HotSwap_PTH` | 同上但定位孔镀铜（孔可直焊开关，不需要座子） |
| `SW_Kailh_Choc_V1_HotSwap*` | Choc V1 热插拔座（B.Cu SMD 焊盘 + NPTH） |
| `SW_Kailh_Choc_V1V2_HotSwap_Hybrid` | Choc V1/V2 混合热插拔座 |
| `SW_MX_HotSwap_THT/PTH*` | Kailh MX 热插拔座（THT 引脚 + B.Cu SMD） |

## 量产背书

beekeeb 的 Corne GLP（在售产品，BOM 使用 "Gateron Low Profile Hotswap
Sockets"）PCB 内嵌的 Gateron LP 热插拔封装与本库几何一致（B.Cu 焊盘 +
3 个 NPTH），且与 Gateron 官方"座子焊在 PCB 底部"的描述一致。

## 注意

- 上游 ai03 MX_V2 的 `Gateron-KS33-Hotswap` 几何与本库不同（F.Cu 焊盘、
  位置/孔径不同，且无 THT 引脚）；画 Gateron LP 座子时**建议以本库几何为
  准**（量产验证过）。
- `SW_Gateron_LowProfile_HotSwap_THT` 的 2 个 THT 引脚在 −y 侧；若要做
  "旋转 180° 多配列共存"，THT 版旋转后引脚会与邻座冲突，**应使用 PTH 版
  或 beekeeb 式纯 SMD+NPTH 几何**（旋转后金属件全落 −y 半区，9mm 中心距
  理论可行，中心孔下限约 5.55mm）。
