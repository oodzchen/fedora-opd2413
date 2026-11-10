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

## 在 kern2 之上的补丁（`opd2413/`）

| 补丁 | 内容 | 真机结果 |
|---|---|---|
| `1411-drm-panel-nt36536-keep-supplies-on-across-unprepare.patch` | 熄屏时面板保持供电，亮屏时复位并重发初始化命令 | 2026-11-11 用户目视确认多次熄屏亮屏都恢复画面 |
| `1412-drm-panel-nt36536-offer-only-120hz.patch` | 只报告 120 Hz 模式（60/30 Hz 出不了画面） | 显示设置只剩 120 Hz |

`experiments/` 里是排查用的诊断补丁（读回面板电源状态、保持供电的第一版），不进正式内核。

### 构建方法（M1 期间）

kern2 的源码树不在任何仓库里，是 armada 仓库忽略目录下的一棵已编译的树
（`output/opd2413-stage4/armada-port/source`，最后一次构建是带失败实验 `1410` 的 grey1）。复现步骤：

```sh
A=~/github/armada/output/opd2413-stage4
cp -a --reflink=always $A/armada-port/source out/kernel-tree           # btrfs 上瞬间完成
cp $A/grey1/ktz8866.c.before out/kernel-tree/drivers/video/backlight/ktz8866.c   # 去掉 1410，回到 kern2
cd out/kernel-tree
patch -p1 < ../../kernel/opd2413/1411-*.patch
patch -p1 < ../../kernel/opd2413/1412-*.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-<N>.opd2413 -j15 Image modules
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- LOCALVERSION=-<N>.opd2413 \
     INSTALL_MOD_PATH=<stage> INSTALL_MOD_STRIP=1 modules_install
```

然后把 `arch/arm64/boot/Image` 拷成 `<stage>/lib/modules/<kver>/vmlinuz`，把 kern2 的 `dtb/` 目录拷进去，
打成 `lib/modules/<kver>/…` 结构的 tar.zst，用 `tools/build-kernel-rpm.sh` 打包。

规则：

- 版本号 `7.2.6-<N>.opd2413`，`N` 每次构建加一、不复用（已用：1 = 原始 kern2 的 `7.2.6`，2 = 1411+1412）。
  **一个版本号不能是另一个的前缀**：卸载内核时 kernel-install 会删除所有 `fedora-<kver>*.conf`，
  2026-11-11 卸载 `7.2.6` 时把 `7.2.6-diag1`、`7.2.6-diag2` 的条目一起删了。
- 必须 `INSTALL_MOD_STRIP=1`（否则模块 2.2 GB）；它只去掉调试段，模块的 `.BTF` 保留。
- 内核和模块必须同次构建、一起安装。

这套做法是 M1 的权宜之计（技术债 #4），M3 换成 Fedora 的 kernel.spec。

## 后续（M3）

以 Fedora 45 的内核为基线重建补丁序列，见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5。
届时新序列放在新的目录里，`armada-7.2.6/` 保留到新内核真机通过为止。
