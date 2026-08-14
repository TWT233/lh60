# lh60-sockets — LH60 项目自用座子库

以 **siderakb/beekeeb 量产几何为准**（Gateron LP 热插拔座：B.Cu SMD 焊盘 +
3 个非镀通孔，无 THT 引脚、无电气孔），键帽轮廓取自 ai03 MX_V2 的图形。

座子几何（相对中心）：

| 项目 | 位置 | 尺寸 |
|---|---|---:|
| 开关孔 NPTH | (0,0) | φ5.25 |
| 定位孔 NPTH | (−4.4,4.7) / (2.6,5.75) | φ3 |
| SMD 焊盘（B.Cu） | (−8.075,4.7) / (6.275,5.75) | 2.5×2.55 |

## 封装清单

**Gateron LP 纯座子（各 U 数辅助封装）**——键帽轮廓按 U 数缩放：

- `Gateron-LP-Hotswap-Socket-1U / 1.25U / 1.5U / 1.75U / 2U / 2.25U / 2.75U`

**Gateron LP 或 Choc V1 双座（1U，字母/符号区用）**：

- `Gateron-LP-or-ChocV1-Hotswap-Socket-1U`

  同一键位中心两套座子图案：正置 Gateron（焊盘 1/2，+y 半区）+ 倒置 180°
  Choc V1 热插拔座（焊盘 3/4，−y 半区）。跨座子最小余量 +0.62mm（实测 DRC 干净）。
  用法：每个键**只焊其中一个座子**；装 Gateron 轴用 1/2 焊盘，装 Choc V1 轴用
  3/4 焊盘（Choc 座焊 180° 朝向，Choc 轴也需旋转 180° 插入，键帽方向不受影响）。
  四个焊盘是同一按键的替代触点，布线时全部接同一行列网络。
  注意：**Choc V2 不可行**——其定位孔倒置后与 Gateron 的 φ3 孔冲突（−0.25mm）。

所有焊盘默认在 B.Cu（座子焊板底，与 Gateron 官方一致）；每键位中心放一个座子即可
（键帽包络只是图形，座子本身恒为 1U）。

## 来源与协议

- 座子几何：beekeeb Corne GLP（在售产品，MIT）量产 PCB 内嵌封装提取；与
  siderakb `HotSwap_THT` 同几何，删去了其"无底座直焊"兼容用的 THT 引脚/电气孔。
- 键帽轮廓图形：ai03-2725/MX_V2（MIT）`Gateron_KS33_Hotswap.pretty`。
- Choc V1 座子图案：siderakb/key-switches.pretty（CERN-OHL-P v2）。

协议：beekeeb Corne GLP（MIT）；几何源自 siderakb/key-switches.pretty
（CERN-OHL-P v2）。
