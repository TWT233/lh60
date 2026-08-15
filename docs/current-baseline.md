# LH60 当前设计基线

> 当前结论入口。历史拷问记录已归档到 `docs/archive/`，只用于追溯推导过程。

## 已定

- 主控：Waveshare RP2040-Tiny，USB 通过 8 针 FPC 分体引出。
- 键距：19.05 × 19.05 mm，15u 键区宽 285.75 mm，面向 MX 键帽生态。
- 主轴：Gateron LP / KS-33。
- 主座：siderakb `SW_Gateron_LowProfile_HotSwap_PTH` 镀铜几何。
- Socket 库：单 G、单 K（Choc V1/V2）和 Gateron LP + Choc V1 Dual 三系列，
  均覆盖 1U / 1.25U / 1.5U / 1.75U / 2U / 2.25U / 2.75U。
- 固定且无重叠的键位默认使用 Dual，并同时焊接两种 socket。
- Choc V2：不纳入 Gateron 双座。V2 角落定位脚与 Gateron PTH 孔冲突。
- 底排：保留方向键版底排；旧 6.25u 标准空格版不在当前范围。
- ISO Enter：不在当前范围。
- 当前配列：76 个物理 socket、70 个逻辑节点；完整 u/mm 坐标与共享关系见
  `docs/layout-current.md`。
- 矩阵：10 × 7，`COL0..COL9 = GP0..GP9`，
  `ROW0..ROW6 = GP10..GP15, GP26`，空闲 `GP27..GP29`。

## 多配列功能区

需要继续支持和验证的多配列区：

| 区域 | 支持方案 | 状态 |
|---|---|---|
| 顶排右端 | 2u / 1u + 1u | 待按 Gateron PTH 方案重新画通 |
| Enter | 2.25u ANSI / 1u Fn + 1.25u Enter | 待按 Gateron PTH 方案重新画通 |
| LShift | 2.25u / 1u Fn + 1.25u Shift | 待按 Gateron PTH 方案重新画通 |
| RShift | 2.75u / 1.75u Shift + 1u Fn / 1u Fn + 1.75u Shift | 已实测三方案共存，需在最终板复现并清制造紧点 |

## Socket 规则

- 固定键默认使用 Gateron + Choc V1 Dual；U 数不决定是否使用 stabilizer。
- 多配列区从单 Gateron LP PTH 座开始重新求解；加入 Choc V1 后仍满足生产规则时
  才升级为 Dual。
- 双座的两套物理触点共享 logical pad 1/2，原理图与布线不再暴露 3/4。
- 双座目标是两种 socket 同时焊接；量产批准前必须做实物 coupon 验证插拔和导通。
- 当前自有座子 footprint 使用 `Dwgs.User` 键帽包络、真实 `B.Fab`、
  外扩 0.50 mm 的 land-pattern-aware `B.CrtYd`、PnP 排除与 STEP 模型。
- 独立插件孔/开关孔孔边间距目标至少 0.50 mm，绝不低于 0.45 mm。
- 生产验证通过 Konnect MCP 在 `/tmp` 创建临时 coupon；仓库不提交测试 KiCad 工程。
- Kailh `CPG135001S30` 官方/LCSC 图纸显示 Choc V1 socket 外形约 13.15 × 6.85 mm，推荐 PCB 主孔中心距 5.00 mm、孔径 3.00 mm。
- Gateron 官网可取得 KS-33 switch 规格书和 PCB layout，但未找到公开的 Gateron LP hotswap socket 独立外形图。

## 当前文档入口

- `docs/layout-current.md`：当前 15u 物理坐标、70 节点和 10 × 7 GPIO 映射。
- `docs/glossary.md`：术语表和当前口径。
- `docs/socket-baseline.md`：socket 基线、PTH 结论、Choc V2 排除原因、免焊换轴验证状态。
- `lib/lh60-sockets/README.md`：自有 footprint 库说明。
- `docs/archive/`：历史推导，可能含 superseded 结论。
