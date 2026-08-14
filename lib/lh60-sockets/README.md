# lh60-sockets — LH60 座子库（siderakb PTH 基底 + U 线框）

本版本**基于 siderakb `SW_Gateron_LowProfile_HotSwap_PTH`（镀铜电气孔）**，
仅增加各 U 数的外圈键帽线框，并做噪声清理。旧版（beekeeb 纯 NPTH）已删除。

## 封装清单

| 文件 | 说明 |
|---|---|
| `Gateron-LP-Hotswap-Socket-1U / 1.25U / 1.5U / 1.75U / 2U / 2.25U / 2.75U` | Gateron LP 热插拔座（PTH 镀铜），仅 Gateron |
| `Gateron-LP-or-ChocV1-Hotswap-Socket-1U` | 双兼容：正置 Gateron（焊盘 1/2）+ 倒置 180° Choc V1（焊盘 3/4）。默认按订单二选一焊接；若要支持用户免焊换轴，可尝试两种座子同时贴装，但需实物 coupon 验证机械干涉 |

## 清理与线框（按需求 1–3、5）

- **无 courtyard**（F/B.CrtYd 全部删除）——消除多座子重叠时的 courtyard 检查噪声；
- **无 F.Fab 图形**——只保留隐藏的 value 文字；
- **F.SilkS 只画外圈键帽框**（`fp_rect`，宽 = U×19.05，高 19.05，中心对齐），
  原 siderakb 丝印全部删除，不画内圈轴框；
- B.SilkS / B.Fab 保持 siderakb 原样（座子侧参考）。

## 双座（1U）

Gateron PTH 0° + Choc V1 PTH 180°，中心开关孔合并为 φ5.25（NPTH）。
焊盘 1/2 = Gateron（thru + smd），3/4 = Choc V1（thru + smd）；四焊盘属同一
按键的替代触点，布线接同一行列网络。

电气/钻孔层面已经按源封装复核通过：非合并孔在 0.2mm copper/hole clearance、
0.25mm hole-to-hole 阈值下无违规。若两种座子同时焊接，目标是让用户后续无需焊接
即可在 Gateron LP 与 Choc V1 之间换轴；但当前仍需实物验证 Gateron socket 塑胶本体
与 Kailh Choc V1 socket 本体不会机械干涉。Kailh `CPG135001S30` 官方/LCSC 图纸显示
Choc V1 socket 外形约 13.15×6.85mm，推荐 PCB layout 主孔中心距 5.00mm、孔径 φ3.00；
Gateron 官网可取得 KS-33 开关规格书与 PCB layout，但未找到公开的 Gateron LP hotswap
socket 独立外形图。

**Choc V2 无法并入**：其定位孔 (5,−5.15) 倒置后落在 (−5,5.15)，与 Gateron 的 φ3
孔距离 0.75mm，孔壁重叠（实测 −0.25）。

## 关于 `SW_Kailh_Choc_V1V2_HotSwap_Hybrid` 右上角铜通孔

那是 **Choc V2 开关定位销的过孔**（混合座为兼容 V1/V2 而设，镀铜）。双座方案
不用混合座（混合座 180° 时该孔撞 Gateron 孔），故本库不含它；`keysw_siderakb`
原库中的混合座保持原样，仅作独立封装参考。

## 来源与协议

- 座子几何：siderakb/key-switches.pretty `SW_Gateron_LowProfile_HotSwap_PTH`
  与 `SW_Kailh_Choc_V1_HotSwap_PTH`（CERN-OHL-P v2），未改几何；
- 键帽框与清理：本库自行生成。
