# 技术债

唯一的一份。每条写清：临时做法、位置、为什么需要、影响、去掉的条件。
还没做的功能不放这里，放 [STATUS.md](STATUS.md)。

| # | 临时做法 | 位置 | 为什么暂时需要 | 影响 | 去掉的条件 |
|---|---|---|---|---|---|
| 1 | 启动参数 `clk_ignore_unused pd_ignore_unused regulator_ignore_unused` | `/etc/kernel/cmdline` | 沿用 Armada 已验证的组合；没人逐个验证过去掉后哪些外设掉电 | 功耗偏高，掩盖设备树里缺失的资源声明；休眠达不到最深态 | M3 合入 erhai 的休眠系列后逐个去掉，每个冷启动验证 |
| 2 | SELinux 非 enforcing（M1 用 `enforcing=0`） | `/etc/kernel/cmdline` | 先只换一个变量；设备服务还没有策略 | 不符合标准 Fedora 的安全默认 | M2：首启 relabel 干净、设备服务无 AVC 拒绝后改 enforcing |
| 3 | DTB 放在 ESP 固定路径，对所有内核全局生效 | ESP `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb`；U-Boot 在 `boot_b` 里写死这个路径 | U-Boot 现在这样加载；改它要重写 `boot_b` | 回滚到旧内核时 DTB 不跟着回滚，DTB 与内核可能不匹配 | 条目已自带 `devicetree` 行，QEMU 里这样的条目能启动内核（2026-11-10）；还要在真机确认内核拿到的是条目的 DTB 而不是 U-Boot 传入的那份，之后固定路径的副本只作兜底 |
| 4 | 沿用 Armada 7.2.6 内核和它的整套补丁（含约 250 个其他掌机的补丁） | `kernel-opd2413` | M1 只换发行版 | 内核落后于 Fedora，没有安全更新；配置不是 Fedora 的 | M3 换到 Fedora 的内核基线（7.3.x） |
| 5 | 扬声器没有原厂保护算法，固定增益 350 / −2.5 dB | UCM、内核 `1408` | 原厂保护在 Android HAL 和 ADSP 调参里，未移植 | 大音量长时间播放有损坏扬声器的风险 | 调研 AW88261 自身保护配置或 ADSP 侧保护模块 |
| 6 | 分区名和 kShimC 菜单标题仍叫 "Armada"（"Armada" 项现在启动的是 Fedora） | GPT、`boot_b` 里的 kShimC 清单和 U-Boot 参数 | 改名要改 GPT 并重写 `boot_b` | 只是名字不符 | 下一次因为别的原因必须重写 `boot_b` 时一起改 |
| 7 | `ARMADA_BOOT`（sda17，1 GiB）闲置 | GPT | Fedora 的内核都放 ESP，不需要独立 `/boot` | 浪费 1 GiB | 决定用途（并入根需要改 GPT，或作 swap） |
| 8 | 休眠禁用 | logind / KDE 电源配置 | Armada 内核空闲挂起后挂死 | 合盖和空闲不省电 | M3 合入 erhai 的 s2idle 系列并真机通过 |
| 9 | 开机灰闪 | 内核显示交接（`1407`、`1409` 之后仍存在） | 根因未找到 | 开机时屏幕闪一下灰色 | 按 armada 计划文档 §19.44 的时序取证路线继续 |
| 11 | WCN7860 的 Wi-Fi 和蓝牙固件由 `opd2413-firmware` 提供，来自 armada 仓库（上游 ROCKNIX extra-firmware） | `packaging/opd2413-firmware/manifest.sha256` 的 `[generic]` 部分 | Fedora 45 的 `atheros-firmware` 只有 WCN7850 | 版本不随 Fedora 更新；板级数据和 regdb 不是本机专用的 | Fedora 收录后删除；板级数据换成本机 OTA 里的（erhai 的做法） |
| 12 | `kernel-opd2413` 声明 `Provides: kernel` 等并用 dnf 配置排除 Fedora 内核 | `kernel-opd2413.spec`、`50-opd2413-kernel.conf` | 内核不是用 Fedora 的 spec 构建的 | 依赖 Fedora 内核子包的软件（如 `kernel-devel`、akmods）装不了 | M3 改用 Fedora 的 `kernel.spec` 构建 |
| 13 | QEMU 启动链测试依赖 Armada 时期留下的 U-Boot 二进制，其源码检出（原在 `/tmp`）已不在 | `tests/qemu-esp-boot.sh` 的 `UBOOT_QEMU` | 复用现成产物最快 | 该二进制是 countdown 模式，不是平板上现在的 quiet / menu 模式；丢了就得重建 | 需要重写 `boot_b` 之前，按 armada 仓库的 `uboot/prepare.py` 重建源码并重新构建 |
| 14 | 安装时用固定镜像（`OPD_MIRROR`），装好的系统仍用 Fedora 默认的 metalink | `tools/install-rootfs.sh` | metalink 曾分到 35 KB/s 的镜像 | 日后 `dnf upgrade` 可能同样很慢 | 问用户是否把系统默认源换成国内镜像，或在 dnf 配置里开 `fastestmirror` |
| 15 | firewalld 不工作（无防火墙） | 内核配置 | Armada 内核没有 `NFT_FIB_IPV4/IPV6/INET`，firewalld 加载规则失败后停止 | 平板在局域网里没有防火墙；sshd 只允许密钥登录 | M3 换用 Fedora 的内核配置后，确认 firewalld `active` |
| 16 | Wi-Fi 的"硬件" MAC 是 ath12k 生成的 `00:03:7f:…`，不是本机真实地址 | 内核 ath12k | 本机真实 MAC 在 persist / OTA 里，未导入 | 用 Fedora 默认的按 SSID 生成的稳定 MAC，地址每次开机不变；与 Android 下的 MAC 不同 | 按 erhai 的做法从本机数据导入真实 MAC（蓝牙地址同理） |
| 17 | KDE 的"空闲时关闭屏幕"在三个电源配置里都关掉 | 用户 `colin` 的 `~/.config/powerdevilrc`（手工设置，不在任何包里） | 运行中面板关闭再打开后黑屏、只能重启（见 STATUS"显示"一行）；自动熄屏会走这条路径 | 屏幕只会调暗、不会熄灭，费电；锁屏后也不熄屏 | 内核修好面板重新 prepare 后的黑屏，熄屏/亮屏真机通过后删掉这几行 |
| 18 | ESP 上没有设置只保留两个内核 | dnf 的 `installonly_limit` 是默认 3 | 还没做 | 三个内核约 384 MB，ESP 剩不了多少，第四个装不下 | M2 内核升级流程里设成 2，并在 `install-kernel` 前检查 ESP 剩余空间 |
