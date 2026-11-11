# 技术债

唯一的一份。每条写清：临时做法、位置、为什么需要、影响、去掉的条件。
还没做的功能不放这里，放 [STATUS.md](STATUS.md)。

| # | 临时做法 | 位置 | 为什么暂时需要 | 影响 | 去掉的条件 |
|---|---|---|---|---|---|
| 1 | 启动参数 `clk_ignore_unused pd_ignore_unused regulator_ignore_unused` | `/etc/kernel/cmdline` | 沿用 Armada 已验证的组合；没人逐个验证过去掉后哪些外设掉电 | 功耗偏高，掩盖设备树里缺失的资源声明；休眠达不到最深态 | M3 合入 erhai 的休眠系列后逐个去掉，每个冷启动验证 |
| 4 | 沿用 Armada 7.2.6 内核和它的整套补丁（含约 250 个其他掌机的补丁），从 armada 仓库忽略目录里的一棵已编译的树构建 | `kernel-opd2413`、`out/kernel-tree` | M1 只换发行版 | 内核落后于 Fedora，没有安全更新；配置不是 Fedora 的（只并入了 Fedora 的 netfilter 选项和 LSM 顺序，`kernel/opd2413/fedora-netfilter-lsm.config`） | M3 换到 Fedora 的内核基线（7.3.x） |
| 5 | 扬声器没有原厂保护算法，固定增益 350 / −2.5 dB | UCM、内核 `1408` | 原厂保护在 Android HAL 和 ADSP 调参里，未移植 | 大音量长时间播放有损坏扬声器的风险 | 调研 AW88261 自身保护配置或 ADSP 侧保护模块 |
| 6 | 分区名和 kShimC 菜单标题仍叫 "Armada"（"Armada" 项现在启动的是 Fedora） | GPT、`boot_b` 里的 kShimC 清单和 U-Boot 参数 | 改名要改 GPT 并重写 `boot_b` | 只是名字不符 | 下一次因为别的原因必须重写 `boot_b` 时一起改 |
| 7 | `ARMADA_BOOT`（sda17，1 GiB）闲置 | GPT | Fedora 的内核都放 ESP，不需要独立 `/boot` | 浪费 1 GiB | 决定用途（并入根需要改 GPT，或作 swap） |
| 8 | 休眠禁用 | logind / KDE 电源配置 | Armada 内核空闲挂起后挂死 | 合盖和空闲不省电 | M3 合入 erhai 的 s2idle 系列并真机通过 |
| 9 | 开机灰闪 | 内核显示交接（`1407`、`1409` 之后仍存在） | 根因未找到 | 开机时屏幕闪一下灰色 | 按 armada 计划文档 §19.44 的时序取证路线继续 |
| 11 | WCN7860 的 Wi-Fi 和蓝牙固件由 `opd2413-firmware` 提供，来自 armada 仓库（上游 ROCKNIX extra-firmware） | `packaging/opd2413-firmware/manifest.sha256` 的 `[generic]` 部分 | Fedora 45 的 `atheros-firmware` 只有 WCN7850 | 版本不随 Fedora 更新；板级数据和 regdb 不是本机专用的 | Fedora 收录后删除；板级数据换成本机 OTA 里的（erhai 的做法） |
| 12 | `kernel-opd2413` 声明 `Provides: kernel` 等并用 dnf 配置排除 Fedora 内核 | `kernel-opd2413.spec`、`50-opd2413-kernel.conf` | 内核不是用 Fedora 的 spec 构建的 | 依赖 Fedora 内核子包的软件（如 `kernel-devel`、akmods）装不了 | M3 改用 Fedora 的 `kernel.spec` 构建 |
| 13 | QEMU 启动链测试依赖 Armada 时期留下的 U-Boot 二进制，其源码检出（原在 `/tmp`）已不在 | `tests/qemu-esp-boot.sh` 的 `UBOOT_QEMU` | 复用现成产物最快 | 该二进制是 countdown 模式，不是平板上现在的 quiet / menu 模式；丢了就得重建 | 需要重写 `boot_b` 之前，按 armada 仓库的 `uboot/prepare.py` 重建源码并重新构建 |
| 14 | 安装时用固定镜像（`OPD_MIRROR`），装好的系统仍用 Fedora 默认的 metalink | `tools/install-rootfs.sh` | metalink 曾分到 35 KB/s 的镜像 | 日后 `dnf upgrade` 可能同样很慢 | 问用户是否把系统默认源换成国内镜像，或在 dnf 配置里开 `fastestmirror` |
| 16 | Wi-Fi 的"硬件" MAC 是 ath12k 生成的 `00:03:7f:…`，不是本机真实地址 | 内核 ath12k | 本机真实 MAC 在 persist / OTA 里，未导入 | 用 Fedora 默认的按 SSID 生成的稳定 MAC，地址每次开机不变；与 Android 下的 MAC 不同 | 按 erhai 的做法从本机数据导入真实 MAC（蓝牙地址同理） |
| 19 | 熄屏时面板保持供电（只发关显示和进睡眠） | 内核 `kernel/opd2413/1411` | 完全断电后面板丢失 ABL 建立的某种状态，内核的初始化序列没有重建它，屏幕保持黑 | 熄屏时多耗面板睡眠电流和 KTZ8868 偏压的静态电流；系统挂起时同样 | 找到断电后缺的那一步（候选：`oplus,panel-reset-position = <2>` 的含义、触控固件下载与显示初始化的顺序），能从断电状态点亮后改回真正断电 |
| 20 | 只提供 120 Hz | 内核 `kernel/opd2413/1412` | 60/30 Hz（只加长垂直前肩）出不了画面；切回 120 Hz 后 DPU 的 CTL 卡住、SSPP 停止取帧，要完整关闭一次才恢复 | 没有省电的低刷新率，也没有可变刷新率 | 弄清厂商切换刷新率的面板命令和 DPU 侧的正确切换流程，真机通过后恢复这两个模式 |
| 22 | 回退内核 `7.2.6-2.opd2413` 没有 SELinux | 平板上的 `kernel-opd2413-7.2.6-2.opd2413` | 它是内核 3 之前唯一真机通过的正式内核 | 用它启动时 SELinux 关闭，期间新建的文件没有标签，回到内核 3 后可能出现拒绝 | 下一个正式内核（4）真机通过后，`installonly_limit=2` 自动卸掉 2；用过 2 之后执行 `fixfiles onboot` 再重启（全盘重新标记约 23 s） |
