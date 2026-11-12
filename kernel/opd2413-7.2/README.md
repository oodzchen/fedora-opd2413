# 7.2.15 内核（M3 的基线）

内核 3（`7.2.6-3.opd2413`）的全部补丁移到 Linux 7.2.15，与 erhai v0.7.2 的基础（erhai 仓库 `497791a0a` "Linux 7.2.15"）对齐。
功能不变，只换上游版本；之后的 erhai 功能在这个基线上逐项加（[docs/M3-FEATURES.md](../../docs/M3-FEATURES.md)）。

## 输入

| 输入 | 来源 |
|---|---|
| 上游源码 | erhai 仓库提交 `497791a0a` 的 `git archive`（即 Linux 7.2.15） |
| 补丁序列、板级 DTS | `kernel/armada-7.2.6/`（302 项） |
| 本机补丁 | `kernel/opd2413/1411`、`1412` |
| 配置 | 内核 3 的 `.config` + `olddefconfig`，关闭 `LOCALVERSION_AUTO`（源码在 git 树里时它会给版本号加 `-g<哈希>`） |

应用：`tools/kernel/apply-armada-series.sh <干净的 7.2.15 树>`，全部严格匹配（`patch -F0`，每个 hunk 都要成功）。

## 与 7.2.6 序列的差别

| 补丁 | 处理 | 原因 |
|---|---|---|
| `0048a` drm/msm/dsi: round the byte clock rate after reparenting | 跳过（脚本先反向核对确实已在） | Dmitry Baryshkov 的上游修复，7.2.15 稳定版已收录 |
| `0048` drm/msm/dsi: reparent byte/pixel src to XO on disable | 用 `refreshed/` 里的版本 | 上一条修复删掉了结构体里的 `byte_intf_clk_rate`，第一块的上下文变了；插入位置人工核对 |
| `1145` wifi: ath12k: optional cfg_static_window hif op | 用 `refreshed/` 里的版本 | 7.2.15 去掉了 `hif_ops.panic_handler`，上下文变了 |
| `0532` hwmon: pwm-fan: run the fan while charging in s2idle | 用 `refreshed/` 里的版本 | 7.2.15 改了 `pwm_fan_cleanup()` 的结尾，第 10 块（新函数，插在 `pwm_fan_probe()` 前）手工放到同一位置 |

刷新版保留原补丁头和作者，只改上下文。其余 298 个补丁原样严格应用。

## 离线核对（2026-11-11）

- 补丁序列改过的 414 个文件里，只有 22 个与内核 3 源码不同，抽查都是上游稳定版的修复（pwm-fan 定时器清理、ath12k 去掉 panic handler、
  input 清零、DPU flush 掩码等）；显示相关的 `dsi_host.c` 与内核 3 完全相同。
- 配置与内核 3 只差 7.2.15 新增的三个默认值（`ARM64_ERRATUM_3821522`、`ARM64_WORKAROUND_BROKEN_AMU_CONSTCNT`、`CC_OPT_INLINE_MEMSET`）。
- `sm8750-oneplus-pad2pro.dtb` 反编译后与内核 3 完全相同；模块清单相同（1770 个）；编译警告与内核 3 同类（第三方驱动缺函数原型）。
- `tests/package-install-test.sh` 通过（initramfs 66 个设备固件齐全）。

构建记录在主机 `out/m3k/`（源码树、`build.sh`、日志），包是 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-1.opd2413.aarch64.rpm`。

## M3 功能补丁（基线之上）

基线之后的功能改动按 [docs/M3-FEATURES.md](../../docs/M3-FEATURES.md) 的顺序逐项加，每项真机通过后才加下一项：

| 位置 | 内容 |
|---|---|
| `patches/series`、`patches/*.patch` | 功能补丁，`tools/kernel/apply-opd2413-features.sh <树> [最后一个编号]` 严格应用（`patch -F0`） |
| `config/*.config` | 配置片段，按文件名顺序追加到内核 3 的 `.config` 之后再 `olddefconfig`（后写的赋值覆盖前面的） |

| 版本 | 内容 |
|---|---|
| `7.2.15-1` | 基线（上面各节） |
| `7.2.15-2` | M3.1 蓝牙：`2001`（erhai `5fbc7cbd1`，hci_qca 断电时复位 IBS 状态）+ `m3-1-bluetooth.config`（RFCOMM TTY、BNEP） |
| `7.2.15-3` | M3.2a 电池与充电：`2101`（erhai v0.7.2 的 battmgr 整文件：电流符号、去掉 POWER_NOW、充电阈值改用属性 24、USB 外设供电、固定 9 V PD、充电通知不唤醒）。PPS 驱动（`CHARGER_ERHAI_PPS`、`CHARGER_SC8547A`）不编译 |
| `7.2.15-4` | M3.2b PPS：`2102`（wcd939x-usbss 的 D+/D- 切换）、`2103`（SC8547A 电荷泵和 erhai PPS 引擎）+ `m3-2b-pps.config` |
| `7.2.15-5` | M3.4b 摄像头：`2301`–`2346`（erhai 的相机系列 46 个提交）+ `m3-4b-camera.config` |
| `7.2.15-6` | M3.5 麦克风（候选）：`2401`（erhai 的 lpass-tx/va-macro，显式时钟管理 + TX HPF 控件） |
| `7.2.15-7` | 实验（不保留）：本机音频通路 14 个文件换成 erhai 版本，麦克风仍坏，排除内核音频驱动 |
| `7.2.15-8` | M3.6 `2403`（Esc 键报 `KEY_ESC`）；还带过 `2402`（恢复 SoC 的 TX SoundWire 端口描述），后来证明不需要、已从 series 去掉 |
| `7.2.15-9` | M3.5 候选：`2404`–`2406`（erhai 的 ADSP 消息修复：q6v5、GLINK、APR） |
| `7.2.15-10` | M3.5 麦克风根因修复 `2407`（wcd939x 按声道报告/切换 SoundWire 开关）；去掉 `2402`，TX SoundWire 布局回到 erhai 的 |
