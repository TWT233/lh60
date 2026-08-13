# 第三方库来源

本目录内的库均为从社区仓库 vendored 的固定版本（不含 `.git` 元数据），用于 lh60-rp2040-v2 的 KiCad 设计。

| 目录 | 上游仓库 | 提交 | 日期 | 许可证 | 用途 |
|---|---|---|---|---|---|
| `kiswitch/` | https://github.com/kiswitch/kiswitch | `aefcf65038d48d2666ff14530d482be3c350fa6e` | 2024-11-28 | MIT + CC-BY-SA（双许可） | 开关/热插拔座封装，含 Choc V1/V2 双兼容座 `Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_Choc_V1V2_*` |
| `MX_Alps_Hybrid/` | https://github.com/ai03-2725/MX_Alps_Hybrid | `cdbfc72a211525b4e024d4cd312ce8b922918018` | 2024-03-06 | MIT | MX/Alps/Choc 开关封装及热插拔座 |
| `Type-C.pretty/` | https://github.com/ai03-2725/Type-C.pretty | `fecd1a97dee885e7daf32da80dfa47e726d59529` | 2020-09-28 | 无 LICENSE 文件 | USB-C 连接器封装（HRO 31-M-12 等） |
| `random-keyboard-parts.pretty/` | https://github.com/ai03-2725/random-keyboard-parts.pretty | `b0bedf4c33a4efd241614130dea3c80140f6f2e7` | 2020-04-04 | 无 LICENSE 文件 | 二极管（SOD-123）、复位键、杂项封装与符号 |

## 注意事项

- kiswitch 的 README 注明 v2.1.2 之前的版本存在 Choc V1 尺寸错误；本仓库使用的提交在其之后，尺寸已修复。
- kiswitch 自带 3D 模型（约 34MB）未入库以控制仓库体积；如需 3D 预览，可按上表提交号从上游重新取回 `library/3dmodels/`。
- kiswitch 仅含 Cherry MX 卫星轴封装（`Mounting_Keyboard_Stabilizer.pretty`），**无矮轴（Choc）卫星轴封装**；矮轴卫星轴封装需另行处理（自绘或另找社区封装）。
- 开关符号未随库提供，原理图中使用 KiCad 标准库 `Switch` 符号即可。
