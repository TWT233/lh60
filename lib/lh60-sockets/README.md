# lh60-sockets — LH60 三系列热插拔座库

本库通过 `tools/lh60_design/socket_library.py` 参数化生成 Gateron LP、Kailh Choc
V1/V2、Gateron LP + Choc V1 三个系列。所有 KiCad 写入均通过 Konnect MCP 完成。

## 封装清单

每个系列覆盖 `1U / 1.25U / 1.5U / 1.75U / 2U / 2.25U / 2.75U`：

| 系列 | 说明 |
|---|---|
| `Gateron-LP-Hotswap-Socket-{U}` | Gateron LP / KS-33 PTH 热插拔座 |
| `Kailh-Choc-V1V2-Hotswap-Socket-{U}` | Kailh Choc V1 / V2 混合热插拔座 |
| `Gateron-LP-or-ChocV1-Hotswap-Socket-{U}` | 正置 Gateron LP + 倒置 Choc V1 双座 |

## 图层约定

- `Dwgs.User`：外圈键帽包络，宽 = U×19.05、高 19.05 mm、中心对齐；
- `F.SilkS`：不放键帽网格，避免相邻键位形成生产丝印重叠；
- `B.Fab`：底面座体真实轮廓，使用 `G` / `K` / `C` 标记装配方向；
- `B.CrtYd`：底面座体与完整 land pattern 的几何并集整体外扩 0.50 mm；
  双座先合并两套已外扩轮廓，避免 courtyard 自交；
- 不增加 `F.CrtYd`：顶面的开关和定位板机械约束由整板结构设计负责。
- 所有座子 footprint 都设置 `exclude_from_pos_files`，手焊座子不进入 PnP
  坐标文件，但仍保留 BOM 语义。
- 单 G / 单 K 各关联一套 STEP；双座同时关联 Gateron 与 Choc STEP。

同系列各 U 数只有 `Dwgs.User` 键帽包络不同；pad、`B.Fab`、`B.CrtYd`、属性和
模型合同完全一致。

## 双座

Gateron PTH 0° + Choc V1 PTH 180°，中心开关孔合并为 φ5.25（NPTH）。
Gateron 与 Choc 两套 thru + smd 触点都编号为 1/2；同号的多个铜形状表示同一
逻辑连接，布线只需连接该按键的行列网络。

双座目标是让用户在 Gateron LP 与 Choc V1 之间免焊换轴，因此生产板默认同时焊接
两种 socket。KiCad 几何与临时 clean coupon DRC 已通过，但量产批准前仍必须制造
实物 coupon，验证两种 socket 同时焊接后的插入、锁定、拔出和导通。

**Choc V2 无法并入**：其定位孔 (5,−5.15) 倒置后落在 (−5,5.15)，与 Gateron 的 φ3
孔距离 0.75mm，孔壁重叠（实测 −0.25）。

## 临时 Coupon

生产验证只通过 Konnect MCP 在 `/tmp` 创建临时 KiCad coupon，检查 footprint
inventory、KiCad 解析和 DRC；仓库不提交测试 KiCad 工程。当前 21 件 clean
coupon 的 KiCad 10 DRC 结果为 `0 violations / 0 unconnected items`。

## 关于 `SW_Kailh_Choc_V1V2_HotSwap_Hybrid` 右上角铜通孔

那是 **Choc V2 开关定位销的过孔**（混合座为兼容 V1/V2 而设，镀铜）。双座方案
不用混合座（混合座 180° 时该孔撞 Gateron 孔），故本库不含它；`keysw_siderakb`
原库中的混合座保持原样，仅作独立封装参考。

## 来源与协议

- 座子几何：siderakb/key-switches.pretty `SW_Gateron_LowProfile_HotSwap_PTH`
  、`SW_Kailh_Choc_V1_HotSwap_PTH` 与
  `SW_Kailh_Choc_V1V2_HotSwap_Hybrid`（CERN-OHL-P v2）；
- 3D：仓库内已审计的 Gateron KS-33 与 Kailh Choc socket STEP；
- 参数化键帽框、真实 courtyard 与生成器：LH60 自有。
