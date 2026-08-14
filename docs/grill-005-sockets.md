# LH60 拷问报告 #005：定库与双座方案

> 生成：2026-08-15 · grill-with-docs 第五轮

## 1. 裁决

1. **以 siderakb/beekeeb 量产几何为准**（B.Cu SMD + 3 个 NPTH，无 THT 引脚/电气孔）；
2. **新增各 U 数辅助封装**（Gateron LP 纯座子 1U–2.75U，键帽轮廓取自 ai03）；
3. **字母/符号键（1U、无需多配列）采用"正置 Gateron + 倒置 Choc V1"双座**，
   用户可按区装 Gateron LP 或 Choc V1 轴。

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

## 3. 使用注意事项

- 双座封装焊盘编号：1/2 = Gateron，3/4 = Choc；四个焊盘同属一键，接同一行列网络；
- Choc 座焊 180°、Choc 轴也旋转 180° 插入（键帽沿十字轴旋转不受影响）；
- 每键只焊一个座子；未焊座子的备用焊盘空置即可；
- 双座仅 1U（字母/符号区）；需多配列的键仍用单 Gateron 座 + 布局替代方案。

## 4. 交付

`lib/lh60-sockets/`：Gateron-LP-Hotswap-Socket-{1,1.25,1.5,1.75,2,2.25,2.75}U
+ Gateron-LP-or-ChocV1-Hotswap-Socket-1U，已注册 fp-lib-table（`lh60_sockets`）。
