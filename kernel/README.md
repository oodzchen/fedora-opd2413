# 内核

## `armada-7.2.6/`：M1 使用的内核输入

从 armada 仓库 `oneplus-pad-2-pro` 分支提交 `f9fc784` 的 `packages/kernel/` 原样导入，没有改动：

| 路径 | 内容 |
|---|---|
| `BASE.env` | 上游版本：7.2.6 |
| `patches/series`、`patches/` | 补丁序列。OPD2413 专用的是 `1400`–`1409`；其余是 Armada 支持的各款掌机共用的补丁 |
| `PATCHES.md` | 每个补丁的来源、上游状态和修改说明 |
| `dts/` | 板级设备树，本机是 `sm8750-oneplus-pad2pro.dts` |
| `config/` | 在 defconfig 之上合并的配置片段 |
| `scripts/build-kernel.sh` | Armada 的构建脚本（kernel.org 源码包 + 序列 + 配置片段） |

M1 不重新编译，直接把已真机验证的构建产物打成 RPM：

```
tools/build-kernel-rpm.sh <armada>/output/opd2413-stage4/kern2/out/armada-kernel-7.2.6.tar.zst 7.2.6 1
```

该产物的 SHA-256 是 `7c6d84fae968b3dad37cf8224a388ee72d1d5ca3ab297aa39d6d112f35f731c7`，
内核与 1594 个模块同次构建（2026-11-04），对应上面的序列到 `1409` 为止。
产物里没有 `System.map` 和 `config`，需要配置时在运行中的系统读 `/proc/config.gz`。

模块带 BTF，必须与同次构建的内核配套使用。

## 后续（M3）

以 Fedora 45 的内核为基线重建补丁序列，见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5。
届时新序列放在新的目录里，`armada-7.2.6/` 保留到新内核真机通过为止。
