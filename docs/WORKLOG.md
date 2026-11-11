# 工作日志

按日期记结论的变化。原始证据放 `private/`，这里只写路径。

## 2026-11-10

### 立项

用户决定从 Armada（bootc / ostree）改为标准可变的 Fedora 45 + KDE Plasma，取代现有 Armada；
内核分两步走；手写笔不做。决定记录在 [AGENTS.md](../AGENTS.md)。

### 评估结论

- **不是重新移植**。启动链与发行版无关；Armada 分支的内核（7.2.6 + `1400`–`1409`）已在本机验证
  显示、触控、Pogo 键盘、Wi-Fi、GPU、扬声器。
- **erhai v0.6（7.2.14）补上 Armada 缺的部分**：休眠、充电、摄像头、传感器、合盖、硬解。
  文件级对比（erhai 浅克隆的最近 58 个提交）显示 Armada 序列没有 `sc8547a`、`sc820cs`、`sc1300cs`
  驱动，尽管 DTS 里有对应节点。合入前需要逐提交核对，这个对比只是线索。
- **Fedora 45 的内核是 7.2.15**（此条有误，当天已更正，见下文"Fedora 45 的内核是 7.3.3"），与两边同代，合并成本低。Mesa 是 26.2.6，不低于 Armada 用的 26.2.5，
  但 Armada 的 Mesa 带补丁，原版能否驱动 Adreno 830 未验证。
- ColorOS 的内核模块和 HAL 不能直接用，能提取的是固件、校准、配置和设备树。见 ARCHITECTURE.md §6。

### M1.1 只读取证

- ESP（sda16）整分区读到 `private/esp-20261110/esp-sda16.img`，536870912 字节，
  设备侧与主机侧 SHA-256 一致（`bb173be6…`）。同时是 `KSHIM.CHO` 所在分区的完整备份。
- ESP 内容：`/EFI`、`/dtbs/qcom/`（31 个 DTB）、`/loader`、`/ostree`（三套部署，每套
  `vmlinuz-7.2.6` 64.3 MB + `initramfs-7.2.6.img` 84.4 MB）、`KSHIM.CHO`（16 KiB）。
  `loader.conf`：`timeout 3`、`default armada-*`。
- 现用内核命令行（`grey1` 条目）里与硬件相关的参数：
  `fw_devlink.strict=1 pcie_ports=compat swiotlb=8192 allow_mismatched_32bit_el0
  clk_ignore_unused pd_ignore_unused regulator_ignore_unused selinux=0`。
  根为 btrfs 子卷 `root`，挂载选项 `noatime,compress=zstd:1,discard=async`。
- **Armada 的根子卷已经叫 `root`**，所以 Fedora 的子卷在并存期间要用别的名字。
- **U-Boot 的约定**（读 armada 仓库 `porting/oneplus-pad-2-pro/uboot/build.py`）：按 PARTLABEL
  `ARMADA` 找 ESP，固定加载 `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb` 和 `/EFI/BOOT/BOOTAA64.EFI`。
  结论：换 Fedora 不需要重写 `boot_b`。
- **M1 用的内核产物**：armada 仓库 `output/opd2413-stage4/kern2/out/armada-kernel-7.2.6.tar.zst`
  （SHA-256 `7c6d84fa…`，即 fast2 / fast3 / firmware1 镜像用的那一套，对应已提交的补丁序列）。
  设备当前运行的 `grey1` 多了一个失败的实验补丁 `1410`，不采用。
  该内核 `SECURITY_SELINUX=y`、`BTRFS_FS=m`、`DEBUG_INFO_BTF=y`、无 `EFI_ZBOOT`，版本串 `7.2.6`。
- 固件输入：Armada 的清单 `oneplus-pad-2-pro.sha256` 共 62 个文件，本地文件在 armada 仓库的忽略目录里，逐文件校验通过。

### 设计决定

- Fedora 装进现有 btrfs 的新子卷，不重新 mkfs。理由：不能在运行中的 Armada 里格式化它自己的根；
  这样在 Fedora 首次启动成功前原系统始终可用；结果与重新格式化等价。
- 首次启动不改 systemd-boot 默认项，经 kShimC 的 "Armada boot menu" 手选 Fedora。
  默认启动路径在验收前保持不变。
- M1 用 `enforcing=0` 而不是 `selinux=0`，让文件标签从第一天就正确；enforcing 留到 M2。

### M1.2–M1.4 软件包与离线验证

构建产物在 `out/rpms/`（忽略目录），由 `tools/build-*.sh` 和 `tools/collect-rpms.sh` 生成：

| 包 | 版本 | 说明 |
|---|---|---|
| `kernel-opd2413` | 7.2.6-1 | `kern2` 产物原样打包；解包后与源 tarball 逐文件一致（2136 个文件） |
| `opd2413-firmware` | 16.0.10.600-1 | 71 个文件，构建时逐个校验 SHA-256 |
| `opd2413-device` | 0.1-2 | ufs-guard、dracut 模块、kernel-install 设置与两个插件、dnf 排除规则、禁用休眠 |
| `opd2413-audio` | 0.1-2 | UCM 与拓扑，与 armada 仓库的文件相同 |

**`tests/package-install-test.sh` 通过**（Fedora 45 aarch64 容器，systemd 262.1、dracut 111；
证据 `out/pkg-test/`）：

- `kernel-install` 生成 `/fedora/7.2.6/{linux,initrd,sm8750-oneplus-pad2pro.dtb}` 和条目
  `fedora-7.2.6.conf`，条目含 `linux`、`initrd`、`devicetree` 三行，路径相对 ESP 根。
- 固定路径的 DTB 已同步，与条目里的 DTB 相同。
- initramfs 93 MB（非 hostonly），66 个设备固件全部在内。
- dnf 查不到 Fedora 的 `kernel`、`kernel-core`。
- 反例：故意让 dracut 不带设备固件时，`60-opd2413-initrd-check.install` 让 `kernel-install` 失败。

**`tests/qemu-esp-boot.sh` 通过**（证据 `out/qemu-test/`）：Armada 时期构建的 QEMU 版 U-Boot
（RAM 盘后端，`--esp-ufs ARMADA`）读取"真实 ESP 副本 + 上面测试产出的 Fedora 文件"，
ESP 上现有的 systemd-boot 259 列出 Fedora 条目并启动其内核，U-Boot 的 ExitBootServices 钩子触发。
测试镜像里移除两套回滚部署后，加入 Fedora 文件还剩 220 MB。
这只证明到内核 EFI stub 退出启动服务为止；内核在真机上的行为由 1.7 验证。

测试过程中发现并修复的问题：

- `/usr/lib/kernel/install.conf` 属于 `systemd-udev`，我们的设置改放 `install.conf.d/` drop-in。
- 容器里 `/boot/efi` 不是挂载点时，`kernel-install` 写出的条目路径会带 `/boot/efi` 前缀。
  这是测试环境的假象（真机上 ESP 是挂载点），测试已改为挂载点。
- dracut 模块里的局部变量 `manifest` 与 dracut 自己的只读变量同名，导致固件一个都没装进去，
  而 **dracut 在模块失败后照样产出镜像**。改名之外，新增 kernel-install 插件做硬检查。
- 最小系统没有 `cmp`，给 `opd2413-device` 加了 `diffutils` 依赖。
- Fedora 45 仓库核对：`qcom-firmware` 有 Adreno 830 微码；WCN7860 的 Wi-Fi 和蓝牙固件没有。
- 主机没有 `createrepo_c`，暂时直接用 `dnf install ./*.rpm`，不建仓库。

### 下一步的准备

1.5–1.8 的路线和判据写在 [M1-INSTALL.md](M1-INSTALL.md)。已识别的一个注意点：Armada 每次开关机会把
`/boot/ostree` 重新镜像到 ESP，所以腾 ESP 空间要通过 Armada 自己的机制移除回滚部署，不能只删 ESP 上的文件。

### M1.5a 安装前提核对（只读）

平板启动到 Armada `20261104.92448d0.grey1` 后经 SSH 核对，结果表在 [M1-INSTALL.md](M1-INSTALL.md) 的"1.5a"一节。
影响方案的几点：

- btrfs 顶层已有 `root`、`var`、`home`，Fedora 的子卷定名 `fedora`、`fedora-home`。
- Armada 里有 `podman` 和 `dnf5` 且能直连镜像站，所以在平板上原生安装，不在主机上模拟构建。
- ostree 有三套部署，其中一套被 pin。腾 ESP 空间的做法定为：unpin 后 `ostree admin undeploy`
  两套旧部署，再跑 `armada-boot-update` 让它自己清理 ESP。
- `armada-bootimg-sync.service` 在开机和关机时都会同步 ESP，1.6 之后要重启一次 Armada 验证它不影响 Fedora 的文件。

### Fedora 45 的内核是 7.3.3，不是 7.2.15

解析 KDE 环境组时看到 `kernel-tools-7.3.3-300.fc45`。立项评估时写的"Fedora 45 是 7.2.15"来自主机上
尚未更新的内核，是错的。对 M1 没有影响（M1 用自带的 7.2.6）；对 M3 的影响是补丁要前移到 7.3，
工作量估计要上调，已更新 ARCHITECTURE.md §5 和 STATUS.md。

### 用户的决定与安装脚本

- 账户与区域：登录名 `colin`、显示名 `Colin`、英文、`Asia/Singapore`。中文字体仍安装
  （`google-noto-sans-cjk-vf-fonts`），否则中文内容显示为方块；这一项是我的判断，用户没有明确要求。
- 新增 `tools/install-rootfs.sh`（1.5b）和 `tools/install-kernel.sh`（1.6b），都在平板上运行。
  两个脚本只做过语法检查，**没有在平板上运行过**；`dnf --installroot` 加 KDE 环境组的事务在主机的
  aarch64 容器里解析通过（2204 个包），实际安装没有预演。
- 离线确认：ESP 上现有的 `sm8750-oneplus-pad2pro.dtb` 与 `kernel-opd2413` 里的 DTB 逐字节相同。
- 用户对"是否批准 1.5b 和 1.6 的写入"的答复是先不写、先把文档写清楚。写入批准仍然待定。

### M1.5b 开始（真机写入）

用户批准开始 1.5b，并同意 1.5b 判据通过后直接继续 1.6（任何一步不符合预期就停）。
软件包和脚本已拷到平板 `/var/tmp/opd2413/`，`SHA256SUMS` 在平板上校验通过。
`install-rootfs.sh` 以 `nohup` 在平板上运行，日志 `/var/tmp/opd2413/install-rootfs.log`；
子卷 `fedora`、`fedora-home` 已创建。

### 镜像问题与两次撤销

- 第一次运行：metalink 给主仓库分到约 35 KB/s 的镜像，停在加载元数据。此时还没装任何包，
  停掉容器后按手册撤销（卸载、删除两个空子卷）。Wi-Fi 本身没问题，平板上实测：
  南京大学约 21 MB/s、吉林大学约 17 MB/s、阿里云约 10 MB/s、中科大约 0.3 MB/s、清华 403。
- 给 `install-rootfs.sh` 加了 `OPD_MIRROR`：在容器里把 `/usr/share/dnf5/repos.d/fedora{,-updates}.repo`
  的 metalink 换成固定 baseurl（Fedora 45 的仓库定义在这里，不在 `/etc/yum.repos.d`）。
- 第二次运行（南京大学）：`updates` 的 repomd 引用了 11 个返回 404 的文件（镜像正在同步），dnf 报
  "all mirrors were already tried"。又撤销一次。这次运行是在用户中断那条命令的过程中启动的，事后核实才知道。
- 核对方法：取 `repodata/repomd.xml`，对其中每个 `href` 发 HEAD，全部 200 才算完整。
  吉林大学和阿里云的 `releases/45` 与 `updates/45` 都完整、revision 相同，选吉林大学。
- 第三次运行（吉林大学）：开始下载 2197 个包，速度正常。
- 两次撤销后 btrfs 只剩 Armada 原有的 `root`、`var`、`home`、`steamapps`。

### M1.5b 完成

第三次运行（吉林大学镜像）成功：2198 个包，子卷 `fedora` 约 7 GB。判据全部通过：有 `plasma-desktop`、
没有 `kernel-core`；fstab 与 `/etc/kernel/cmdline` 的 UUID 与 `blkid` 一致；`display-manager.service` →
`plasmalogin.service`；用户 `colin`（wheel）密码已设；子卷只多了 `fedora`、`fedora-home`
（以及 systemd 在其中自建的 `fedora/var/lib/portables`）。

补充处理：`plasma-setup.service`（首次运行向导）只看 `/etc/plasma-setup-done` 是否存在，已创建该文件并加进脚本。
Armada 也没有 `rmtfs`、`qrtr-ns`、`pd-mapper`、`tqftpserv` 服务（由内核提供），Fedora 里 `rmtfs` 保持禁用。
日志里的 "error while processing parameters" 来自 chroot 里的 `audit-rules` 脚本，无害。

### M1.6 完成

- 1.6a：unpin 并 `ostree admin undeploy` 索引 2、1，再跑 `armada-boot-update`。ESP 只剩 `grey1` 一套，
  可用 69 MB → 361 MB；`KSHIM.CHO`、systemd-boot、`loader.conf`、DTB 哈希不变。
- 1.6b 第一次失败：KDE 环境组带了 `dracut-config-rescue`，它的 kernel-install 插件
  `51-dracut-rescue.install` 先写了 280 MB 的 `fedora/0-rescue/`，随后因路径错误退出，主条目没写成。
  离线测试的干净容器里没有这个包，所以没测出来。处理：`opd2413-device` 0.1-3 用
  `/etc/kernel/install.d/51-dracut-rescue.install → /dev/null` 屏蔽它；离线测试改为同时安装
  `dracut-config-rescue` 并断言 ESP 上没有 rescue 镜像（通过）；`install-kernel.sh` 支持在包已安装时重试，
  也支持 `OPD_MIRROR`。删掉 ESP 上残留的 `fedora/` 后重跑。
- 1.6b 第二次成功：条目 `fedora-7.2.6.conf`（`linux`、`initrd`、`devicetree` 三行，`options` 与
  `/etc/kernel/cmdline` 完全一致）；initramfs 216 MB，含全部设备固件；ESP 其余文件哈希不变；剩 94 MB。
  initramfs 比容器测试大很多，原因见技术债 #10。
- 1.6c：经 SSH 重启，kShimC 按记忆约 30 秒后自动进入 Armada，约 65 秒 SSH 可连；`running`、失败单元 0；
  关机和开机时的 `armada-boot-update` 都没有动 Fedora 的文件。

### M1.7 首次启动 Fedora（真机启动）

用户经 "Armada boot menu" → systemd-boot 选 Fedora 进入系统。SELinux 是 Disabled，所以没有发生重新标记
和自动重启（见下）。证据在 `private/m1-firstboot/`（基本状态、完整 journal 和 dmesg、错误汇总、GPU）。

机器检查：

| 项 | 结果 |
|---|---|
| 内核、根 | `7.2.6 #30`（kern2 产物），根为子卷 `fedora`，`/boot/efi` 为 ESP |
| 系统状态 | `running`，失败单元 0 |
| GPU | KWin：OpenGL ES 3.2 Mesa 26.2.6，`Adreno (TM) 830`（freedreno）；Vulkan：turnip |
| 输入设备 | `NVTCapacitiveTouchScreen`、`OnePlus Pad 2 Pro Keyboard`、`… Keyboard Touchpad`、电源键、音量键 |
| 触控固件 | `nt36536-xn242.bin` 下载成功 |
| 音频 | 声卡 `OnePlus-Pad-2-Pro`；PipeWire 有 "Built-in Audio Speakers" 和 "Internal microphones" |
| Wi-Fi、蓝牙 | Wi-Fi 已连接（IP 与 Armada 时不同）；蓝牙控制器 Powered |
| 背光 | `/sys/class/backlight/backlight` 1433/2047 |
| UFS 保护 | `userdata`、LUN1 等只读；`ARMADA`、`ARMADA_BOOT`、`ARMADA_ROOT` 可写 |

启动日志里的报错（用户注意到的）：本次 205 行 err 级别。以只读挂载 Armada 的 `var` 子卷、读它最近一次启动
（同一 7.2.6 内核）的 journal 作基线，那次有 172 行。逐类对比：

- **Armada 下同样存在**：iris 视频固件缺失、`DSI PLL(0) lock failed`（双 DSI 启动时的已知现象，显示正常）、
  `qcom_battmgr unknown notification`、`qcom-apm CMD timeout`（技术债里的开机 APM 超时）、
  蓝牙 `Frame reassembly failed`、powerdevil 的 ddcutil 无权访问 `/dev/i2c-*`（为外接显示器探测 DDC，无害）、
  nt36536 驱动把普通信息打成 err 级别、simple-framebuffer 资源冲突（显示交接时的正常现象）。
- **Fedora 才有的**：
  - firewalld 的 nftables 规则失败 → firewalld inactive。原因：内核没有 `NFT_FIB_*`。登记技术债 #15。
  - `modprobe snd-seq` 的 install 命令报错：实际上 `snd_seq` 已加载，无害。
  - 触控板 "kernel bug: Touch jump detected"（libinput 警告），待用户确认触控板手感。
  - bfq 调度器写入失败（`Device or resource busy`）：无害。

两个新发现：

- **SELinux 没生效**：Armada 内核 `CONFIG_LSM="landlock,lockdown,yama,loadpin,safesetid,ipe,bpf"`
  不含 selinux，也没有 `SECURITY_SELINUX_BOOTPARAM`，所以命令行的 `enforcing=0` 不起作用。
  `/.autorelabel` 仍在，等启用 SELinux 后的第一次启动执行。改法是加 `lsm=` 参数，属于 M2。
- **IP 变了**：Fedora 45 自带 `22-wifi-mac-addr.conf`，按 SSID 生成稳定的 MAC；Armada 曾覆盖为硬件 MAC。
  硬件 MAC 本身也是 ath12k 生成的（`Generated MAC_ADDR: 00:03:7f:…`）。保留 Fedora 默认，地址每次开机不变。

### 运行中切刷新率后黑屏（真机失败）

用户在显示设置里把 120 Hz 改成 60 Hz 后黑屏。KDE 15 秒后自动撤销到 120 Hz，屏幕仍黑。

- dmesg：363 s 和 378 s 各有一次 `panel_unpreparing` → `panel prepared`（切 60 Hz、自动撤销），
  两次都没有 DSI/DPU 报错；之后 DRM 状态、KScreen 和 KWin 保存的配置都是 3392x2400@120。
- 背光：`led-backlight` 下两路 KTZ8868（`white:backlight-1/2`）都是 1433/2047。把亮度写成 1200 再写回
  1433，屏幕仍黑，所以不是"背光寄存器丢失"那么简单（假设被否定，适用于这一次现象）。
- 用户按电源键后误触发重启，重新进入后显示正常、仍是 120 Hz。
- 这不是 Fedora 引入的：Armada 计划文档第 1007 行（第十一轮）记录了完全相同的现象，"面板命令均发出、
  无 DPU 报错"，之后没有修。erhai 的 `erhai-display-power` 用 LD_PRELOAD 把 GNOME 的熄屏改成只关背光，
  就是在绕开这条路径。
- 影响：KDE 的自动熄屏和锁屏后熄屏都会让 DRM 关闭再打开显示，大概率触发同样的黑屏。临时规避：
  关掉 `colin` 的"空闲时关闭屏幕"（技术债 #17）。
- 正常状态基线：两路 `dsi_isr` 中断各 122 次（与 Armada 开机黑屏排查时的正常值一致），
  `msm`（DPU）中断持续增长。下次复现时先对比这两个数，判断哪一路 DSI 停了，再决定下一个实验。

### M1 验收清单通过；initramfs 改为 hostonly

- 用户确认：触屏、键盘打字、触控板、声音（播放、音量、静音）、亮度滑块都正常。加上机器检查
  （GPU 硬件渲染、Wi-Fi、Android 分区只读、失败单元 0），M1 验收清单全部通过。
- `opd2413-device` 0.1-4：去掉 `hostonly="no"`，用 Fedora 默认的 hostonly。平板上 `kernel-install add`
  重新生成：initramfs 216 MB → 63 MB，`opd2413-initrd-check` 报 66 个固件齐全，含 `btrfs.ko`；
  ESP 可用 94 MB → 239 MB。离线测试改为在容器里显式用非 hostonly（容器不是平板）。技术债 #10 已还。
- `KSHIM.CHO` 的哈希与 1.6 时不同：用户这次在 kShimC 选了 "Armada boot menu"，kShimC 改写了记忆页。
  这是设计行为，不是我们的写入；以后核对 ESP 时不要把它当作"不应变化"的文件。
- 用户决定：Armada 的数据全部删除（AGENTS.md）。

### 冷启动回归通过；1.8 第 1 步

- 换 hostonly initramfs 后，用户两次 `poweroff` 后开机，均选 Fedora 正常进入，触屏、键盘、声音正常；
  两次启动 `running`、失败单元 0，err 行数与首次启动相同。
- **关机后会自动重新开机**：两次关机日志都正常走到 `systemd-shutdown` 同步文件系统，之后平板自己重启进
  kShimC 菜单。当时接着充电（`qcom-battmgr-usb` online）。推测是插着电时固件把关机处理成重新开机，
  待拔线后复测；不影响使用。
- 1.8 第 1 步：`/boot/efi/loader/loader.conf` 的 `default armada-*` 改为 `default fedora-*`
  （原文件备份 `/var/tmp/opd2413/loader.conf.armada`，在 Fedora 的根里）。`bootctl list` 显示 Fedora
  为 default。待用户经 kShimC "Armada"（quiet 模式）冷启动验证。

### 1.8 第 1 步通过；第 2 步换 systemd-boot 262

- 第 1 步验证：用户在 kShimC 选 "Armada"（U-Boot quiet 模式），直接进入 Fedora。`bootctl status`：
  当前条目 `fedora-7.2.6.conf`，loader 为 systemd-boot 259.10（Armada 带来的）。
  `systemd-analyze`：firmware 13.3 s + loader 1.46 s + kernel 0.64 s + initrd 1.59 s + userspace 7.56 s。
- 第 2 步离线：`tests/qemu-esp-boot.sh` 增加 `SD_BOOT`，只把 loader 换成平板上 Fedora 的
  systemd-boot 262.1（`69410a95…`），其余与之前通过的测试相同。结果通过（证据 `out/qemu-sdboot262/`）。
  第一次运行退出码 141 是新加的版本打印行在 `pipefail` 下的 SIGPIPE，判据本身当时已满足；修好后重跑通过。
- 第 2 步真机：备份旧 loader 到 Fedora 的 `/var/tmp/opd2413/esp-before-sdboot/`，执行
  `bootctl --esp-path=/boot/efi --no-variables update`。ESP 前后哈希对比，变化只有：两份 loader
  `621d1cc4…`（259）→ `69410a95…`（262）；新增 `EFI/systemd/systemd-boot-fallbackaa64.efi`（旧 259）
  和 `loader/entries.srel`。待冷启动验证。

### 1.8 完成：Fedora 取代 Armada（M1 完成）

每一小步之后都由我经 SSH 执行 `systemctl poweroff`，平板自动重启（插着电），kShimC 按记忆约 30 秒后
进入 "Armada" 项，即 Fedora；每次都 `running`、失败单元 0。

| 步 | 做了什么 | 结果 |
|---|---|---|
| 1 | `loader.conf` 默认项 `armada-*` → `fedora-*` | kShimC "Armada"（quiet）直接进 Fedora |
| 2 | `bootctl update` 换 systemd-boot 262 | `bootctl status`：Product systemd-boot 262.1-1.fc45 |
| 3 | 删 ESP 上的 `armada-ostree-1.conf`、`/ostree`、`dtbloaderaa64.efi`、其他 28 款机型的 DTB | ESP 剩 12 个文件，可用 390 MB；保留文件哈希不变 |
| 4 | 删 btrfs 子卷 `home/armada/.local/share/Steam/steamapps`、`home`、`var`、`root` | 只剩 `fedora`、`fedora-home`（及其内的 `fedora/var/lib/portables`）；已用 93 GB → 5.9 GB |

ESP 最终内容：`/EFI/BOOT/BOOTAA64.EFI`、`/EFI/systemd/systemd-bootaa64.efi`（262）、
`/EFI/systemd/systemd-boot-fallbackaa64.efi`（259，bootctl 保留）、`/dtbs/qcom/sm8750-oneplus-pad2pro.dtb`、
`/fedora/7.2.6/{linux,initrd,sm8750-oneplus-pad2pro.dtb}`、`/loader/{loader.conf,entries.srel,random-seed}`、
`/loader/entries/fedora-7.2.6.conf`、`/KSHIM.CHO`。

开机时间（kShimC 自动选择）：firmware 41 s（含 kShimC 30 s 倒计时）+ loader 1.5 s + kernel 0.6–0.9 s +
initrd 1.6 s + userspace 8 s。

## 2026-11-11

### 自动登录

用户要求免密码自动登录。`/etc/plasmalogin.conf.d/50-autologin.conf`（`[Autologin] User=colin Session=plasma.desktop`），
并关掉 `colin` 的自动锁屏（`kscreenlockerrc`：`Autolock=false`、`LockOnResume=false`）。重启后直接进入 colin 的桌面会话。
这两处是手工配置，不在任何包里。

### 运行中黑屏的排查与修复

证据在 `private/display-repro{1,2,3}/`、`private/display60/`；抓取脚本 `private/display-snap.sh`、`private/display-repro.sh`，
寄存器对比工具 `tools/kms-snapshot-diff.py`。

1. **基线与复现**（原内核 7.2.6）：`kscreen-doctor --dpms off/on` 稳定复现。熄屏后再亮屏：两路 DSI 中断都从 124 增加到 246
   （又完整执行了 122 条初始化命令），面板复位和偏压 GPIO、vddio 与正负偏压稳压器、KTZ8868 两颗芯片的寄存器、背光值都与正常时
   逐项相同；DRM 调试日志里没有任何超时和错误，提交照常完成。
2. **线索**：Armada 计划文档第 1007 行记录过同样的现象；erhai 的提交 `8d8b1df`（"Full modeset recovery still leaves the panel dark"）
   最终改为只关背光，`b6a88bc` 记录过 DPU 的 CTL 卡住（我们的日志里没有超时，不是那一层）。
3. **假设一："开机时内核的初始化命令其实没生效，是 ABL 的状态撑着"——否定。** 诊断内核 `7.2.6-diag1`
   （`kernel/experiments/diag-0001`）在初始化后读回 DCS 0x0A：开机时主链路（dsi1）为 `0x9e`
   （升压开、退出睡眠、正常模式、显示开），DSI 错误 0；断电重开后同样是 `0x9e`、错误 0，但屏幕是黑的。
   从链路（dsi0）读回 `-61`，是绑定模式下只有主链路能读，正常。
4. **全模块寄存器对比**：`/sys/kernel/debug/dri/0/kms` 读出时会导出 DSI、PLL、CTL、DSPP、INTF、PINGPONG、SSPP、DSC 等全部
   寄存器。正常与断电重开后的黑屏两份快照：DSC 配置逐字相同，CTL 干净，SSPP 在取数；差异只有状态和计数寄存器、未用的
   DSPP 查找表 SRAM，以及 PLL 的 `FRAC_DIV_START_LOW` 差 1（开机时是 ABL 写的 0xe7，内核算的是 0xe6，频率差约百赫兹）。
   结论：主机侧硬件状态与正常时一致，问题在面板内部。
5. **假设二："面板断电后丢失了开机时由 ABL 建立、扛得过复位但扛不过断电的状态"——确认。** 诊断内核 `7.2.6-diag2`
   （`kernel/experiments/diag-0002`）在关闭面板时只发关显示和进睡眠，不断电；重新打开时照常复位并初始化。
   用户目视确认：单次、两次熄屏亮屏都恢复画面。缺的究竟是哪一步仍未知（厂商参数里的 `oplus,panel-reset-position = <2>`、
   触控固件和显示初始化的先后顺序都是候选）。
6. **60 Hz 是另一个问题**：逐步测试中，切到 60 Hz（只加长垂直前肩到 2684 行）立即黑屏；再切回 120 Hz 仍然黑；再做一次熄屏亮屏
   就恢复。切回 120 Hz 后的黑屏状态与熄屏亮屏后的正常状态对比：`ctl_0` 的 0x94 / 0x180 / 0x184 / 0x18c 有一组非零值，
   `sspp_8` 的取数计数停住，INTF 和 DSI 的行计数停在超过帧总行数的位置。说明模式切换路径会让 DPU 的 CTL 卡住、停止取帧，
   完整的关闭流程能把它复位。这几个偏移在上游驱动里没有定义，我没有可靠的资料解读，没有继续逆向。
   而断电重开的那次黑屏，`ctl_0` 是干净的，所以确实是两个不同的问题。
7. **修复**：`kernel/opd2413/1411`（熄屏时保持供电，亮屏时复位并初始化）和 `1412`（只报告 120 Hz）。内核
   `7.2.6-2.opd2413`（`kernel-opd2413-7.2.6-2.opd2413`），与 kern2 同源，只多这两个补丁。真机：显示模式只剩 120 Hz；
   用户目视确认三次熄屏亮屏都恢复画面；失败单元 0。之后撤掉 KDE 的"空闲不熄屏"规避，恢复默认。

### 安装内核时的两个坑

- **dnf 默认 `installonly_limit=3`**：装第四个内核时它自动卸载了最旧的、已验证过的 `7.2.6`。
- **卸载内核会误删别的条目**：systemd 的 `90-loaderentry.install` 卸载时执行
  `rm -f fedora-<kver>.conf fedora-<kver>*.conf`。卸载 `7.2.6` 时把 `7.2.6-diag1`、`7.2.6-diag2` 的条目也删了，
  ESP 上一度只剩一个从未启动过的 opd1 条目。重启前用 `kernel-install add 7.2.6-diag2 …` 重建了已知能启动的条目。
- 处理：内核版本号改用 `7.2.6-<N>.opd2413`（不会互为前缀），RPM 的 Version/Release 取自它；`opd2413-device` 0.1-5
  设置 `installonly_limit=2`（ESP 刚好放两个）。

### 开机提示音毛刺（观察）

用户说自动登录后的开机提示音有毛刺。原内核、diag1、diag2 各次启动的音频内核消息完全相同（16 条），也没有 xrun 记录。
推测与自动登录有关：提示音在系统刚启动、PipeWire 和功放还在初始化时就播放了。未验证，待单独处理。

### SELinux 和防火墙（内核 3）

- **原因**：Armada 内核的 `CONFIG_LSM` 不含 selinux，SELinux 一直是 Disabled，`enforcing=0` 也无效；内核没有
  `NFT_FIB_IPV4/IPV6/INET`，firewalld 加载 public 区规则失败后退出。
- **改法**：配置片段 `kernel/opd2413/fedora-netfilter-lsm.config`，取自 Fedora 45 的 `config-7.2.15-300.fc45`：
  所有 `NETFILTER_ / NF_ / NFT_ / IP_NF_ / IP6_NF_ / IP_SET / BRIDGE_NF_` 选项，加上 Fedora 的
  `CONFIG_LSM="lockdown,yama,integrity,selinux,bpf,landlock,ipe"` 和 `SECURITY_SELINUX_BOOTPARAM=y`。
  第一次用的正则太宽，把 NFS、NFC、NFP 也带进来了，从保存的合并前配置重做。`merge_config.sh` + `olddefconfig` 后只丢了两个
  OVS 选项。内核 `7.2.6-3.opd2413`，1770 个模块（含 `nft_fib_inet`）。
- **安装**：`/etc/selinux/config` 先改 permissive；卸掉 `7.2.6-diag2`，装内核 3，ESP 上剩内核 3（默认）和 2（回退），空闲 268 MB。
- **首次启动**：autorelabel 23 s 后自动重启；`running`、失败单元 0、AVC 0；firewalld `running`，public 区绑定 wlp1s0。
  KWin（freedreno）、声卡、Wi-Fi、触控固件、触屏和键盘的输入设备都在。
- **enforcing 试用**：运行中 `setenforce 1`，用户试了触控、键盘、声音和音量、亮度、浏览器、系统设置，都正常；
  `ausearch -m AVC,USER_AVC,SELINUX_ERR -ts boot` 无记录。
- **固化**：`/etc/selinux/config` 改 enforcing，`/etc/kernel/cmdline` 去掉 `enforcing=0`，对内核 3 和 2 各执行一次
  `kernel-install add`（ESP 上条目以外的文件哈希不变）。冷启动：内核 3，`getenforce` 为 Enforcing，启动参数里没有
  `enforcing=`，AVC 0，失败单元 0，firewalld 运行，自动登录进入桌面。
- **注意**：回退内核 2 没有 SELinux（技术债 #22）。

### 每条目 DTB 真机验证

- 问题：U-Boot 从 ESP 固定路径加载 DTB 交给 EFI；条目里也有 `devicetree` 行。三份 DTB 内容相同，只读手段分不出内核用的是哪份。
- 实验：主机上用 `fdtput` 在内核 3 的 DTB 的 `/chosen` 里加 `opd2413,dtb-source = "entry-dtbtest"`（dts 对比只差这一行），
  放到 ESP `/opd2413-dtbtest/`，新增条目 `opd2413-dtbtest.conf`（不用 `fedora-` 前缀，因为 `loader.conf` 的
  `default fedora-*` 会匹配它；`sort-key zz-dtbtest` 排最后）。`bootctl set-oneshot` 失败：U-Boot 不支持运行时写 EFI 变量
  （efivars 只读），由用户在 kShimC 选 "Armada boot menu" 后手选测试项。
- 结果：`LoaderEntrySelected` 为测试项；`/proc/device-tree/chosen/opd2413,dtb-source` 为 `entry-dtbtest`，`u-boot,version`、
  `linux,uefi-*` 也都在（U-Boot 的修补作用在了替换后的 DTB 上）；`running`，Enforcing。
- 清理：删掉测试条目和目录，ESP 文件集合与测试前相同。技术债 #3 关闭。

### 开机提示音毛刺（继续）

- 用户补充：只在刚启动进入桌面时偶尔出现。
- PipeWire 和 WirePlumber 的数据线程由 rtkit 设为 RR 20，主线程 nice −11；48 kHz、quantum 1024。
- 空闲时手动播放 `ocean/stereo/desktop-login.oga` 两次（第一次功放已空闲挂起，第二次紧接着）：用户听都正常。
  所以声音通路和功放冷启动本身没问题。
- 时间线：PipeWire 11.4 s 启动，plasmashell 13.95 s，pipewire-pulse 15.37 s 才被提示音按需拉起（套接字激活），
  正是 Plasma 大量服务同时启动的时候。这次开机所有节点 ERR 为 0（不知道这次有没有毛刺）。
- 处理：不为偶发现象反复重启。下次听到毛刺时不重启，当场取 `pw-top -b` 的 ERR 和该次开机的日志，再决定改哪里
  （候选：登录时就启动 pipewire-pulse、加大启动期的 quantum）。

### Wi-Fi 省电模式

- `iw` 显示 power_save on（NetworkManager 默认），HE 160 MHz、信号 −34 dBm、收发 2161 Mbit/s。
- 主机 ping：30 包间隔 0.5 s 丢包 0、6–22 ms；30 包间隔 0.05 s 4–18 ms。之前的 SSH 超时都发生在重启前后，与省电无关。
  保持默认，不改。

### 内核升级与回滚流程

把装内核 3 的实际过程写成 [KERNEL-UPDATE.md](KERNEL-UPDATE.md)：`installonly_limit=2` 下"先确认最新内核已通过再装下一个"、
`default fedora-*` 的含义、EFI 变量只读所以只能开机手选、kShimC 记住选项、改启动参数后对每个内核 `kernel-install add`、
回退内核没有 SELinux 时的重新标记。

### M3a 上机（7.3 内核起不来，排查中）

上机前离线检查都通过（编译、DTB 对比、容器安装测试、QEMU 启动链），见 M3-KERNEL.md。上机经过，按时间顺序：

| # | 启动项 | 内核 / 镜像 | 参数要点 | 屏幕上看到的 | 结果 |
|---|---|---|---|---|---|
| 1 | `fedora-7.3.3-1.opd2413.conf`（默认项） | 7.3.3-1，压缩 `vmlinuz.efi` | 默认（quiet） | 用户未看清 | 几秒内整机复位；没有日志 |
| 2 | `fedora-7.3.3-2.opd2413+1.conf` | 7.3.3-2，`vmlinuz.efi` | 默认 | 一行红字（systemd-boot 给启动项改名计数失败：`Failed to rename ... Access denied`，"ignoring"），随即复位 | 两次都复位（一次 kShimC 选 "Armada"，一次菜单手选） |
| 3 | `opd2413-m3debug.conf`（手工） | 7.3.3-2，未压缩 `Image` | 去掉 quiet，加 `earlycon=efifb keep_bootcon ignore_loglevel` | **没有红字，内核日志滚动**：8 个 CPU 起来、CPU 特性、Memory、pstore 在 `0xbfff00000`、到约 10 秒的 fw_devlink 依赖循环信息；顶部有一段 `efi_earlycon_remap` 里 memremap 的警告调用栈（earlycon 引起） | 然后黑屏，不复位；等 4 分钟以上 SSH/ping 都不通。照片 `~/Downloads/IMG_20261111_120551.jpg` |
| 4 | 同上 + `initcall_blacklist=msm_drm_register` | 同上 | 同上，不加载 msm 显示/GPU 驱动 | 灰屏 | 卡住，20 分钟内网络不通 |
| 5 | `fedora-7.3.3-3.opd2413+0.conf`（kernel-install 条目改名为 +0，非默认） | 7.3.3-3（SHM bridge），`Image` | 去掉 quiet，加 `ignore_loglevel` | 同样的红字，随即复位。照片 `IMG_20261111_130612.jpg` | 复位后自动进了默认的内核 3 |
| 6 | 同上 + `nokaslr` | 同上 | 同上 | 红字后立即复位 | 复位 |
| 7 | `opd2413-m3test.conf`（去掉计数后缀，非默认） | 7.3.3-3，`Image` | 同 5（无 nokaslr、无 earlycon） | **没有红字**，黑屏 | 然后复位 |

已经确定的事实：

- 复位后没有任何 7.3 的日志：journal 里没有 7.3 的开机记录（没走到挂载根分区、启动 journald）；pstore 为空。
- **ramoops 在这台机器上重启后不保留**：内核 3 下写入标记后 `systemctl reboot`，回到内核 3 pstore 仍为空。
  长按电源键的硬复位同样为空（RTC 也被重置）。以后不要再指望 pstore。
- **systemd-boot 的启动计数在这台机器上不能用**：U-Boot 的 EFI 文件接口拒绝改名（Access denied），条目名不会变，
  也就不会自动回退。上面的红字就是这条警告。
- 两份 DTB 的保留内存区（reserved-memory，排序后比较）完全一致；固件路径一致。
- 内核 3 的 `/sys/class/watchdog` 为空，没有看门狗设备在用。
- 内核 3 下 efifb 可用（3392x2400，帧缓冲在 0xfc800000）；earlycon 打字很慢（每行重绘整屏）。

我做过、但被后来的结果否定的判断（记下来，避免重复）：

- "看门狗驱动是模块所以复位"：内核 3 下根本没有看门狗设备。
- "压缩镜像 EFI_ZBOOT 导致复位"：依据是第 3 次（Image）能起来，但第 5、6、7 次 Image 同样复位。
- "物理地址 KASLR 落到受保护内存"：第 6 次加 `nokaslr` 仍复位（不过那次带着计数后缀，严格说不算独立的否证）。
- "红字（计数改名失败）无害" 和随后的 "红字是复位原因"：第 7 次没有红字照样复位，所以它不是（唯一）原因；
  但红字是否完全无害也没有被证明。

目前唯一越过复位的是第 3 次。它与第 7 次的区别只有两个：内核（7.3.3-2 vs 7.3.3-3，后者只多了 SHM bridge 配置）
和参数（第 3 次有 `earlycon=efifb keep_bootcon`）。下一个实验：第 7 次的条目加上这两个参数（只动参数）。
越过 → earlycon 相关（可能与早期时序或帧缓冲内存有关），并且能看到之后的日志；仍复位 → 嫌疑转到 SHM bridge。

第 3 次之后的黑屏卡死是另一个问题：黑屏发生在显示驱动接管时（之后的日志看不到），之后网络始终不通。
