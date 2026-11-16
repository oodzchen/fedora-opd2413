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
| `7.2.15-11` | M3.6 键盘休眠唤醒 `2408`、`2409`（共享 RX `gpio3` 休眠态 `input-enable + bias-pull-down` 与 `wakeup` 中断，4 簇脉冲过滤屏蔽 10 s 脉冲与 22.66 s 电池包拍频重合，仅真实按键唤醒） |
| `7.2.15-12` | M3.3 s2idle 修复 `2410`（erhai `b30d759d3`：`LLCC_ISLAND1` 使用 `res_ways = 0x7fffffff` 替代 `bonus_ways`，修 `2401` 引入后冷启动早休眠在 `PM: suspend-to-idle` 后触发 `PS_HOLD` 复位的问题） |
| `7.2.15-18` | 显示与夜览：`2411`（按共享 `hw_ctl` 延后一次 `phys_cleanup`，保持 `phys_0 -> phys_1` 停用顺序）、`2412`（预分配 DSPP 且不因 `ctm` 强制 `mode_changed`）、`2413`（恢复 `60/30 Hz`） |
| `7.2.15-22` | 显示 `2414`（`dpu_encoder_virt_atomic_disable()` 按 `new_state && new_state->active` 仅对在线 modeset 跳过 `INTF_MODE_VIDEO` 的 `trigger_flush`/`trigger_start`，解决 `-18` 手动 60 Hz 切换卡死与 `-20`/`-21` DPMS 超时互斥；技术债记为 `#36`/`#37`） |
| `7.2.15-23` | 开机灰闪 `2415`–`2417`（`ktz8866`/`led_bl` 同步真实关断 bootloader 遗留背光，`dispcc-sm8750` 延迟到 `led-backlight` 就绪并关断背光后再注册/停泊 `mdp_clk_src`；TECH-DEBT `#9`） |
| `7.2.15-24` | 5 GHz 调控域 `m3-wifi-reg.config`（启用 `CONFIG_EXPERT`、`CONFIG_CFG80211_CERTIFICATION_ONUS`、`CONFIG_ATH_REG_DYNAMIC_USER_REG_HINTS`，配合 `/etc/sysconfig/regdomain` `COUNTRY=CN` 支持动态用户调控域提示与非 DFS 5 GHz AP 信道） |
| `7.2.15-25` | 功耗与续航 Batch 1：`2418`–`2422`（erhai `62ed205f1..6f237b23c`，将 `adreno_gmu` 注册为独立驱动绑定到 `3d37000.gmu` 并解决 `fw_devlink` `sync_state` 依赖，TECH-DEBT `#34`）、`2423`（erhai `1055cf6dc`，GMU 接管带宽后释放内核 `set_initial_bw` 遗留的 DDR 最高频投票）、`2424`（erhai `39919af08`，修正 `a6xx_gmu_rpmh_dep_votes_init()` 传入 `gpu->pdev->dev` 以生成正确的 RPMH 依赖投票表） |
| `7.2.15-26` | 功耗与续航 Batch 2：`2425`（erhai `c5590c6a0`，允许非 x86 原生热插拔根端口进 D3）、`2426`（erhai `81aafa28f`，保留活跃 PCIe 控制器/PHY 的唤醒路径）、`2427`（erhai `39636e8c3` + `f12f2ab7a`，给 `gcc_pcie_0_{phy_,}gdsc` 添 `GENPD_FLAG_ACTIVE_WAKEUP`）、`2428`（erhai `870167fad`，板级 DTS `&pcieport0` `wake-gpios` 改为 `GPIO_ACTIVE_LOW`）、`2429`（erhai `627372bef`，`dwc3-qcom` 休眠期延迟 VBUS role override 更新）、`2430`（erhai `a1576b156`，避免 `qmp-combo` probe 窗口误进 runtime suspend）+ `m3-3-power.config`（`CONFIG_HOTPLUG_PCI_PCIE=y`）；上机配合移除 `pcie_ports=compat` 与 `fw_devlink.sync_state=timeout` 并加 `mem_sleep_default=s2idle` |
| `7.2.15-27` | 功耗与续航 Batch 3（`TECH-DEBT #19` 面板熄屏/休眠真断电）：`2431`（erhai `5930568b2`，每次 `dsi_pll_enable_pll_bias()` 编程 `PLL_SYSTEM_MUXES`）、`2432`（erhai `8ebec9278`，传播 DSI 时钟父级/速率/使能失败并平衡 `pm_runtime` 引用）、`2433`（回退 `1411`，恢复 `novatek_nt36536_unprepare()` 关断 `vddio`/`lcd_vsp`/`lcd_vsn`） |
| `7.2.15-28` | 冷启动竞态修复：`2434`（`q6dsp-lpass-clocks.c` 将 `dev_set_drvdata(dev, cc)` 提前到 `devm_clk_hw_register()` / `devm_of_clk_add_hw_provider()` 之前，消除并发加载 `va_macro` 等驱动在窗口期调用 `clk_prepare_enable()` 触发 `cc->desc`〔`0x348`〕空指针 Oops 并永久死锁 `clk_prepare_lock` 的问题） |
| `7.2.15-29` | 后摄音圈对焦修复（`TECH-DEBT #42`）：`2435`（修正 `cn3927` `device_link_add` 中 `consumer`/`supplier` 方向为 `sc1300cs -> cn3927` 并在传感器已激活时附加 `DL_FLAG_RPM_ACTIVE`，补上 `0x08=0x6f` 解锁后 OEM `100 us` 稳定延时、`CN3927_PARK_STEP=64` 与 `cn3927_write()` I2C 重试，消除 `ac7b000.cci` 超时） |
