# lh60-sockets — LH60 座子库（siderakb PTH 基底 + U 线框）

本版本**基于 siderakb `SW_Gateron_LowProfile_HotSwap_PTH`（镀铜电气孔）**，
增加各 U 数的键帽包络、真实底面装配轮廓与 courtyard。旧版（beekeeb 纯 NPTH）已删除。

## 封装清单

| 文件 | 说明 |
|---|---|
| `Gateron-LP-Hotswap-Socket-1U / 1.25U / 1.5U / 1.75U / 2U / 2.25U / 2.75U` | Gateron LP 热插拔座（PTH 镀铜），仅 Gateron |
| `Gateron-LP-or-ChocV1-Hotswap-Socket-1U` | 双兼容：正置 Gateron + 倒置 180° Choc V1；两套触点都使用 logical pad 1/2。默认按订单二选一焊接；若要支持用户免焊换轴，可尝试两种座子同时贴装，但需实物 coupon 验证机械干涉 |

## 图层约定

- `Dwgs.User`：外圈键帽包络，宽 = U×19.05、高 19.05 mm、中心对齐；
- `F.SilkS`：不放键帽网格，避免相邻键位形成生产丝印重叠；
- `B.Fab`：底面座体真实轮廓；双座同时显示 Gateron 与 Choc V1，并用 `G`/`C`
  线框标记装配方向；
- `B.CrtYd`：底面座体与完整 land pattern 的几何并集向外偏移 0.25 mm，
  线宽 0.05 mm；双座保留两套独立轮廓；
- 不增加 `F.CrtYd`：顶面的开关和定位板机械约束由整板结构设计负责。
- 所有座子 footprint 都设置 `exclude_from_pos_files`，手焊座子不进入 PnP
  坐标文件，但仍保留 BOM 语义。
- 单座关联 Gateron STEP；双座同时关联 Gateron 与 Choc STEP，便于在 KiCad 3D
  Viewer 中检查两套座体。

封装图形由 `tools/update_socket_library.py` 计算并通过 Konnect MCP
`set_footprint_graphics` 原子写入，不直接编辑 `.kicad_mod`。

## 双座（1U）

Gateron PTH 0° + Choc V1 PTH 180°，中心开关孔合并为 φ5.25（NPTH）。
Gateron 与 Choc 两套 thru + smd 触点都编号为 1/2；同号的多个铜形状表示同一
逻辑连接，布线只需连接该按键的行列网络。

电气/钻孔层面已经按源封装复核通过：非合并孔在 0.2mm copper/hole clearance、
0.25mm hole-to-hole 阈值下无违规。若两种座子同时焊接，目标是让用户后续无需焊接
即可在 Gateron LP 与 Choc V1 之间换轴；但当前仍需实物验证 Gateron socket 塑胶本体
与 Kailh Choc V1 socket 本体不会机械干涉。Kailh `CPG135001S30` 官方/LCSC 图纸显示
Choc V1 socket 外形约 13.15×6.85mm，推荐 PCB layout 主孔中心距 5.00mm、孔径 φ3.00；
Gateron 官网可取得 KS-33 开关规格书与 PCB layout，但未找到公开的 Gateron LP hotswap
socket 独立外形图。

**Choc V2 无法并入**：其定位孔 (5,−5.15) 倒置后落在 (−5,5.15)，与 Gateron 的 φ3
孔距离 0.75mm，孔壁重叠（实测 −0.25）。

## 可复现 Coupon

`test/generate_socket_coupons.py` 只通过 Konnect MCP 创建并放置 footprint：

```bash
python test/generate_socket_coupons.py --plan
python test/generate_socket_coupons.py --apply

KICAD_CLI=~/.local/bin/kicad-cli \
  python -m unittest -v test.test_socket_library_update test.test_lh60_sockets
```

- `test/socket-clean.kicad_pcb`：包含 8 个 canonical footprint，预期
  `0 violations / 0 unconnected items`。
- `test/socket-conflicts.kicad_pcb`：两个 1U Gateron footprint 同向、中心距
  17.25 mm，预期只报告 `courtyards_overlap`，用于证明真实 `B.CrtYd` 能发现
  装配冲突。

## 关于 `SW_Kailh_Choc_V1V2_HotSwap_Hybrid` 右上角铜通孔

那是 **Choc V2 开关定位销的过孔**（混合座为兼容 V1/V2 而设，镀铜）。双座方案
不用混合座（混合座 180° 时该孔撞 Gateron 孔），故本库不含它；`keysw_siderakb`
原库中的混合座保持原样，仅作独立封装参考。

## 来源与协议

- 座子几何：siderakb/key-switches.pretty `SW_Gateron_LowProfile_HotSwap_PTH`
  与 `SW_Kailh_Choc_V1_HotSwap_PTH`（CERN-OHL-P v2），未改几何；
- 键帽框与清理：本库自行生成。
