# LH60 Socket 基线

> 当前 socket 基线文档；总体入口见 `docs/current-baseline.md`。历史第五轮拷问记录已吸收到本文。

## 1. 裁决

1. **以 siderakb PTH 镀铜几何为当前基线**（`SW_Gateron_LowProfile_HotSwap_PTH`）；
2. **新增各 U 数辅助封装**（Gateron LP PTH 1U–2.75U，键帽轮廓取自 ai03）；
3. **字母/符号键（1U、无需多配列）采用"正置 Gateron + 倒置 Choc V1"双座**；
4. **不承诺 Choc V2**：V2 角落定位脚会与 Gateron PTH 孔冲突，不能并入双座。

> Superseded：早期"以 beekeeb 纯 NPTH 几何为准、删除电气孔/THT"的判断已被后续 PTH
> 实测推翻。纯 NPTH 仍可作为余量更大的备选，不是当前主基线。

## 2. 双座几何验证（真实封装数值）

同一键位中心合并两套座子图案，中心开关孔取 φ5.25（Gateron 规格，Choc 居中销
更小可容纳）。铜 0.2 / 孔 0.25 间隙：

| 组合 | 结果 | 最紧余量 |
|---|---|---:|
| Gateron 0° + Choc V1 180° | ✅ 可行 | 跨座子 +0.62mm；整体 +0.33mm |
| Gateron 0° + Choc V1 0° | ❌ | −0.25mm（焊盘/孔重叠） |
| Gateron 0° + Choc V1V2 混合座 180° | ❌ | −0.25mm（V2 定位孔撞 Gateron φ3 孔） |

结论：**双座仅对 Choc V1 成立**；Choc V2 的定位孔 (5,−5.15) 倒置后落在
(−5,5.15)，与 Gateron 定位孔 (−4.4,4.7) 距离 0.75mm，孔壁重叠。除非放弃
Choc V2 兼容，否则无法并入双座。

KiCad 10 实测：双座封装自检 DRC 干净（0 footprint errors、0 孔/铜违规）。

### 2.1 同时焊两种座子的状态

双座的保守装配语义是"每键二选一焊接"：焊 Gateron 或焊 Choc V1。若目标是用户后续
免焊换轴，则同一 1U 键位需要 **两种 socket 同时焊接**。目前结论分层如下：

| 层面 | 结论 |
|---|---|
| 电气/钻孔 | ✅ 源封装复核通过；非合并孔在 0.2mm copper/hole clearance、0.25mm hole-to-hole 下无违规 |
| Choc V1 socket 外形 | ✅ Kailh `CPG135001S30` 官方/LCSC 规格图显示外形约 13.15×6.85mm，推荐 PCB 主孔中心距 5.00mm、孔径 φ3.00 |
| Gateron KS-33 开关孔位 | ✅ Gateron 官网规格书显示 15×15mm switch、中心孔 φ5.25，以及 5.00/3.20/5.75/4.70/2.60/4.40mm 等 PCB layout 标注 |
| Gateron hotswap socket 实体外形 | ⚠️ 未找到公开官方 socket 外形图；需实物测量或 coupon 验证 |

因此：**可以把双座同时焊接作为免焊换轴目标保留，但量产承诺前必须做 1U coupon 实物验证**。

### 2.2 Courtyard 修正

初版封装沿用了 ai03 的 courtyard（按 ai03 镜像几何的座子轮廓画的），与
beekeeb 座子焊盘对不上（如 pad1 在 x=−8.075，ai03 courtyard 只到 −6.65）。
中间版本曾改用 16.5×16.5 / 20×15 mm 包围方框，但会把座体凹槽和两套座子之间的
空白区误判为占用空间。

当前版本使用真实 `B.CrtYd`：对底面塑胶座体、金属端子和完整 land pattern
（SMD 焊盘、铜桥、PTH 焊环）的几何并集整体外扩 0.25 mm。Gateron 单座是一套闭合
轮廓；双座保留 Gateron 与旋转 180° Choc V1 两套独立闭合轮廓。键帽包络移至
`Dwgs.User`，不再占用生产 `F.SilkS`。

### 2.3 "保留镀铜" 验证

**修正（2026-08-15）：保留镀铜不影响方案，两个方案实测均成立。**

用户把 RShift 五座子换用 siderakb `HotSwap_PTH`（镀铜）并调整了位置（9.75–11.5u，
两个 1u Fn 用 ±90°）后实测 DRC 干净；我带网络复测 + 独立几何复核均通过
（仅一处 0.07mm 制造级紧点，见下）。双座（Gateron PTH 0° + Choc V1 PTH 180°，
四焊盘挂不同网络）DRC 实测同样 0 违规。

先前"镀铜必失败（−0.25mm）"的结论有误，原因：
1. **旋转方向用反**：KiCad 正角度为 (x,y)→(y,−x)（y 向下屏幕系），先前计算
   用了标准数学逆时针，±90° 座子位置全部镜像错位；
2. 双座计算未合并中心孔（φ5.25 与 φ3.429 重叠被误算成冲突）；
3. KiCad 实测不报"焊环 vs 邻座中心 NPTH"0.07mm 间隙（min_hole_clearance 0.2
   未强制 NPTH-焊环）。

**唯一制造紧点**：Shift-C（rot180）的镀铜引脚焊环（φ4）与 Fn-B 中心孔
（φ5.25）Y 向仅 0.07mm。DRC 不报，但钻孔偏置 ±0.1mm 可能蹭铜；建议该对
改纯 NPTH（清 0.57mm）或把 Fn-B 右移 0.2mm。

结论：**可全程使用 siderakb PTH（镀铜）版**，无底座直焊能力顺带保留；
纯 NPTH（beekeeb/lh60_sockets）作为余量更大的备选。

## 3. 使用注意事项

- 双座封装焊盘编号：1/2 = Gateron，3/4 = Choc；四个焊盘同属一键，接同一行列网络；
- Choc 座焊 180°、Choc 轴也旋转 180° 插入（键帽沿十字轴旋转不受影响）；
- 默认每键只焊一个座子；若追求用户免焊换轴，可两种座子都焊，但必须先通过实物 coupon；
- 双座仅 1U（字母/符号区）；需多配列的键仍用单 Gateron 座 + 布局替代方案。

## 4. 交付

`lib/lh60-sockets/`：Gateron-LP-Hotswap-Socket-{1,1.25,1.5,1.75,2,2.25,2.75}U
+ Gateron-LP-or-ChocV1-Hotswap-Socket-1U，已注册 fp-lib-table（`lh60_sockets`）。
