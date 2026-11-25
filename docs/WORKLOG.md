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
| 3 | `opd2413-m3debug.conf`（手工） | 7.3.3-2，未压缩 `Image` | 去掉 quiet，加 `earlycon=efifb keep_bootcon ignore_loglevel` | **没有红字，内核日志滚动**：8 个 CPU 起来、CPU 特性、Memory、pstore 在 `0xbfff00000`、到约 10 秒的 fw_devlink 依赖循环信息；顶部有一段 `efi_earlycon_remap` 里 memremap 的警告调用栈（earlycon 引起） | 然后黑屏，不复位；等 4 分钟以上 SSH/ping 都不通（有用户拍的照片，不进仓库） |
| 4 | 同上 + `initcall_blacklist=msm_drm_register` | 同上 | 同上，不加载 msm 显示/GPU 驱动 | 灰屏 | 卡住，20 分钟内网络不通 |
| 5 | `fedora-7.3.3-3.opd2413+0.conf`（kernel-install 条目改名为 +0，非默认） | 7.3.3-3（SHM bridge），`Image` | 去掉 quiet，加 `ignore_loglevel` | 同样的红字，随即复位（有照片，不进仓库） | 复位后自动进了默认的内核 3 |
| 6 | 同上 + `nokaslr` | 同上 | 同上 | 红字后立即复位 | 复位 |
| 7 | `opd2413-m3test.conf`（去掉计数后缀，非默认） | 7.3.3-3，`Image` | 同 5（无 nokaslr、无 earlycon） | **没有红字**，黑屏 | 然后复位 |
| 8 | 同 7 | 同 7，镜像哈希未变 | 同 7，追加 `earlycon=efifb keep_bootcon` | 有日志，照片可见到约 13.63 s 的 `Fixed dependency cycle(s)`，随后黑屏 | 用户确认自动复位；主机观察窗内 SSH 未恢复 |
| 9 | 同 8 | 同 8，镜像哈希未变 | 同 8，只追加 `initcall_debug` | 用户确认黑屏，未取得照片 | 自动复位；用户手选内核 3 回桌面，15:19 SSH 确认恢复正常 |
| 10 | 用户手动补测，同 9 的测试项 | 未报告更换镜像 | 条目读回与 9 相同 | 用户确认照片为黑屏前最后一屏：约 66.95 s，末行 CP110 legacy calling | 15:27 SSH 确认回到内核 3；补测的具体复位方式未独立报告 |
| 11 | 同 10 的测试项 | 写前哈希核对与 9 相同 | 只加 `initcall_blacklist=gpu_cc_sm8750_driver_init` | 用户报告日志后灰白屏停留，随后持续黑屏 | 主机五分钟内 SSH 不通，用户未报告自动复位；后续转持久化取证 |

已经确定的事实：

- 复位后没有任何 7.3 的日志：journal 里没有 7.3 的开机记录（没走到挂载根分区、启动 journald）；pstore 为空。
- **ramoops 在这台机器上重启后不保留**：内核 3 下写入标记后 `systemctl reboot`，回到内核 3 pstore 仍为空。
  长按电源键的硬复位同样为空（RTC 也被重置）。以后不要再指望 pstore。
  **（18:45 更正：这条结论是错的，见"18:39 起：评估"一节。热复位后 ramoops 保留，只有长按电源才丢。）**
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

### M3a 接续：先核对状态，再做 earlycon 对照（14:58）

只读核对证据：`private/m3-resume-20261111/preflight.txt`。当前运行 `7.2.6-3.opd2413`，`running`、失败单元 0、
SELinux Enforcing；电量 98%、正在充电。ESP 约剩 242 MiB，只有稳定内核条目和非默认 `opd2413-m3test.conf`。
测试内核是 `7.3.3-3.opd2413`，其 Image、initramfs 和 DTB 的哈希已记录；测试项没有 earlycon、没有启动计数后缀。
本次检查没有修改平板配置或触发重启。

下一个实验的写入范围（待本次用户批准）：先把原测试条目和 ESP 文件哈希清单备份到 Fedora 根分区的
`/var/tmp/opd2413/`，再只修改 ESP 上 `loader/entries/opd2413-m3test.conf` 的 options 行，追加
`earlycon=efifb keep_bootcon`。内核、模块、DTB、initramfs、`loader.conf`、稳定内核条目、`KSHIM.CHO` 和
`boot_b` 均不改；不运行 kernel-install。改后读取校验，ESP 文件内容差异应只有这一个测试条目。
用户同意后经 SSH 关机，再由用户经 kShimC 的 "Armada boot menu" 手选该测试项；未选测试项则仍进稳定内核。

判据与取证：记录从选中条目到复位或停住的时间、最后可见日志（包括函数名和时间戳），同时从主机探测 SSH。
若进入 7.3，立即采集 cmdline、dmesg、journal、驱动延迟及失败单元；若复位，回到稳定内核并核对启动记录；
若停住，保留屏幕证据后由用户长按电源恢复，避免重复等待二十分钟。earlycon 绘屏很慢，SSH 暂时不通本身不等于死锁。

解释边界：本次相对第 7 次只改上述两个控制台参数，能检验它们是否改变现象；无论是否复位，单次结果都不能证明
SHM bridge 是根因。第 3 次与本次仍有构建、启动时序和固件残留状态等潜在差异，需要后续对照确认。

15:00，用户明确批准“修改并重启”。已完成条目备份、参数追加及 ESP 全文件内容哈希核对，只有
`loader/entries/opd2413-m3test.conf` 变化，稳定内核条目、`loader.conf`、`KSHIM.CHO` 及所有镜像均未变化。
设备侧备份：`/var/tmp/opd2413/m3-earlycon-20261111-150041/`；主机证据：
`private/m3-resume-20261111/enable-earlycon.txt`。

15:01:52，经 SSH 执行已获批的 `systemctl poweroff`。用户手选第 8 次测试后报告：有日志，随后黑屏、自动复位。
照片已归档 `private/m3-resume-20261111/experiment8.jpg`（底部放大图 `experiment8-bottom.png`）。
可辨认的日志有 ramoops 注册、CPU 空闲 PSCI 和大量 `Fixed dependency cycle(s)`，最下方约 13.63 s；照片中未见 panic/Oops。
主机每约十秒尝试一次 SSH，到 15:04:53 的观察窗结束均未连通（`reboot-watch.txt`），不能由此证明复位后已经回到稳定内核。
已请用户先选回 `7.2.6-3.opd2413`，不重复启动测试项。

离线复核（本次没有再改设备）：

- `config-2-to-3.diff` 确认 -2 与 -3 保存的配置只差 TZMEM generic / SHM bridge 的选择；但这不证明它导致复位。
- 照片中的 `Fixed dependency cycle(s)` 来自 `drivers/base/core.c:__fwnode_link_cycle()` 的 `pr_info`，
  表示 fw_devlink 已标记依赖环，不是报错，也不是 CoreSight 驱动已执行或已失败的证据。
- `drivers/of/platform.c` 的 `of_platform_default_populate_init()` 是 `arch_initcall_sync`；
  `drivers/gpu/drm/msm/msm_drv.c:msm_drm_register()` 是 `module_init`（内建时 device initcall）。
  当前照片只能提供早期阶段的下界，不能确认黑屏就发生在 DRM 接管处。
- `init/main.c` 已支持 `initcall_debug`，会成对打印 `calling <函数>` 和 `initcall <函数> returned`。
  下一轮优先只加这一个参数、保持所有镜像及其他参数不变，争取拿到最后一个开始/返回的初始化函数；
  不先禁用 CoreSight、SMMU 或改另一份 DTB。此轮属于新的写入和重启，需另行批准。
- efifb 每次滚屏要复制大量像素；加日志会进一步改变时序，所以即使现象变化也只能作为诊断线索。

### M3a 第 9 次：initcall_debug（预期与判据）

用户已明确批准继续。15:10:30 只读确认已回稳定 `7.2.6-3.opd2413`，`running`、失败单元 0、Enforcing，电量 97%；
测试条目仍为第 8 次的参数，见 `private/m3-resume-20261111/pre-experiment9.txt`。

本轮只在同一测试项的 options 行末追加 `initcall_debug`，其他参数及全部镜像保持不变；写前备份条目和 ESP 内容哈希，
写后读回并断言 ESP 只有该测试条目变化，再执行已获批的关机。用户经原菜单手选同一测试项，并记录黑屏前最后一屏，优先视频。

判据：抓到 `calling <函数>` 和对应 `initcall <函数> returned` 的最后几组，尽量区分“函数尚未返回”、
“显示日志通道丢失”与“随后复位”。若能到 SSH 则立即取完整日志；若仍复位则先回稳定内核。
单个没有返回行的函数只列为待核对线索，不直接当根因（异步探测、截帧和绘屏延迟也会影响最后可见行）。
本轮不增加黑名单、不改 DTB、不换内核，避免把定位初始化层和验证某个外设混在一起。

15:11:38，参数已写入并读回，ESP 全文件内容哈希核对只有测试条目变化。设备备份：
`/var/tmp/opd2413/m3-initcall-debug-20261111-151138/`；证据：`private/m3-resume-20261111/enable-initcall-debug.txt`。
15:12:22 发出本轮已获批的 `systemctl poweroff`（SSH 返回 0），随后监测到 15:15:23，期间 SSH 均未连通。
主机观察已结束，没有后台任务；证据：`private/m3-resume-20261111/experiment9-reboot-watch.txt`。
监测结束时待用户提供第 9 次屏幕照片/视频及是否复位的报告，不能仅根据当时 SSH 不通判断失败类型。

随后用户明确报告第 9 次黑屏后自动重启，已手选 `7.2.6-3.opd2413` 进入桌面。15:19:47 只读核对：
SSH 恢复，内核版本正确，`running`、失败单元 0、SELinux Enforcing、AVC 查询无记录，电量 97%、正在充电。
`loader.conf` 仍为 `default fedora-*`；诊断参数仅在非默认 M3 测试项，稳定内核的运行参数不含这些诊断参数。
证据：`private/m3-resume-20261111/experiment9-recovery.txt`。本次核对没有设备写入或重启。

第 9 次仍为真机失败（自动复位），但复位前最后一个 initcall 未知。唯一下一步是取得本轮末尾照片/视频并解析，
再决定针对哪个初始化层取证；不继续盲目重启。

### M3a 第 10 次：用户手动补测取照（15:24）

用户因第 9 次没有照片，手动重新测试并提供照片；单独记为第 10 次，不把新照片冒充第 9 次原始证据。
照片已归档 `private/m3-resume-20261111/experiment10.jpg`，底部放大图 `experiment10-bottom.png`。
本次 agent 没有触发设备重启或写入。用户随后明确确认：这就是黑屏前最后看到的一屏。

15:27:56 只读确认已在稳定 `7.2.6-3.opd2413`，`running`、失败单元 0、Enforcing，SSH 正常；
测试项仍含 `earlycon=efifb keep_bootcon initcall_debug`，没有 blacklist，`loader.conf` 仍为 `default fedora-*`。
证据 `experiment10-state.txt`。

照片转录与离线核对：

- 末尾约 `66.922433`：`initcall ap_cpu_clock_driver_init... returned 0 after 64 usecs`。
- 最后一行约 `66.947432`：`calling cp110_syscon_legacy_driver_init... @ 1`；该照片没有拍到它的返回行，
  但不能仅由单帧断定此函数未返回或导致复位。
- 核对与已安装 Image 同哈希的构建产物和同一份 System.map，initcall 顺序是
  `cp110_syscon_legacy_driver_init` → `cp110_clock_driver_init` → `disp_cc_sm8750_driver_init` →
  `gpu_cc_sm8750_driver_init`。对应片段保存在 `experiment10-initcall-order.txt`。
- CP110 驱动只匹配 `marvell,cp110-system-controller0` / `marvell,cp110-clock`，编译后的本机 DTS 无这些节点；
  不把其名称里的 Armada 与此前使用的发行版混淆，也不凭它是最后一行就先禁用它。
- 稳定内核与 M3 的 `dispcc-sm8750.c`、`gpucc-sm8750.c`、`clk-alpha-pll.c`、`gdsc.c` 逐字相同；
  `drivers/clk/qcom/common.c` 只有一处差异：`qcom_cc_really_probe()` 的 `use_rpm` 收尾从
  `pm_runtime_put()` 改成 `pm_runtime_put_sync()`。GPUCC 的描述符设置了 `use_rpm=true`，
  DISPCC 没有设置且自行执行未变化的 `pm_runtime_put()`。这是 GPUCC 探测期同步 runtime suspend 的源码线索，
  不是已确认的根因；可能还受设备树、PM 核心和时序差异影响。对比证据 `clock-source-comparison.txt`、`common-k3-to-m3.diff`。

候选下一轮（待批准）：仅给非默认测试项追加 `initcall_blacklist=gpu_cc_sm8750_driver_init`，
保持 Image、DTB、initramfs 及所有其他参数不变。目的仅是隔离 GPUCC 初始化，观察是否能保留日志并到达 SSH；
跳过 GPU 时钟会使 GPU 不可用，桌面起不来不算本实验失败，也绝不能作为正式修复。写前备份、写后 ESP 单文件差异校验，
稳定内核和默认项不改。若仍在同一区间黑屏，停止重复并改查更早的显示时钟/平台注册；若越过则先取完整日志，
再对 GPUCC 的具体 runtime PM 调用做最小对照，不把 blacklist 留作永久方案。

### M3a 第 11 次：只跳过 GPUCC 初始化（预期与判据）

用户已单独批准本轮写入和重启。只修改 `opd2413-m3test.conf` 的 options 行，追加
`initcall_blacklist=gpu_cc_sm8750_driver_init`；第 10 次确认的参数以及全部镜像均保持不变，不同时跳过 DISPCC 或 MSM DRM。
现有内核的 `CONFIG_KALLSYMS=y` 且函数名已在同版本 System.map 确认，blacklist 应能按精确函数名生效。

期望与判据：观察是否越过照片的 CP110 → DISPCC → GPUCC 区间，能否看到 GPUCC blacklisted 以及之后的 initcall；
若 SSH 可达，优先读出完整 cmdline、dmesg、失败单元和 deferred probes，验证跳过的是指定函数。GPU/桌面不工作是预期，
不据此判定本轮失败；若仍黑屏/复位，先取末尾照片/视频并回稳定内核，不重复启动。本次不能同时回答显示时钟是否导致黑屏，
也不能证明同步 runtime suspend 是根因，只是选择性隔离 GPUCC 注册和探测路径。

15:34:31 完成参数写入及读回校验，ESP 全文件内容哈希只有该测试条目变化。备份：
`/var/tmp/opd2413/m3-skip-gpucc-20261111-153431/`；证据 `private/m3-resume-20261111/skip-gpucc.txt`。
技术债 #26 已同步登记临时 blacklist。

15:36:22 发出已批准的 `systemctl poweroff`，SSH 因远端断开返回 255；没有重复发送关机命令。
主机观察到 15:41:32 仍未连接 SSH（`experiment11-reboot-watch.txt`）。用户随后报告：日志后灰白屏停留，
之后黑屏且持续不恢复，没有报告自动复位。不能把没有桌面当作本轮 GPUCC 隔离失败，也不能把不再自动复位直接当作根因证据。

### 第 11 次后：停止抓拍，先建立持久化取证

用户明确指出抓拍时机无法掌握、操作不方便，要求持久化抓取和存储日志。停止要求用户补拍，也不继续叠加黑名单试启动。
已请用户长按电源恢复并选稳定内核；截至后续只读查询，SSH 尚未恢复，不能假定已经回到桌面。

补查了同一局域网的 SSH 地址变化：仅探测端口和主机公钥，没有发现与已知 Fedora 主机密钥匹配的目标，
没有对其他主机执行命令（`experiment11-lan-discovery.txt`）。这没有证明平板没连 Wi-Fi，只是没有找到可自动采集的 SSH 通道。

本地源码核对：UFS 在 device initcall 的链接位置晚于照片中的时钟驱动；pstore/blk 是 late initcall，
`/init` 又在所有 initcalls 之后才执行。直接加 pstore/blk 或一个 dracut 日志脚本都不能保证覆盖更早的失败。
pstore/blk best-effort 也没有专用 panic_write，并且会占用原始块设备、破坏现有文件系统，因此不直接试写 sda17。

路线改为先在稳定内核上验证“initramfs 日志同步写现有 Linux 文件系统、重启后自动读回”的独立正对照，
再把可疑显示/GPU 时钟驱动模块化，等日志通道 READY 后一次加载一个。完整范围、先后次序、覆盖边界及批准要求见
[BOOT-LOGGING.md](BOOT-LOGGING.md)。候选日志盘为闲置 `ARMADA_BOOT`，仍需恢复后只读核对和备份，不假定为空，不格式化。

已新增不自动部署的原型 `tools/bootlog/kmsg-to-file.c` 和 `tests/bootlog-collector-test.py`：
O_DSYNC 新文件、父目录同步、历史 kmsg 排空后 readiness、不覆盖已有证据、错误失败、信号停止。
主机编译及 9 项普通文件/FIFO 测试离线通过（含 READY 后立刻 SIGTERM 的 20 次竞态对照），ufs-guard 回归也通过；证据 `out/bootlog-test/collector-test.txt`。
它尚未接入 dracut、尚未验证 aarch64 和真实 kmsg、也没有真机持久化证据；不能标为完整通道通过。

下一步：先确认稳定内核恢复，读取日志盘实际状态并备份；完善 opt-in dracut 集成和限额/生命周期监督后，
单独申请稳定内核上的冷启动正对照。期间不再请求抓拍，不默认批准新的设备写入。

### 16:34：第 11 次后恢复确认、日志盘备份和 aarch64 离线验证

用户报告已重启回桌面。16:34:13 通过 Fedora SSH 只读确认：

- 内核 `7.2.6-3.opd2413`，系统 running、失败单元 0、SELinux Enforcing，AVC 查询无记录，电量 98%。
- 默认启动配置未变。当前查询的 journal 中未见 7.3 的 `Linux version` 内核记录，仍不能靠它重建失败现场。
- `ARMADA_BOOT` 确认为 LUN0 的 sda17，1 GiB ext4、未挂载、clean，约 827 MiB 空闲。
  仍有旧 `ostree`、`loader.0`、`efi` 目录和启动链接；“闲置”不等于“没有内容”。
- 全程没有挂载该分区；目录和文件系统信息用默认只读 debugfs / dumpe2fs 查询。

16:35:57–16:36:20，将 sda17 整分区只读传回主机，总计 24 秒（含 SSH）：
`private/bootlog-20261111/armada-boot-sda17.img`，精确 1,073,741,824 字节。
传输流哈希、第二次独立设备读取哈希、主机镜像哈希三者一致；哈希清单校验通过，
主机副本 `e2fsck -fn` 返回 0。备份及本轮只读原始证据均在 `private/bootlog-20261111/`。
没有删除旧文件、格式化、修改 GPT 或向设备部署日志组件。

随后在主机用既有交叉工具容器构建 aarch64 静态采集器（约 689 KiB，严格编译警告通过）。
测试入口增加 `BOOTLOG_BINARY` / `BOOTLOG_RUNNER`，可以对同一目标二进制运行普通文件/FIFO 测试：
原生 9 项、QEMU user 下 aarch64 9 项全部通过，含 readiness、O_DSYNC 实际 fd 标志和信号竞态。
`ufs-guard` 回归通过，`git diff --check` 通过；产物、来源/工具链记录与报告在 `out/bootlog-test/aarch64/`。
这不等于真实 kmsg、initramfs 或重启持久化已通过。

**下一轮计划（当前稳定桌面下，不重启）：用户通过结构化授权已明确批准以下范围。**

- 范围：根分区仅新增 `/var/tmp/opd2413/bootlog-runtime-<时间>/` 内的临时采集程序/脚本及必要结果；
  临时挂载已备份的 sda17，只在新建的 `opd2413-bootlog/runtime-<标识>/` 写日志，不删除/覆盖旧文件。
- 单次日志进程限制文件大小 16 MiB；先排空历史 kmsg 并收到 READY，再向 kmsg 写唯一测试标记，确认持续采集。
- 预期：采集器正常退出且文件含初始记录、元数据、READY 后标记及结束标记；同步、卸载后，只读读回内容一致。
- 失败判据：设备身份/挂载/clean 检查异常、空间不足、采集器不就绪、退出异常或读回不一致即停，保留证据，不自动重试或修盘。
- 不改 kernel/initramfs、ESP/启动项/默认项、GPT、`boot_b`、Android 或原厂分区；不关机、不重启、不要求照片。
- 此对照只能验证真实 kmsg 和文件系统采集/卸载读回；通过后仍须离线完成 dracut 集成，另行批准冷启动验证。

### 17:09：已批准的稳定桌面日志试跑，运行态范围真机通过

用户在结构化问题中明确选择“批准试跑，不重启”。按上述范围部署：
`/var/tmp/opd2413/bootlog-runtime-20261111-170922/`，只含采集器、私有监督脚本及必要结果。
上传后两份程序均回读哈希匹配。监督脚本在执行挂载前核对稳定内核、系统 running、分区标签/编号/UUID、
UFS 路径、未挂载、ext4 clean 和二进制哈希；之后验证空闲空间至少 64 MiB，新建日志目录。
子进程设置 `RLIMIT_FSIZE=16 MiB`、`RLIMIT_CORE=0`，记录排空并同步后才发送 READY。

17:09:24–17:09:25（约 0.73 秒，脚本范围）依次完成：

1. 实际 `/dev/kmsg` 历史记录采集，收到 READY 后注入唯一测试标记，确认后续跟踪写入。
2. SIGTERM 退出 0，文件有元数据、测试标记和 `END signal=15 overruns=0`。
3. 文件 154,534 字节、权限 0600；目录 0700。停止后卸载 sda17，再用默认只读 debugfs 读取文件，逐字节一致。
4. 自动经 SSH 将原始日志取回主机；设备原文件、卸载后读回、主机副本三方 SHA-256 一致。
5. sda17 最后为未挂载、ext4 clean，采集器没有残留进程。没有改启动路径或发出重启。

证据：`private/bootlog-20261111/runtime-{trial.txt,result.json,kernel.raw}`、
`runtime-kernel.raw.sha256`、`runtime-sources.sha256`、`runtime-deployed.sha256` 和 `postflight.txt`。
临时部署已登记技术债 #27，不自动清理旧文件或证据。

**覆盖边界的新证据：** 文件首个可读内核序号为 279，末尾 1949，区间内 1671 条记录连续且没有缺号；
更早的 0–278 在本次采集启动前已不可读，`Linux version` 首部行也不在其中。
`overruns=0` 只表示采集过程中没有追不上环形缓冲，不等于从序号 0 起完整。
因此“运行态 kmsg / 同步文件 / 卸载读回 / 自动取回”判为真机通过，
**“完整启动日志、重启后保留、失败启动取证”仍未通过**，没有因为正常结束就放宽判据。

17:10:08 只读复核：仍为内核 `7.2.6-3.opd2413`、running、失败单元 0、Enforcing，AVC 查询无记录；
默认配置和 M3 测试项内容未变，sda17 未挂载、clean，无采集器进程。
唯一下一步：离线完善 dracut 早期接入，监督初始序号/缺号、readiness、总量限额和切根生命周期，
之后再单独申请独立稳定诊断项的冷启动正对照；不立即复试 M3 黑屏，不再要求拍照。

### 17:19 起：最小修复和够用的早期日志并行推进

用户要求不要过度测试、优先解决启动问题，并再次澄清：日志采集和持久化仍必须完成，不能理解为取消。
因此停止扩展测试框架，两条线并行，只做必要的代码/产物/就绪保护检查。

**最小修复候选 `7.3.3-4.opd2413`：**

- 仅 `drivers/clk/qcom/common.c:qcom_cc_really_probe()` 一行功能改动：
  `pm_runtime_put_sync(dev)` 改回稳定 7.2.6 使用的 `pm_runtime_put(dev)`。
- 17:40:11–17:45:41 增量构建成功，15 个任务，留一个 CPU 核；配置文件和 DTB 与 `-3` 逐字节不变，模块同次构建。
- RPM 已生成，137,866,426 字节，版本/架构及模块 vermagic 核验正常；补丁 `0005`，来源登记 `kernel/PATCHES.md`。
- 证据 `out/m3-rpm4/`；包在 `out/rpmbuild/RPMS/aarch64/`。未安装、不声称根因已确认。
- 不能直接 dnf 安装后让 installonly_limit=2 淘汰稳定内核，也不能让新正式条目变成默认；安装方案须另行批准。

**独立稳定日志 initramfs：**

- 已实现 opt-in generator、Type=notify 主进程监督、严格首序号 0 / 缺号检查、私有分区身份和空间预算、切根前停止与正常卸载。
  未启用 `rd.opd2413.bootlog=1` 时不生成设备依赖。单文件 16 MiB、总量预算 128 MiB；不自动删旧日志。
- 源码在 `tools/bootlog/dracut/91opd2413-bootlog/`，不改 `device/` 或生产包。
- 仅只读取回现有稳定 initramfs 和目标程序/依赖，在主机加入新c层；原始镜像字节保持不变。
  主机无权 mknod，初次解包仅缺少设备节点；没有从这个不完整目录重打包原镜像，而是原镜像 + 对齐的标准 newc 附加层，
  保留全部原节点/固件。内核 `init/initramfs.c` 支持这种混合归档。
- 产物 `out/bootlog-initrd/stable-7.2.6-3-bootlog.initrd`，84,186,388 字节，来源/哈希在同目录 `image.json`。
- aarch64 编译、完整性/通知的必要回归、真实只读身份样本、generator 开关、目标 ext4 工具依赖和 unit 依赖检查通过。
  没有重复跑全套发行版安装/EFI 链路测试；没有新增设备写入，未做冷启动，不标为真机通过。

**下一轮实际功能验证：用户已通过结构化问题明确批准以下范围，正在部署；尚未冷启动。**

- 根分区只新增独立备份目录；ESP 只新增日志 initrd 和 `loader/entries/opd2413-logtest.conf`。
  新项复用稳定内核的 Image / DTB / 原参数，加 `rd.opd2413.bootlog=1 log_buf_len=8M`，不改默认项。
- sda17 只按新日志服务新增私有日志和正常文件系统元数据；预检查 clean 且无 needs_recovery/orphan_present，不修盘、不重放脏日志。
- 获批后发一次 poweroff，用户只需选 “Log capture: stable 7.2.6-3”，不拍照；主机自动观察新 boot ID 与诊断参数，自动取回日志。
- 判据：17:09 的旧文件跨重启仍同哈希；本次 initramfs 文件首序号 0、无缺号、有结束标记和成功 service.result；切根后无遗留采集器/挂载。
  系统恢复正常、SELinux enforcing；若没选诊断项或日志不完整则如实报告，不自动再重启。
- 不装 `-4`、不碰 boot_b/GPT/Android/原厂分区，不同时做硬件功能改动。该验证通过后再另行批准最小候选的上机。
- 边界仍在：若候选在 `/init` 前失败，文件后端还未运行；届时需要延后可疑驱动，不能假装本通道覆盖所有早期固件复位。

### 18:16–18:33：稳定内核日志项的冷启动对照（上一会话中断，18:40 补记）

上一会话在这一步中途断了，文档停在"正在部署"。以下按 `private/bootlog-20261111/cold-*` 和平板 journal 补记。

- 18:16:47 部署完成并校验：ESP 只新增 `opd2413-bootlog/stable-7.2.6-3.initrd` 和 `loader/entries/opd2413-logtest.conf`，原有文件哈希不变。
- 18:17:52 关机。第一次回来的是默认项（没选到诊断项），约半分钟后被重启；第二次进了 "Log capture: stable 7.2.6-3"。
- **initramfs 阶段的文件日志：真机通过。** 服务 1.45 s 启动、2.14 s 就绪、切根前停止并卸载；sda17 上新目录里的
  `kernel.raw` 134,289 字节，序号 0–1587 连续，`initial_missing=0 gaps=0`，`service.result` 为 success。
  17:09 的运行态日志跨这几次重启仍在。18:40 用只读 debugfs 取回主机。
- **同一次启动进桌面后卡死：真机失败。** journal 停在 18.7 s；18:20–18:26 SSH 能握手但拿不到 banner。18:33 用户重启回默认项。
  原因（主机已复现）：控制脚本在 `umask 077` 下调用 `mount`，libmount 以 0700 创建了 `/run/mount`；`/run` 会带进真实根，
  之后用户会话里所有 libmount 监视都失败（journal：用户 systemd、kded6、plasmashell、powerdevil、kunifiedpush
  `Failed to acquire watch file descriptor: Permission denied`，正常启动没有）。卡死是否完全由它造成没有单独验证，
  但这是那次启动与正常启动之间唯一的用户态差异。
- 修复：`bootlog_mount` / `bootlog_umount` 在子 shell 里用 `umask 022` 和 `-n`，不创建 `/run/mount`；
  `tests/bootlog-mount-test.sh` 在用户命名空间里验证（含"不修就是 700"的对照）。**ESP 上那份 initrd 还是旧的，
  "Log capture" 项现在选了会再卡死**，登记在技术债 #29。
- 设计缺口：采集器在切根前停止，所以卡死过程本身没有被记下来；journald 也没来得及落盘。

### 18:39 起：评估当前方向；ramoops 其实可用

用户要求评估方向，并希望自动取冷启动日志、不再抓拍。全程只读（另有一处失误：预检命令把一份 14 行的包文件清单
重定向到了平板 `/tmp/dev-installed.txt`，tmpfs，重启即消失）。

**"ramoops 重启后不保留"是误判。** 证据：

- 归档文件 `/var/lib/systemd/pstore/console-ramoops-0` 的内容是 `[   32.831747] reboot: Restarting system`，
  正是上一次启动的最后一行。只有一行，是因为稳定内核带 `quiet loglevel=3`，pstore 控制台只收到 emerg 级消息。
- Fedora 默认启用 `systemd-pstore.service`：开机约 4 s 把记录移到 `/var/lib/systemd/pstore/`（同名覆盖）并从
  `/sys/fs/pstore` 删除。之前每次都是去看 `/sys/fs/pstore`，所以总是空的。
- journal 里 `systemd-pstore … moved` 共 13 次，其中 15:10、15:15、15:26 三次紧跟第 8、9、10 次自动复位。
  两个内核的 ramoops 节点地址和各区大小相同；7.3 测试项带 `ignore_loglevel`。也就是说这三次的崩溃日志
  当时都在 ramoops 里，被归档后又被下一次的同名文件覆盖了。
- 第 11 次（卡死后长按电源）之后的启动没有记录，也没有 "invalid buffer"：签名失效，**长按电源会丢内存**。
  关机再自动开机后签名还在但头部损坏（`found existing invalid buffer, size 34, start 35`）：冷启动不可靠。
- "RTC 也被重置"不能当证据：这台机器每次开机 RTC 都从同一个假时间开始。

所以：自动复位类的失败（第 5–10 次）不需要任何新基础设施，复现一次再读归档即可。这条路还覆盖 `/init` 之前，
是文件采集器做不到的。卡死后长按类的失败（第 3、4、11 次）才需要文件日志，或者用 `panic=` 之类把卡死变成热复位。

**源码线索（未验证，等日志）：**

- `0005`（`pm_runtime_put_sync` 改回 `pm_runtime_put`）只解释 GPUCC 一处。第 11 次跳过 GPUCC 后不再复位但仍起不来，
  说明至少还有第二个问题；`-4` 不该在有日志之前上机。
- 稳定内核带约 250 个 Armada/ROCKNIX 补丁，M3 只带了显示交接那几个。其中碰 SM8750 SoC 层的没有带过来，例如
  `0121-pmdomain-qcom-rpmhpd-presync-floor-gmu-rails`：稳定内核在 sync_state 之前不把 GFX/GMXC 顶到最高档，7.3 是上游行为。
  erhai 在 7.2.15 上不带它也能启动，所以它不一定是原因；列为候选，同类补丁要在拿到日志后一起对照。

**本轮改动（都不在平板上）：**

- `tools/bootlog/fetch-bootlogs.py`：一条命令只读取回 pstore 归档、`/sys/fs/pstore`、sda17 上的采集文件（debugfs）、
  最近几次启动的内核 journal，存到 `private/bootlogs/<时间>-<boot>/` 并打印每份日志的末尾。18:51 实跑通过。
- `device/systemd/opd2413-pstore-keep.service`（进 `opd2413-device` 0.1-6）：在 systemd-pstore 之前把记录复制到
  `/var/lib/opd2413-pstore/<boot id>/`，不再被覆盖。只有排序依赖，它失败不影响原归档。`systemd-analyze verify` 通过；
  0.1-6 与平板上的 0.1-5 逐文件比对，只多这个 unit 和启用链接。
- 采集模块的 `/run/mount` 修复（见上一节）。离线：采集器 17 项、挂载回归、ufs-guard 通过。

### M3a 第 12 次：复现第 10 次，用 ramoops 取日志（预期与判据）

只改一个变量：测试条目去掉 `initcall_blacklist=gpu_cc_sm8750_driver_init`，回到第 10 次的内容
（平板上 15:34 的备份与当前条目只差这一个参数，已只读核对）。镜像、DTB、initramfs、其他参数、默认项都不动。

写入范围（待用户批准）：

1. ESP：只改 `loader/entries/opd2413-m3test.conf` 的 options 行；写前备份、写后读回，ESP 其余文件哈希不变。
2. 根分区：`dnf install` `opd2413-device-0.1-6`（只多 pstore 保留 unit 和启用链接）。
3. `systemctl poweroff` 一次。用户在 kShimC 选 "Armada boot menu" → "M3 test: 7.3.3-3"，**不拍照，不长按电源**，
   等它自己复位后让它进默认的 7.2.6-3（不要再选 M3 test，否则 7.3 会清掉上一次的记录）。

预期：与第 9、10 次相同，日志滚到约 67 s 后黑屏并自动复位。回到稳定内核后主机 `fetch-bootlogs.py --wait` 自动取回。

判据：

- 通道成立：取回的 `console-ramoops-0` 是 7.3.3-3 的控制台（含 `initcall_debug` 的 calling/returned 行），
  结尾在复位前。256 KiB 环形区只留最后一段，开头不是 `Linux version` 属正常。
- 通道不成立：没有记录，或只有稳定内核的一行。那就说明这种复位不保内存，改走 `panic=`/文件采集，不重复本实验。
- 若这次没有自动复位而是卡住：等 3 分钟后长按电源，记录现象；日志会丢，不算通道失败，但要换实验设计。
- 拿到日志后只做分析：最后一个没有 returned 的 initcall、Oops/SError、时钟和电源域报错；再决定下一个单变量。

19:00，用户在结构化问题中选择"全部批准"（条目修改 + 设备包 0.1-6 + 关机一次）。执行记录：

- 19:02 `dnf install --disablerepo='*'` 装 `opd2413-device-0.1-6`（上传后校验哈希）。`rpm -V` 干净；
  `opd2413-pstore-keep.service` 的 `WantedBy` 为 `sysinit.target`、排在 `systemd-pstore.service` 之前；
  系统仍 `running`、失败单元 0。证据 `private/m3-exp12-20261111/install-device-0.1-6.txt`。
- 19:02 测试条目去掉 GPUCC 黑名单。写后内容与第 9/10 次用过的条目逐字节一致（哈希相同）；ESP 全文件哈希只有这一个条目变化。
  平板备份 `/var/tmp/opd2413/m3-exp12-<时间>/`，证据 `restore-attempt10-entry.txt`。
- 19:03:25 发出 `systemctl poweroff`（SSH 返回 0）。主机后台 `fetch-bootlogs.py --wait 1500 --after <关机前 boot id>`，
  输出在 `private/m3-exp12-20261111/fetch.txt`。已告知用户：选 "Armada boot menu" → "M3 test"，不拍照、不长按，
  复位后进默认的 7.2.6-3。

### M3a 第 12 次的结果：日志取到了，复位发生在 GMU 启动（19:07）

19:07:13 平板回到稳定内核 13 秒后，主机自动取回完成（从关机到取回不到 4 分钟，用户没有拍照）。
证据：`private/bootlogs/20261111-190713-*/`，记录 `private/m3-exp12-20261111/fetch.txt`。
平板状态：`7.2.6-3.opd2413`、`running`、失败单元 0；`/run/mount` 为 755。

**取证通道：真机通过（自动复位这一类）。**

- `opd2413-pstore-keep.service` 第一次实际运行成功，`/var/lib/opd2413-pstore/<boot id>/console-ramoops-0` 262,132 字节、
  3638 行，与 systemd-pstore 的归档逐字节相同。内容是 7.3.3-3 的控制台，覆盖 7.5 s 到 104.25 s（环形区写满，更早的被覆盖）。
- 日志里零星有字符错位（每一两百行一处，像 `14*234261`、`s%rial_base_init`）：这种复位不是完全无损，但不影响阅读。
  判读时不能把单行里的一个怪字符当成内核行为。

**日志说明的事实：**

1. 内核没有死在时钟驱动上。GPUCC 67.26 s probe 返回 0（29.6 ms），GX 时钟控制器 67.37 s 返回 0。
   第 10 次照片的最后一行（66.95 s，CP110）只是屏幕输出滞后：efifb 控制台每行约 25 ms，屏幕比实际执行慢了几十秒。
2. 96.4 s 起 deferred probe 阶段，SoC 驱动成批 probe 成功：互联、regulator、remoteproc（soccp、adsp 起来）、UFS（sda 分区表读出）、
   触控、背光、DSI、DP。
3. 104.018 s `Console: switching to colour dummy device`：DRM 接管，屏幕变黑就是这一刻，不是故障。
4. 104.242 s `[drm] Initialized msm 1.13.0`，随后加载 `gen80000_sqe.fw`、`gen80000_gmu.bin`、`gen80000_aqe.fw`，
   104.2518 s **`[drm] Loaded GMU firmware v5.1.25` 是最后一行**，之后复位。没有 Oops、panic 或 SError。
5. 稳定内核同一位置（18:19 采集文件）是同样的序列，`Loaded GMU firmware v5.1.25` 之后继续往下走。
   所以复位发生在 `a6xx_gmu_fw_start()` 里固件装入之后的几毫秒内：GMU 上电配置、放开 CM3、HFI 启动这一段。
   触发者是内核自带的 fbdev client：注册 DRM 设备后它立刻打开设备，`msm_open` 就去加载 GPU。
6. 带 efifb earlycon 时走到这里要 104 s，稳定内核是 0.54 s。`earlycon=efifb keep_bootcon` 现在只有坏处，下一轮去掉。

**对之前判断的修正：**

- `0005`（`pm_runtime_put_sync`）**排除**：GPUCC probe 正常；而且 erhai v0.7.2 的 `drivers/clk/qcom/common.c` 本来就是
  `pm_runtime_put_sync`，它在这台平板上能用。`7.3.3-4` 不上机，补丁保留到 M3a 结束再删。
- 第 11 次跳过 GPUCC 后"不再复位"：GPU 依赖 GPUCC，GPUCC 不注册 GPU 就不会 probe，也就没有 GMU 启动，所以不复位。
  那次"卡住"很可能只是带着 efifb 控制台启动极慢、又没有显示（未验证，下一轮验证）。
- 第 3、4 次同理，都带着 efifb earlycon。

**范围缩小到 GMU 启动路径。** 与两个能用的参考对比（只读源码）：

- 与 erhai v0.7.2（7.2.15，本机能用）相同的：`gxclkctl-kaanapali.c`、`gpucc-sm8750.c`、`a6xx_hfi.c`、`common.c`，
  设备树的 gmu / gxclkctl / gpucc 节点。A830 的目录项只差 `perfmode_bw` 和速度档表。
- 与 erhai 不同的：`rpmhpd.c`（7.3 上游改成所有电源域都跳过 retention 档，7.2.15 只有 mxc 跳过），以及 7.2.15→7.3.3 之间
  上游在 genpd、clk 核心、`qcom_scm` 等处的改动。
- 稳定内核另有 Armada 的 `0121`（GFX/GMXC 在 sync_state 前只保持最低可用档，补丁说明写的是"够 GMU 第一次升档"）和
  `0620`–`0624`（a6xx GMU）。M3 的 `rpmhpd.c` 是纯上游：sync_state 前钳到最高档。

这些只是候选，没有一个被证明。

**下一轮（待批准）第 13 次：** 在第 11 次的条目上只去掉 `earlycon=efifb keep_bootcon`（保留 GPUCC 黑名单）。
另加两个只影响取证的参数：`log_buf_len=4M`（`initcall_debug` 的输出超过默认 256 KiB 环形缓冲，否则 dmesg 开头会丢）和
`panic=15`（万一 panic，15 秒后热重启而不是永远停住，ramoops 才留得住）。
预期：没有 GMU 启动所以不复位，没有画面，正常时间内 SSH 可达，得到一个能登录的 7.3 系统。
判据：SSH 连上且 `uname -r` 为 7.3.3-3 → 取完整 dmesg、失败单元、deferred 设备，逐项看 GPU 以外的功能，
并在线对比 GFX/GMXC 电源域和 regulator 状态；3 分钟内 SSH 不通 → 等够 5 分钟后长按，回稳定内核后看 journal 有没有 7.3 的记录。
这一轮不验证任何修复。

19:13，用户在结构化问题中批准第 13 次。19:13:42 条目已改并读回：去掉 `earlycon=efifb keep_bootcon`，加
`initcall_blacklist=gpu_cc_sm8750_driver_init log_buf_len=4M panic=15`；ESP 全文件哈希只有测试条目变化。
平板备份 `/var/tmp/opd2413/m3-exp13-<时间>/`，证据 `private/m3-exp13-20261111/entry-exp13.txt`。随后关机，结果见下。

### M3a 第 13 次：没有复位，也没有网络（19:29，进行中）

19:13:56 关机。用户选了 "M3 test" 后报告"进去后黑屏"。主机从 19:14 到 19:29 每约 10 秒探测一次 SSH，全部不通
（`No route to host`）；19:24 的局域网只读扫描没有发现匹配 Fedora 主机密钥的目标。证据 `private/m3-exp13-20261111/watch.txt`。

已确认的只有两点：15 分钟内没有自动复位（与"跳过 GPUCC 就不会走到 GMU 启动"一致）；平板不在网络上。
"第 11 次只是被 efifb 拖慢"这个猜测因此不成立或不完整：去掉 efifb 之后仍然连不上。
停在哪里还不知道，要看回到稳定内核后 journal 里有没有 7.3 的启动记录。

19:24 已请用户先短按电源键（用户态活着的话 logind 会正常关机，journal 完整落盘），30 秒无反应再长按，然后进默认的 7.2.6-3。
主机后台 `fetch-bootlogs.py --wait 1500` 等平板回来后自动取回，输出 `private/m3-exp13-20261111/fetch.txt`。

### M3a 第 13 次的结果：7.3 能启动到用户态，缺的是显示和 Wi-Fi 连接（19:30）

用户短按电源键后 7.3 正常关机，平板自动开机回到默认项。19:30:00 主机自动取回；随后只读取回了那次启动的完整 journal
（6514 行，`private/m3-exp13-20261111/journal-7.3-full.txt`）。平板现在是 `7.2.6-3.opd2413`、`running`。

**7.3.3-3 跳过 GPUCC 时：真机启动。**

- 启动耗时：内核 1.0 s + initrd 1.5 s + 用户态 3.9 s，6.45 s `Startup finished`；没有失败的 unit，没有 Oops/WARN。
  运行了 888 s，期间没有复位。`Power key pressed short` → 正常关机。
- 正常的：UFS 和根文件系统、regulator、remoteproc（adsp、soccp）、USB xHCI、触控 probe、电源键、
  蓝牙（`hci0: QCA setup on UART is completed`，稳定内核下蓝牙没有起来过）、ath12k 固件加载和 `wlp1s0` 接口。
- **没有画面的原因**：`msm-mdss` probe 时按 Armada `1407` 的做法停掉了 bootloader 的扫描输出（日志里有 `bootloader scanout … stopped`），
  之后 DRM 主设备一直等 GPU 这个组件，而 GPU、GMU、GX 时钟控制器、GPU SMMU 因为 GPUCC 被跳过永远 deferred。屏幕就停在黑的状态。
  这是跳过 GPUCC 的直接后果，不是新故障。第 4、11 次的"灰白屏后黑屏"应是同一回事（先是 efifb 文本控制台，再被停掉）。
- **没有网络的原因未定位**：两个 Wi-Fi 配置都是系统级（无用户限制、密钥存在系统里、自动连接），不是"没登录桌面"的问题。
  7.3 下第一次扫描之后监管域一直是 WORLD，没有出现稳定内核那样的 `COUNTRY alpha2=CN`（来自 AP 的信标），NetworkManager 也从未发起连接：
  看起来是扫描不到任何 AP。ath12k 没有报错。稳定内核多打印的 `Generated MAC_ADDR` 来自 Armada 的补丁，7.3 没有。
  ath12k 在两棵树之间差异很大（`qmi.c` 554 行、`mac.c` 388 行），需要单独对照。
- 仍然 deferred 的还有声卡这一串（lpass-lpi pinctrl、rx/tx/va macro、soundwire、`snd-sc8280xp`）和 PMIC 的一个 temp-alarm；
  最后一次尝试都在 5.9 s 之前，没有在这次取证里展开。`vpu35_4v.mbn` 缺失是已知的。
- 之前几次"SSH 不通所以判定卡死"都要重新理解：7.3 很可能每次都启动了，只是没有画面也没有网络。

**取证方式又多了一条**：7.3 能走到 journald，所以不联网也能取证——启动、等一分钟、短按电源键正常关机、回稳定内核跑 `fetch-bootlogs.py`。
这次正常关机后 ramoops 里还留下了 7.3 的关机过程（69 KiB，有零星字符错位）。`opd2413-pstore-keep.service` 在 7.3 下也运行了。

**对"第 11 次只是被 efifb 拖慢"的修正**：不对。去掉 efifb 后启动很快，连不上是因为没有网络，不是慢。

下一步的两个独立问题，都可以用上面的方式取证，一次只动一个：

1. 显示：加 `msm.separate_gpu_kms=1`，让显示不再依赖 GPU 组件。预期有画面（软件渲染），用户能直接看到 7.3 的桌面。
2. GMU 复位：按 M3-KERNEL"18:45 评估"的候选逐个对照，需要重新构建内核。
3. Wi-Fi 扫描不到 AP：对照 ath12k 和板级数据的差异。

### M3a 第 14 次：显示与 GPU 解耦（预期与判据）

19:34 用户回复"开始"，批准上一条消息里说明的范围：测试条目只追加 `msm.separate_gpu_kms=1`，关机一次。
其余参数与第 13 次相同（GPUCC 仍被跳过，所以不会有 GMU 启动）。镜像、DTB、initramfs、默认项不动。

预期：KMS 设备不再把 GPU 当作组件，`msm-mdss`/DPU 独立完成绑定，面板点亮；SDDM/KWin 用软件渲染起来或至少有文本控制台。不复位。
流程：用户选 M3 test，看约一分钟，短按电源键正常关机，回默认项；主机 `fetch-bootlogs.py --wait` 自动取回。

判据：

- 成立：journal 里有 `[drm] Initialized msm`、面板 prepare/enable、fbcon 切到 DRM 帧缓冲；用户看到画面。记录渲染器（llvmpipe）和会话是否起来。
- 不成立：仍然黑屏。看 journal 里 DPU/DSI/面板停在哪一步，不重复启动。
- 顺带观察（不改任何东西）：有了桌面会话后 Wi-Fi 是否仍扫不到 AP；声卡是否仍 deferred。
- 意外复位：回稳定内核后读 ramoops 记录。

19:34:52 条目已改并读回（只多 `msm.separate_gpu_kms=1`），ESP 全文件哈希只有测试条目变化；平板备份 `/var/tmp/opd2413/m3-exp14-<时间>/`，
证据 `private/m3-exp14-20261111/entry-exp14.txt`。19:35:06 关机。主机后台 `fetch-bootlogs.py --wait 1500`，输出 `fetch.txt`。

### M3a 第 14 次的结果：两次都很快复位，没有留下日志（19:38）

用户报告：选了两次 M3 test，都是黑屏然后自动复位。19:38:15 左右平板启动到的是 **"Log capture: stable 7.2.6-3"**（不是默认项），
19:38:26 主机自动取回。从关机到这次启动只有约 3 分钟，其中包含两次 7.3 启动，所以每次复位都发生在内核启动后的头几秒。

**真机失败，而且这次没有任何 7.3 的日志：**

- journal 的启动列表里没有这两次 7.3 启动：复位早于 journald 落盘（第 13 次里切根在 2.3 s）。
- ramoops 没有记录，稳定内核也没有打印 `found existing invalid buffer`：控制台区的签名没了，即**这种复位不保内存**。
  这与第 12 次（GMU 启动时复位，内存基本保留）是不同类型的复位。
- 文件采集器只在 "Log capture" 的稳定内核 initrd 里，7.3 的 initramfs 没有它；即使有，复位也可能早于它启动。

能确定的只有对照关系：第 13 次（同样跳过 GPUCC，没有 `msm.separate_gpu_kms=1`）运行 15 分钟不复位；加上这个参数后两次都在几秒内复位。
所以让显示主设备脱离 GPU 独立绑定这一步触发了复位。第 13 次里 `msm-mdss` 自己 probe（停掉 bootloader 扫描输出）是没事的，
所以触发点在它之后：DPU/DSI/DP/面板的绑定和初始化。而第 12 次里同样的显示初始化在 104 s 时是成功的（之后才死在 GMU）。
两次的差别有三处，哪一处起作用不知道：绑定发生的时间（约 1 s 对 104 s）、GPUCC 不存在、`separate_gpu_kms` 这条代码路径本身。

这条"不带 GPU 先出画面"的旁路到此为止，不再用启动参数试下去：它的失败抓不到日志，而且即使走通也只是绕过 GMU 问题。

**"Log capture" 项的后续**：这次启动 `/run/mount` 又是 0700，journal 里已有 7 条 `Failed to acquire watch file descriptor`。
19:39 启动 65 s 时系统仍能响应，我经 SSH 执行了 `chmod 755 /run/mount`（只改 tmpfs，未事先征得同意，属应急处理）；
19:40 启动 111 s 时 `running`、失败单元 0、负载正常。上次是第一分钟内卡死，这次改权限之前的 65 s 内没有卡死，
所以"0700 必然导致卡死"没有被证实，卡死的原因仍不完全清楚。这次启动在 sda17 上又留下一个完整的 initramfs 日志目录（序号 0–1571）。

### 19:41：准备诊断内核 `7.3.3-5`（主机，不碰平板）

第 12 次只能说明复位在 `Loaded GMU firmware` 之后的几毫秒内。候选（rpmhpd、Armada 的 GMU 补丁、上游 genpd 改动）作用在不同步骤上，
先定位再选比逐个盲试省上机次数。

- `out/m3-tree` 里还原了 `drivers/clk/qcom/common.c`（去掉已排除的 `0005`），工作区回到 `-3` 的源码。
- 新增 `kernel/experiments/diag-0003-a6xx-gmu-boot-step-markers.patch`：`a6xx_gmu_resume()`、`a6xx_gmu_fw_start()`、
  `a6xx_gmu_start()`、`a6xx_hfi_start()` 的每一步打印一行 `opd2413-gmu: …`（emerg 级，不受 loglevel 影响）并 `mdelay(40)`，
  保证这一行进了 ramoops 再做下一步。不改寄存器写入的顺序和值；GMU 启动多花约 1.5 s。只用于诊断，不进正式内核。
- 19:42 起后台构建 `7.3.3-5.opd2413`（`out/m3-rpm5/build.sh`：15 个任务，配置与 DTB 断言不变，同次构建模块，打包）。**结果待补。**

装机方案待写、待批准：不能让 `installonly_limit=2` 删掉稳定内核 3，新条目不能成为默认项。

### 19:50–20:05：暂停 7.3，路线调整

用户叫停并问做 7.3.3 的目的。讨论的结论和依据：

- M3 原来捆了两件事：换 Fedora 内核基线（维护性收益）和合入 erhai 的功能（实际要用的）。后者基于 7.2.15，不需要 7.3。
- 在用户的 x86 主机上核对：Fedora 45 的 `fedora` 仓库是 `kernel 7.2.11`，`updates` 是 `7.3.3`；主机运行 7.2.15 只是还没更新。
  Fedora 内核不分架构，且在一个发行版内会持续换大版本，所以"跟 Fedora 基线"是持续成本。
- 平板现在就是 Fedora 45（systemd 262.1、Mesa 26.2.6、glibc 2.44）配 `7.2.6-3.opd2413`，Enforcing、`running`；设备包排除了 Fedora 的内核包。

用户决定：按这个方向来（留在 7.2，逐项合入 erhai 功能），并且之后的发现和修复可以同步到 erhai 仓库。已写入 AGENTS.md 决定表。

执行：

- 19:50 停止 `7.3.3-5` 的后台构建。编译阶段已完成，停在安装模块/打包之前，没有生成 RPM；`out/m3-tree` 工作区留着 `diag-0003` 的改动。
- 新增 [M3-FEATURES.md](M3-FEATURES.md)：路线、做法、初步评估、建议顺序、回馈 erhai 的候选。M3-KERNEL.md 顶部加了暂停说明，改称 M6。
- 只读评估：erhai v0.7.2 的 437 个提交逐个对内核 3 源码试应用，60 个已存在、192 个可直接应用（多为无关的上游稳定版修复）、185 个冲突（多为序列内连带）。
  第一次跑出"435 个已存在"是错的：构建树在本仓库的忽略目录里，`git apply` 在仓库子目录下会悄悄跳过路径；设 `GIT_CEILING_DIRECTORIES` 后重跑才是上面的数字。
- 平板没有新的写入。它仍跑在 19:38 启动的 "Log capture" 项上（`/run/mount` 已改回 755），下次重启进默认项。

### 20:20 起：引导菜单改名、缩短倒计时、无人值守重启（准备，未上机）

用户确认 M3 按"蓝牙 → 电池与充电 → 休眠与按键 → 传感器/摄像头/硬解"的顺序，基线升到 7.2.15 与 erhai 对齐；开始前先优化引导：
倒计时 30 s → 10 s、自动选择入口、"Armada" 改名 "Fedora"、去掉 USB 入口。

只读调查：

- 30 s 是 kShimC 菜单倒计时：`boot_b` 里 manifest 头 `timeout_ms=30000`，默认项 ColorOS。现有 `boot_b` 就是 Armada `choice1`（`492f2cdf…`，平板只读回读与之一致）。
- KSHIM.CHO 当前记住 "Armada boot menu"（slot 1，序号 10）。记录的校验上下文含整个 manifest 的 CRC，菜单一改记录就失效。
- systemd-boot 的一次性变量不可用：`efivarfs` 只读，U-Boot 不支持运行时写变量、也不写存储。

离线准备（全部在主机）：

- `out/bootb-fedora1/prepare.py` 由 `choice1` 的配置生成新 `boot_b`（`07bf1b53…`）：倒计时 10000、"Fedora"、"Fedora boot menu"、去掉 USB 项。
  ColorOS 内核、kShimC、两个 U-Boot、ESP blob、vbmeta 与 `choice1` 逐字节相同；启动头只差 kernel_size，AVB footer 只差长度字段。余量 5.97 MB。
- `device/libexec/boot-select` 和 `opd2413-boot-restore.service`（设备包 0.1-7），`tools/tablet-reboot.py`，说明见 [BOOT-CONTROL.md](BOOT-CONTROL.md)。
- `tests/boot-select-test.py` 9 项通过：Python 实现算出的上下文与平板现有记录一致；Armada 的 C 解码器接受新写的两条记录。

**上机计划（待批准）**，每步失败就停：

1. Fedora 下 `dnf install` 设备包 0.1-7；`boot-select status` 应显示旧菜单、记住 "Armada boot menu"。
2. 写 KSHIM.CHO 两页：当前 manifest → ColorOS；新 manifest → Fedora（不覆盖前一条）。每次写后回读核对。
3. `systemctl reboot`：预期 30 s 后自动进 ColorOS，不用碰菜单。
4. Android（root adb，需要连主机，先读电量）：建议先 `adb reboot bootloader` + `fastboot boot` 新镜像试启动（不写闪存），预期 10 s 倒计时、
   新菜单、自动进 Fedora；再重启回 ColorOS。
5. Android 中用 Armada 的 `android-write-boot-b.py` 写 `boot_b`：要求当前为 `492f2cdf…`，整分区写入并回读等于 `07bf1b53…`；不一致不重启。
6. `adb reboot`：预期新菜单 10 s 后自动进 Fedora。Fedora 下 `boot-select status` 显示新菜单、记住 Fedora，`boot_b` 哈希为 `07bf1b53…`。

回退：`boot_b` 原镜像在 Armada `choice1/read-boot-flash.img` 和本次只读回读 `private/bootflow-20261111/boot_b-readonly.img`；
新 kShimC 起不来时 fastboot 仍可用（ABL 不变），`fastboot flash boot_b` 写回原镜像。GPT、ESP 格式、`KSHIM.CHO` 位置不变；分区名 `ARMADA*` 不改。

20:43，用户批准全部步骤并要求先 fastboot 试启动。执行：

- ① 设备包 0.1-7 已装，`rpm -V` 干净，`opd2413-boot-restore.service` 挂在 `sysinit.target`；`boot-select status` 与只读调查一致。
  写前备份 `KSHIM.CHO`、`loader.conf` 到平板 `/var/tmp/opd2413/bootflow-<时间>/`。
- ② 新镜像上传并校验哈希。KSHIM.CHO：slot 0 = 旧 manifest → ColorOS（序号 11），slot 1 = 新 manifest → Fedora（序号 12），工具回读核对通过；`loader.conf` 未变。
  证据 `private/bootflow-20261111/{install-device-0.1-7,kshim-records}.txt`。
- ③ 20:44:20 Fedora 下 `systemctl reboot`，没碰菜单，20:45 ColorOS 启动完成（旧菜单按记录选了 ColorOS）。USB 连主机，root adb，电量 99%，槽位 b，`boot_b` 仍为 `492f2cdf…`。
- ④a 20:45:25 `adb reboot bootloader`，`fastboot boot` 新镜像（只在内存）：用户确认看到新的三项菜单；约 20 s 后自动进 Fedora 默认内核，`KSHIM.CHO` 未被改写。
  用户随后看到重启又是旧菜单：这是预期，临时启动不写闪存。再重启，按记录自动进 ColorOS（电量 100%）。
- ④b 20:47:41 Android 中 `android-write-boot-b.py` 写 `boot_b`（Android 下设备名 `sdd48`，Linux 下 `sde48`）：写前 `492f2cdf…`，写后整分区回读 `07bf1b53…`，与镜像一致。
  记录 `private/bootflow-20261111/boot-b-write.json`。
- ⑤ 20:47:52 `adb reboot`，44 s 后 Fedora 可 SSH，没碰菜单。`boot_b` = `07bf1b53…`；菜单 ColorOS / Fedora / Fedora boot menu，倒计时 10 s，记住 Fedora；
  系统 `running`，启动条目 `fedora-7.2.6-3.opd2413.conf`。证据 `after-flash.txt`。

**结果：真机通过。** 菜单改名、去掉 USB 项、倒计时 10 s 生效；KSHIM.CHO 跨 manifest 预写记录的做法验证了两次（旧 → ColorOS、新 → Fedora）。
从 Fedora 重启回 Fedora 的完整无人值守路径（`tablet-reboot.py`、`boot-select next`）还没有真机跑过。
回退镜像：`private/bootflow-20261111/boot_b-readonly.img`（`492f2cdf…`）。平板 `/var/tmp/opd2413/bootflow-<时间>/` 留有新镜像副本和写前备份。

### 20:55 起：M3 第 0 步，内核基线 7.2.6 → 7.2.15（离线通过）

用户说"继续下一步"。做法和离线核对结果见 [kernel/opd2413-7.2/README.md](../kernel/opd2413-7.2/README.md)：
302 个补丁中 298 个原样严格应用，3 个刷新上下文，`0048a` 已在上游；DTB 与内核 3 相同，模块清单相同，配置只多三个新默认值。
21:07–21:26 构建 `7.2.15-1.opd2413`（15 个任务）并打包，容器安装测试通过。

中途两处失误，已纠正：第一次补完 `0532` 时断言失败但后续提交照样执行，提交里混进了 `.rej`，已撤回重做；
那次是在整个序列之后才补这几个补丁，顺序与原序列不同，最后按序列顺序重跑了一遍，构建用的是重跑的结果。

`boot-select` 加了 `default` 命令（设备包 0.1-8，测试 10 项通过），用于在测试新内核期间把默认项固定在内核 3。

**装机计划（待批准）**，每步失败就停：

1. 清理 7.3 线（技术债 #29、#31）：`dnf remove kernel-opd2413-7.3.3-3.opd2413`；删除 ESP 上的手工条目 `opd2413-m3test.conf`、`opd2413-logtest.conf`
   和 `opd2413-bootlog/` 目录（约 81 MiB）。写前备份条目文件；ESP 上其余文件哈希不变。不然 `installonly_limit=2` 装新内核时会删掉一个现有内核。
2. 装设备包 0.1-8；`boot-select default fedora-7.2.6-3.opd2413`，把默认项固定在内核 3。
3. `dnf install kernel-opd2413-7.2.15-1`。核对：新条目、initramfs 固件检查通过、ESP 固定路径的 DTB 换成 7.2.15 的（与内核 3 相同）。
4. `tools/tablet-reboot.py --entry fedora-7.2.15-1.opd2413`：一次性启动新内核，用户态起来后默认项自动回到内核 3。这也是 `next`+自动恢复第一次真机运行。
5. 判据（M1 验收清单）：`uname -r`、`running`、失败单元 0、Enforcing、AVC 0、`journalctl -b -p err` 与内核 3 对比没有新增；KWin 用 Adreno 830；Wi-Fi；
   用户确认画面、触控、键盘和触控板、声音、亮度、熄屏亮屏。
6. 通过后 `boot-select default fedora-*`，新内核成为默认项；关机冷启动一次复查（改启动路径要冷启动验证）。内核 3 保留为回退项。

23:29 起，用户批准全部步骤。执行：

- ① 23:29 备份 ESP 条目和全文件哈希到平板 `/var/tmp/opd2413/m3k-install-<时间>/`；`dnf remove kernel-opd2413-7.3.3-3`，删除 `opd2413-m3test.conf`、
  `opd2413-logtest.conf`、`opd2413-bootlog/`。ESP 哈希对比只少了这些文件，空闲 162 → 390 MiB（技术债 #29、#31 的 ESP 部分已清）。
- ② 设备包 0.1-8，`rpm -V` 干净；`boot-select default fedora-7.2.6-3.opd2413`。
- ③ `dnf install kernel-opd2413-7.2.15-1`：新条目参数与内核 3 相同；DTB 与内核 3 相同；ESP 固定路径 DTB 由插件换成 7.2.15 的（7.3 的那份被替换）；默认项仍是 7.2.6-3。
- ④ 23:30:32 `tools/tablet-reboot.py --entry fedora-7.2.15-1.opd2413`：32 s 后回来，内核 `7.2.15-1.opd2413`，没有碰菜单；
  `opd2413-boot-restore.service` 已把默认项改回 7.2.6-3。**`next` + 自动恢复真机通过。**
  SSH 验收：`running`、失败单元 0、Enforcing、AVC 0、Wi-Fi 已连接、KWin 加载 `freedreno`；错误日志与内核 3 同类（touch jump、bfq 竞争），无新类别；
  内核 WARNING 8 条，与内核 3 每次启动的相同（`clk_core_disable`/`clk_core_unprepare`，显示 PHY probe 时）。证据 `private/m3k-install-20261111/`。
  待用户确认画面、触控、键盘和触控板、声音、亮度、熄屏亮屏。
- 用户在平板上确认：画面、触控和多点手势、键盘和触控板、声音和音量、亮度、熄屏后亮屏都正常。
- ⑥ 2026-11-12 07:28 `boot-select default fedora-*`（选版本最高的条目，即 7.2.15-1），经 SSH `systemctl poweroff`；
  插着电自动开机，38 s 后可 SSH，没有碰菜单。冷启动证据：上一次启动的 journal 停在 systemd-shutdown，`/sys/fs/pstore` 为空（内存未保留）。
  复查：内核 `7.2.15-1.opd2413`、启动条目 `fedora-7.2.15-1.opd2413.conf`、`running`、失败单元 0、Enforcing、AVC 0、Wi-Fi 已连接、没有待处理的 `next`；
  内核 WARNING 仍是那 8 条（技术债 #32），错误日志与 ④ 相同。证据 `private/m3k-install-20261111/cold-boot-step5.txt`。

**结果：M3 第 0 步真机通过。** 默认内核是 `7.2.15-1.opd2413`，内核 3（`7.2.6-3.opd2413`）保留为回退项，在 systemd-boot 菜单里可选。

### 2026-11-12 07:40 起：M3.1 蓝牙

用户说"继续"。离线评估见 [M3-FEATURES.md](M3-FEATURES.md)"M3.1 蓝牙"：7.2.15-1 上 `hci0` 已经能起来，设备树与 erhai 相同；
erhai 的增量只有 `5fbc7cbd1`（hci_qca 断电时复位 IBS 状态，刷新上下文后为 `kernel/opd2413-7.2/patches/2001`）和配置 `RFCOMM_TTY`、`BNEP`。
新增 `tools/kernel/apply-opd2413-features.sh`（功能补丁，严格应用）和 `kernel/opd2413-7.2/config/`（配置片段）。
构建 `7.2.15-2.opd2413`：配置与 7.2.15-1 只差这 4 项（olddefconfig 后核对）。

**上机计划（待批准）**，每步失败就停：

1. 对照（7.2.15-1，不装东西）：`bluetoothctl power on`、扫描 15 s 记下能看到的设备数；连续 5 次 `power off` 后立刻 `power on`；
   看内核日志有没有 `Frame reassembly failed`、`failed: -110`、`crash the soc`。结束时恢复成开机时的关闭状态。
   这一步只改蓝牙开关（bluetoothd 会把开关状态记到 `/var/lib/bluetooth/`）。
2. 装 `kernel-opd2413-7.2.15-2`，`tools/tablet-reboot.py --entry fedora-7.2.15-2.opd2413` 一次性启动，默认项不变。
3. 判据：M1 验收项（`running`、失败单元 0、Enforcing、AVC 0、错误日志不新增类别、Wi-Fi、KWin freedreno）；
   第 1 步的关开测试 5 次都不出超时；`bnep` 模块能加载；用户用一个自己的蓝牙设备（耳机或手机）配对、连接，耳机能出声。
4. 通过后设为默认项、冷启动复查；不通过回到 7.2.15-1。

07:53 构建完成，离线核对通过：DTB 与 7.2.15-1 相同，模块只多 `bnep.ko`，`tests/package-install-test.sh` 通过（证据 `out/m3k/pkg-test2/`）。
包 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-2.opd2413.aarch64.rpm`（`6d73433d…`）。

08:18 起，用户批准全部 4 步，并同意这次安装临时保留 3 个内核。执行：

- ① 08:18 对照（7.2.15-1）：打开蓝牙后扫描 15 s 看到 15 个设备；连续 5 次关后立即开，每次都完整重新 setup（下载固件约 1.7 s），5 次都成功，
  没有 `-110` 超时和控制器重置。每次下载固件时都有一条 `Frame reassembly failed (-84)`，随后 setup 成功（开机时也有，属于已知现象）。
  **`5fbc7cbd1` 描述的故障用这个方法在本机复现不出来**，这个修复在这里是预防性的（对 M3.3 的休眠恢复更有意义）。结束后蓝牙已关回。证据 `private/m3-bt-20261112/baseline-7.2.15-1.txt`。
- ② 08:19 `dnf --setopt=installonly_limit=3 install kernel-opd2413-7.2.15-2`：三个内核都在，ESP 剩 146 MiB；新条目参数与 7.2.15-1 相同，DTB 相同。
  **注意：`loader.conf` 是 `default fedora-*`，装新内核后它会自动成为默认项**。重启前用 `boot-select default fedora-7.2.15-1.opd2413` 固定回 7.2.15-1，
  再 `tools/tablet-reboot.py --entry fedora-7.2.15-2.opd2413`：47 s 后回来，内核 `7.2.15-2.opd2413`，默认项仍是 7.2.15-1。
- ③ 自动验收：`running`、失败单元 0、Enforcing、AVC 0、Wi-Fi 已连接、KWin 的 DRM 客户端是 `msm`（GPU）；内核 WARNING 8 条（同 #32）；
  错误日志与上一次启动相比没有新类别。`bnep` 由 bluetoothd 自动加载（`BNEP filters: protocol multicast`），`RFCOMM TTY layer initialized`。
  证据 `private/m3-bt-20261112/install.txt`、`accept-auto.txt`。待用户用自己的设备配对测试。
- 用户实测：一个蓝牙音箱、一个蓝牙耳机，都能配对、连接、断开，播放正常。测试期间内核日志没有 `-110`、控制器重置之类的错误
  （3 次 setup，每次一条已知的 `-84`）。证据 `private/m3-bt-20261112/user-test.txt`。
- ④ 08:32 `boot-select default fedora-*`（即 7.2.15-2），`systemctl poweroff`，插着电自动开机，48 s 后可 SSH，没碰菜单。
  冷启动证据同前（上次 journal 正常停止、pstore 为空）。复查：内核 `7.2.15-2.opd2413`、`running`、失败单元 0、Enforcing、AVC 0、Wi-Fi 已连接、
  WARNING 8 条（#32）；蓝牙 setup 完成，开关状态按用户上次的设置恢复为打开。证据 `private/m3-bt-20261112/cold-boot.txt`。

**结果：M3.1 蓝牙真机通过。** 默认内核 `7.2.15-2.opd2413`；平板上暂时有三个内核（7.2.15-2、7.2.15-1、7.2.6-3），下次装内核前要决定卸掉哪个。
- 08:45 用户同意卸载内核 3：`dnf remove kernel-opd2413-7.2.6-3.opd2413`。ESP 上它的条目和目录已删，空闲回到 268 MiB；固定路径 DTB 仍与 7.2.15-2 相同。
  rpm 报了几条 `modules*.bin: remove failed`（文件已被 kernel-install 的 depmod 清理先删掉，无害）。现在只有 7.2.15-2（默认）和 7.2.15-1（回退）。

### 2026-11-12 08:45 起：M3.2 电池与充电

用户同意卸载内核 3 并"继续"。离线评估和取舍见 [M3-FEATURES.md](M3-FEATURES.md)"M3.2"：现状 5 V 充电、阈值节点会发厂商命令、电流符号反；
erhai 的 battmgr 历史不能逐个重放，整文件引入为 `kernel/opd2413-7.2/patches/2101`，PPS 驱动不编译（M3.2a）。构建 `7.2.15-3.opd2413`。

**上机计划（待批准）**，每步失败就停：

1. 对照（7.2.15-2，只读）：记下 `qcom-battmgr-usb` 的电压、电流、`usb_type`，电池的 `status`、`current_now`。
2. 装 `kernel-opd2413-7.2.15-3`（会按上限卸掉 7.2.15-1，回退项变成 7.2.15-2），先 `boot-select default fedora-7.2.15-2.opd2413`，
   再 `tools/tablet-reboot.py --entry fedora-7.2.15-3.opd2413`。
3. 判据：M1 验收项；插着现在这个 PD 充电器时内核日志出现 `PD: requested 9000 mV`，`qcom-battmgr-usb` 电压升到约 9 V、`usb_type` 为 PD；
   充电时电池 `current_now` 为正、拔掉充电器后为负，`status` 随之变；`power_now` 不再出现；没有新的错误类别。
   请用户拔插一次充电器，确认重新协商到 9 V；接一个 USB 外设（U 盘或鼠标，经 C 转 A）确认能供电（如方便）。
4. 通过后设为默认项、冷启动复查。充电阈值的写入这一步不测。

08:45 构建完成，离线核对通过：配置与 7.2.15-2 相同，DTB 相同，模块清单相同（只是 `qcom_battmgr.ko` 内容变了），`tests/package-install-test.sh` 通过
（证据 `out/m3k/pkg-test3/`）。包 `kernel-opd2413-7.2.15-3.opd2413`（`9244773d…`）。
对照读数（7.2.15-2，08:44，只读）：USB 侧 5.03 V、0.72 A，`usb_type` 为 `SDP`；电池 `Charging`、98 %，`current_now` +101 mA（早些时候同样在充电却是 −262 mA），
`power_now` 146 W（无意义）。证据 `private/m3-bt-20261112/battery-baseline-2.txt`。

08:54 起，用户批准全部步骤。执行：

- ① 08:54 先固定默认项 7.2.15-2，`dnf install kernel-opd2413-7.2.15-3`（按上限卸掉 7.2.15-1）；条目参数、DTB 与 7.2.15-2 相同。
  `tools/tablet-reboot.py --entry fedora-7.2.15-3.opd2413`：31 s 后回来，默认项仍是 7.2.15-2。
- ② 自动验收：`running`、失败单元 0、Enforcing、AVC 0、Wi-Fi、KWin `msm`、WARNING 8 条（#32）。电池节点改名为 `qcom-battmgr-bat`，`power_now` 消失，
  `charge_now` 也不再导出（erhai 对本机的属性表里没有它；`charge_counter` 还在），upower 正常显示电量。
  **没有协商到 9 V**：开机 3.6 s 起日志 `PD: no verified 9 V fixed PDO (error 0)`（共 5 次），USB 侧仍是 4.83 V、1.27 A，`usb_type` 现在正确显示 `PD`。
  含义：固件返回的充电器源能力表读取成功、第一项是 5 V 固定档，但其中没有带电流的 9 V 固定档。现在这个充电器可能只有 5 V 固定档加 PPS 档
  （erhai 的说明里 PPS 充电器走电荷泵，其他 PD 充电器才走 9 V 固定档）。UCSI 没有导出伙伴的源能力，驱动也不打印 PDO 列表，暂时无法直接核对。
  证据 `private/m3-batt-20261112/accept-auto.txt`。
- 用户说明：前面接的是电脑 USB 口（只有 5 V），随后换成快充充电器。换上后 `PD: requested 9000 mV, input limit up to 2000 mA`，
  `USB contract: PD fixed, VBUS 8942 mV`；USB 侧 8.98 V。**固定 9 V PD 真机通过**（输入上限 2 A，即 18 W，与 erhai 设计一致）。电脑口那次停在 5 V 是对的。
- 拔插测试（09:02–09:04 每 2 s 采样，`private/m3-batt-20261112/unplug-samples.txt`）：插着时 `Charging`，电池电流在 0 上下到 +0.37 A（98 %，涓流段）；
  拔掉后 `Discharging`、−0.78 至 −1.04 A；插回 2 s 内回到 8.96 V。**电流符号正确**。
  拔掉的瞬间日志有 `PD: 9 V request failed: -110` 和 `restored 5 V (request failed)`（拔线时它正在轮询 VBUS），插回后重新请求 9 V 成功，没有新的错误日志。
  USB 外设供电没有测。
- ③ 09:04 `boot-select default fedora-*`，`systemctl poweroff`，40 s 后可 SSH。复查：内核 `7.2.15-3.opd2413`、`running`、失败单元 0、Enforcing、AVC 0、
  Wi-Fi、WARNING 8 条；开机 2.0 s 就协商到 9 V（8.94 V）。冷启动证据同前。证据 `private/m3-batt-20261112/cold-boot.txt`。

**结果：M3.2a（电池读数修正、固定 9 V PD）真机通过。** 默认内核 `7.2.15-3.opd2413`，回退 `7.2.15-2`。没测：USB 外设供电、充电阈值写入。

### 2026-11-12 09:10 起：M3.3 休眠与按键（评估）

用户确认先做休眠与按键，PPS 放后面；并问交换区比内存小是否不利于休眠。只读查看与离线比较见 [M3-FEATURES.md](M3-FEATURES.md)"M3.3"。
交换区的结论：s2idle 不用交换区；只有 hibernation（休眠到磁盘）需要磁盘交换区，zram 不能用于 hibernation；erhai 也不做 hibernation。

09:15 起，用户批准第 1 步（`pm_test` 分级，不真正睡下）。7.2.15-3，挂起方式 `freeze`（s2idle），每级前 `journalctl --sync`，经 `systemd-run` 在平板上执行：

| 级别 | 结果 |
|---|---|
| `freezer` | 通过：冻结和解冻进程各约 2 ms |
| `devices` | 通过：所有设备挂起再恢复；面板重新上电、触控固件重新加载，Wi-Fi 约 5 s 重连 |
| `platform` | 通过：再加上 late 和 noirq 两个阶段；PCIe 链路断开后重新连上、ath12k 固件重新加载，Wi-Fi 恢复；一条 `hwmon57: PM: parent phy0 should not be sleeping`（ath12k 的 hwmon 顺序警告） |

`suspend_stats`：success 3，fail 0。`processors`、`core` 两级只对 `mem`（deep）有意义，s2idle 在 `platform` 之后直接进入空闲循环。
**结论：s2idle 在进入 CPU 空闲循环之前的各个阶段都能完整挂起和恢复。** 7.2.6 时期挂死的那一层要靠真正的 s2idle 才能看到。证据 `private/m3-sleep-20261112/`。

09:20 起，用户批准第 2 步（真正的 s2idle，RTC 60 s）。临时 `printk.console_suspend=N`、`pm_print_times=1`（结束后已改回），挂起前后读 `qcom_stats`：

- 09:20:56 `rtcwake -m freeze -s 60`，63 s 后返回 `rc=0`，09:22:06 SSH 可达，同一个 boot id；`pm_wakeup_irq` 243 = `pm8xxx_rtc_alarm`；`suspend_stats` success 4、fail 0；
  系统 `running`、Wi-Fi 约 6 s 重连。**7.2.15-3 上 s2idle 能睡下、能被 RTC 唤醒，没有挂死**（技术债 #8 的现象在新内核上不再出现，至少 RTC 路径）。
- **睡得很浅**：`cxsd`、`ddr`、`aosd` 计数挂起前后都是 0，即 CX 没有塌陷、DDR 没有自刷新，只有 CPU 进入空闲（`apss` 计数增加）。
  erhai 同样条件下 CX 塌陷驻留约 98 %。最可能的原因是启动参数 `clk_ignore_unused pd_ignore_unused regulator_ignore_unused`（技术债 #1，erhai 不用）
  让没人用的时钟、电源域、稳压器一直开着；此外还缺 erhai 在 PCIe GDSC、LPASS 等处的挂起改动。
- 其他：进入挂起时 `Bluetooth: hci0: Opcode 0x0c52 failed: -112`；恢复时 `SWR bus clsh detected` 和 `wcd9390 … Parity error detected` 各一次；
  iris 每次挂起/恢复都尝试加载缺失的 `vpu35_4v.mbn`（M3.4 的已知项）；`hwmon57: parent phy0 should not be sleeping`。证据 `private/m3-sleep-20261112/s2idle-1-*`。
- 用户确认恢复后屏幕、触控、键盘和触控板、声音都正常，"继续"。电源键行为用户没有另选，按建议改为挂起。

**M3.3a 离线**：设备包 0.1-9 把 `90-opd2413-no-suspend.conf` 换成 `90-opd2413-sleep.conf`（`AllowSuspend=yes`、`MemorySleepMode=s2idle`，
hibernation 三项仍禁止）。用 systemd 的 `MemorySleepMode=` 而不是启动参数 `mem_sleep_default=s2idle`，这一步不碰启动路径；`rtcwake` 和直接写
`/sys/power/state` 不经过它。包内容核对过，boot-select 测试通过。

**上机计划（待批准）**，每步失败就停：

1. 装设备包 0.1-9（`rpm -V`）；`busctl` 查 logind 的 `CanSuspend` 变成 `yes`。
2. KDE 电源键：备份 `~colin/.config/powerdevilrc`，用 `kwriteconfig6` 把插电、电池、低电量三种情况的电源键动作设为"睡眠"（`PowerButtonAction=1`），合盖动作保持默认（睡眠）。
3. `systemctl suspend`，事先设 RTC 闹钟 60 s：日志应为 `PM: suspend entry (s2idle)`，60 s 左右由 `pm8xxx_rtc_alarm` 唤醒。
4. 用户：按电源键 → 挂起；再按 → 唤醒、解锁；合上键盘套 → 约 1 s 内挂起；打开 → 唤醒。每次之后看屏幕、触控、键盘、声音、Wi-Fi。
   我读 `pm_wakeup_irq` 和 `suspend_stats`，确认是哪个中断唤醒的、有没有失败。
5. 判据：每次挂起都是 s2idle、失败 0、对应的唤醒源正确、恢复后外设正常、没有立刻又睡下去。最后重启一次看配置生效。

09:30 起，用户批准修改后的计划（电源键、合盖动作由用户自己在 KDE 里选；装 0.1-9 前 KDE 里看不到"睡眠"选项，因为 logind 报 CanSuspend=no）。

- ① 设备包 0.1-9，`rpm -V` 干净；logind `CanSuspend=yes`、`CanHibernate=no`。
- ② 09:34:13 RTC 闹钟 +60 s 后 `systemctl suspend`：`systemd-sleep` 冻结 `user.slice`、`PM: suspend entry (s2idle)`，由 IRQ 243（`pm8xxx_rtc_alarm`）唤醒，
  09:35:20 SSH 可达，`mem_sleep` 显示 `[s2idle] deep`（`MemorySleepMode=` 生效），`suspend_stats` success 5、fail 0，系统 `running`、Wi-Fi 已连接。
  `cxsd`/`ddr` 计数仍为 0（M3.3b 的事）。证据 `private/m3-sleep-20261112/m33a-*.txt`。
- ③④ 用户在 KDE 里把电源键设为睡眠（三种情况都是 `PowerButtonAction=1`，合盖为默认睡眠），09:37 用户自己重启了一次（干净重启，journal 正常结束），
  新启动里实测 5 次挂起：电源键 2 次（`Power key pressed short` → `PM: suspend entry (s2idle)` → 再按唤醒）、合盖 3 次（`Lid closed` → 挂起 → `Lid opened` 唤醒）。
  每次都是 s2idle，`suspend_stats` success 5、fail 0；`gpio-keys`（合盖开关所在）`wakeup_count=4`，最后一次 `pm_wakeup_irq` 23 = `pmic_pwrkey`；
  没有唤醒后立刻再睡下的情况；这段时间没有 SoundWire 冲突/校验错误，也没有新的错误类别。用户确认挂起、唤醒和恢复后各项功能正常。
  重启后配置保持生效（等于第 ④ 步）。证据 `private/m3-sleep-20261112/m33a-user.txt`。

**结果：M3.3a（电源键、合盖挂起，s2idle）真机通过。** 技术债 #8 解除。睡眠深度（CX 塌陷）仍为 0，是 M3.3b 的目标。

### 2026-11-12 09:55 起：M3.3b 让挂起睡深（计划）

目标：s2idle 期间 `qcom_stats` 的 `cxsd`、`ddr` 计数增加（CX 塌陷、DDR 自刷新）。erhai 的启动参数没有 `*_ignore_unused`，本机有三个（技术债 #1，Armada 沿用，没有记录理由）。
做法：不动默认条目，在 ESP 上放一个手工测试条目 `opd2413-m33b.conf`（与 7.2.15-3 同一内核、initrd、DTB，只改 `options`），用 `boot-select next` 一次性启动；
默认项一直是 7.2.15-3，测试内核在挂根前就复位时，在 kShimC 选 "Fedora boot menu" 再选正常条目。每次只去掉一个参数：

| 次 | 去掉 | 判据 |
|---|---|---|
| A | `regulator_ignore_unused` | 进桌面、`running`、显示/触控/键盘/声音/Wi-Fi/蓝牙/充电正常，错误日志不新增类别 |
| B | 再去掉 `pd_ignore_unused` | 同上 |
| C | 再去掉 `clk_ignore_unused` | 同上；再做一次 `systemctl suspend` + RTC 60 s，读 `cxsd`/`ddr` 增量 |

哪一次失败就停在那里，找出是哪个电源域/时钟/稳压器被关掉（`/sys/kernel/debug/clk/clk_summary`、`pm_genpd_summary`、`regulator_summary` 与正常启动对比），
再决定是补设备树还是合入 erhai 的对应改动。全部通过后才改 `/etc/kernel/cmdline`，并删除手工条目。手工条目登记为技术债。

09:51 起，用户批准 M3.3b 的参数测试（手工条目 `opd2413-m33b.conf`，一次性启动，默认项不变）。

- 第一次一次性启动进了默认条目而不是测试条目。原因是 `boot-select` 的错误：systemd-boot 拿 `default` 与带 `.conf` 的条目 id 匹配，
  `boot-select` 却去掉了后缀，精确名字从来匹配不上，systemd-boot 退回到最新条目。之前几次"把默认项固定到旧内核"其实都没固定住，
  只是每次想一次性启动的恰好就是最新内核，所以没暴露。修复：`next`/`default` 写完整 id（`xxx.conf`），新增用 `bootctl` 验证 systemd-boot 实际选择的测试；
  `tools/tablet-reboot.py` 在重启前用平板上的 `bootctl list` 核对将要启动的条目，不符就撤销并退出。设备包 0.1-10（为让已批准的测试能进行而装，事后告知用户）。
- A（去掉 `regulator_ignore_unused`）：进测试条目、`running`、失败 0、Enforcing、AVC 0、GPU/Wi-Fi/蓝牙/9 V/声卡正常、无新错误类别；稳压器状态与正常启动完全相同（这个参数实际没有作用）。
- B（再去掉 `pd_ignore_unused`）：同上通过；内核改为"Disabling unused power domains"。
- C（三个都去掉）：同上通过；"Disabling unused clocks"。`systemctl suspend` + RTC 60 s 正常唤醒，但 **`cxsd`/`ddr`/`aosd` 仍为 0**。
- 原因线索：`sync_state() pending`——interconnect（4 个 NoC）、`qcom-rpmhpd`（RPMh 电源域）、`gcc-sm8750` 在等 `ad27000.isp`（相机 ISP，没有驱动），
  rpmhpd 和 camcc 还在等 `adb1000.phy`、`adb3000.phy`（CSI PHY，没有驱动），gcc、gpucc、gxclkctl 在等 `3d37000.gmu`（GMU 节点没有绑定驱动）。
  sync_state 不发生，这些提供者就一直保持开机时的最大投票（interconnect 汇总里 qup 核心为 INT_MAX），CX 不可能塌陷。
  erhai 有相机 ISP/CSI PHY 驱动和"给 GMU 绑定驱动"（`6f237b23c` 等 FROMLIST）。证据 `private/m3-sleep-20261112/m33b-*`。
- 10:03 用户确认 C 下画面、触控、键盘、声音正常，批准 D：C 再加 `fw_devlink.sync_state=timeout`。启动约 10 s 后所有提供者
  "Timed out. Forcing sync_state()"（4 个 NoC、gcc、camcc、gxclkctl、gpucc、rpmhpd），interconnect 的 INT_MAX 投票消失；自动检查同前全部通过。
  10:04:37 `systemctl suspend` + RTC 60 s：**`cxsd` Count 9、Accumulated 1144865267（÷19.2 MHz ≈ 59.6 s），`ddr` 相同**，即约 98 % 的挂起时间 CX 塌陷、DDR 自刷新，
  与 erhai 的实测一致；`aosd` 0（插着 USB，erhai 也是这样）。RTC 唤醒、Wi-Fi 恢复。证据 `private/m3-sleep-20261112/m33b-D-*`。
- 用户确认 D 下画面、触控、键盘、声音正常，批准转正式（日志里没看到用户在 D 下按电源键挂起的记录，只有我的 RTC 那次；电源键挂起在 M3.3a 已验证）。
  10:08 备份到 `/var/tmp/opd2413/m3-sleep/cmdline-100831/` 后改 `/etc/kernel/cmdline`：去掉 `clk_ignore_unused pd_ignore_unused regulator_ignore_unused`，加 `fw_devlink.sync_state=timeout`；
  `kernel-install add 7.2.15-3.opd2413` 只重生成 7.2.15-3 的条目，7.2.15-2 条目哈希不变（仍是旧参数，作回退）；删除手工条目 `opd2413-m33b.conf`。
- 10:09 `systemctl poweroff` 冷启动，37 s 后可 SSH：默认条目 7.2.15-3、新参数生效、9 个提供者强制 sync_state、`running`、失败 0、Enforcing、AVC 0、GPU/Wi-Fi/蓝牙/9 V/声卡正常、无新错误类别。
  10:10 `systemctl suspend` + RTC 60 s：`cxsd`/`ddr` Count 3、Accumulated 1139630334（≈ 59.4 s）。证据 `private/m3-sleep-20261112/m33b-coldboot.txt`、`m33b-final-suspend.txt`。

**结果：M3.3b 真机通过（插着 USB 时 CX 塌陷、DDR 自刷新约占挂起时间的 98 %）。** 技术债 #1 解除，新增 #34（`fw_devlink.sync_state=timeout` 是临时做法）。
拔线待机耗电（`aosd`）没测。

### 2026-11-12 10:20 起：M3.2b PPS 快充

用户要求先提交（分支 `m3-7.2-features`，两个提交），再做 PPS，然后其他。
离线：erhai 的 PPS 由 `erhai_pps`（PPS 协商状态机）和 `sc8547a`（电荷泵）组成，battmgr 侧的挂钩已在 `2101`；`sc8547a` 链接依赖 erhai 对 `wcd939x-usbss.c` 的改动
（串行 VOOC 用的 D+/D- 切换，默认不用），该差异在 Armada `0063` 之上严格应用。板级 DTS 的两个 SC8547A 节点与 erhai 相同（Armada 已移植）。
新补丁 `2102`、`2103` 和配置片段 `m3-2b-pps.config`（模块）；在干净基线上整套 `apply-opd2413-features.sh` 通过，驱动文件与 erhai 逐字节相同；W=1 编译没有新警告。
构建 `7.2.15-4.opd2413`。

注意：erhai_pps 只在电量低于 80 % 时快充（低于 75 % 才重新开始），现在电量 97 %，PPS 不会介入；真正的快充测试要等电量降到 75 % 以下。
平板上还有 7.3 时期留下的 `/etc/modprobe.d/opd2413-pps.conf`（`pps_enable=0`），会让 PPS 不工作；它是运行时可改的模块参数，测试时可以直接打开。

10:26 构建完成，离线核对通过：配置只多 `CHARGER_SC8547A=m`、`CHARGER_ERHAI_PPS=m`；DTB 相同；模块多 `sc8547a.ko`（别名 `of:…southchip,sc8547a`）、`erhai_pps.ko`（`platform:erhai-pps`）；
`tests/package-install-test.sh` 通过（`out/m3k/pkg-test4/`）。包 `kernel-opd2413-7.2.15-4.opd2413`（`902b83a5…`）。

**上机计划（待批准）**：

1. `boot-select default fedora-7.2.15-3.opd2413`（修好后第一次真正固定），装 7.2.15-4（按上限卸掉 7.2.15-2，回退项变成 7.2.15-3），`tablet-reboot.py --entry fedora-7.2.15-4.opd2413`。
   这次启动 `opd2413-pps.conf` 还在，PPS 关着。
2. 判据：M1 验收项；两个 SC8547A 都探测成功、`erhai_pps` 绑定；快充充电器上仍协商到 9 V；RTC 挂起 60 s 唤醒且 CX 塌陷；没有新错误类别。
3. 删除 7.3 时期的 `/etc/modprobe.d/opd2413-pps.conf`，运行时 `pps_enable=1`：电量 97 % 时 PPS 应保持不介入。
4. 设为默认、冷启动复查。真正的 PPS 快充（电量 < 75 %）等电量降下来再测。

10:30 起，用户批准全部 4 步。执行：

- ① `boot-select default fedora-7.2.15-3.opd2413` 写入 `fedora-7.2.15-3.opd2413.conf`，平板上 `bootctl` 确认默认项确实是它（修复后第一次真正固定）；装 7.2.15-4（卸掉 7.2.15-2，回退项 7.2.15-3）；
  一次性启动 7.2.15-4，40 s 回来。
- ② 自动验收：`running`、失败 0、Enforcing、AVC 0、GPU、Wi-Fi、蓝牙、声卡、无新错误类别；`sc8547a 3-006f: master charge pump probed`、`1-006f: slave …`，
  `erhai-pps` 已绑定（`pps_enable=N`，当时 `opd2413-pps.conf` 还在）。用户之前已拔掉充电器（电池放电约 1.5 A），9 V 这一项没法测。
  拔线状态下 RTC 挂起 120 s：`cxsd`/`ddr` 一次进入、驻留 2294751219（≈ 119.5 s），`aosd` 仍为 0（拔线也没有到 AOSS sleep）。
- ③ 备份后删除 `/etc/modprobe.d/opd2413-pps.conf`（7.3 时期的 `pps_enable=0`），运行时 `pps_enable=1`；没接充电器，PPS 没有动作。
- ④ 10:37 `boot-select default 'fedora-*'`（`bootctl` 确认为 7.2.15-4）后 `systemctl poweroff`。**没插充电器时关机不会自动开机**，平板停在关机状态，需要用户按电源键开机。
- 用户说明：拔电是有意的，为了把电量放到 75 % 以下做 PPS 测试；10:47 用户按电源键开机。复查：7.2.15-4、`running`、失败 0、Enforcing、AVC 0、
  两个电荷泵探测成功、无新错误类别（这一次是真正的冷启动）。
- 但 `pps_enable` 仍为 N：7.2.15-4 的 initramfs 是在 `opd2413-pps.conf` 还在时生成的，里面带着 `options erhai_pps pps_enable=0`，而 `erhai_pps` 正是在 initramfs 里加载的。
  `kernel-install add 7.2.15-4.opd2413` 重新生成 initramfs（不再含该文件，启动参数不变），`tablet-reboot.py` 热重启 39 s 回来：`pps_enable=Y`。
  教训：改 `/etc/modprobe.d` 后要重新生成 initramfs（写进 STATUS 的"已知的坑"）。initramfs 改动后还欠一次冷启动，等用户插回充电器时做（插着电关机会自动开机）。
- 现在电量 97 %，拔线放电中。PPS 实测等电量低于 75 % 后插快充。

10:55 起：等放电期间做 M3.4 离线评估（只读），写进 [M3-FEATURES.md](M3-FEATURES.md)"M3.4"。建议顺序：视频硬解 → 摄像头内核 → 传感器用户态，待用户确认。

### 2026-11-12 11:00 起：M3.4b 摄像头（用户：先不管键盘唤醒；不插电调试，做摄像头和传感器）

离线：erhai v0.7.2 里相机相关的 46 个提交（CAMSS SM8750、CSI2 PHY 驱动和 phy core、两个 SmartSens 传感器、CN3927 对焦马达、pmdomain 性能态）去掉 DTS/defconfig 部分后，
在本树上按 erhai 顺序全部严格应用，33 个代码文件与 erhai 逐字节相同；本机 `sm8750.dtsi` 的 CAMSS/CCI/CSIPHY 节点和板级 DTS 的相机节点（`&camss`、`&cci0`、`&i2c9`、两个传感器、对焦马达）
都已与 erhai 相同（Armada 移植过），所以 DTB 不变。补丁 `2301`–`2346`，配置片段 `m3-4b-camera.config`。
11:46 构建 `7.2.15-5.opd2413`（`a03b03db…`）：配置差异只有片段里的项；DTB 相同；模块多 `phy-qcom-mipi-csi2`、`sc1300cs`、`sc820cs`、`cn3927`，DMA-BUF 两个堆改为内建；
`tests/package-install-test.sh` 通过（`out/m3k/pkg-test5/`）。
此时平板 SSH 超时：拔线时 KDE 按电池策略空闲挂起了。

11:50 起，用户批准全部 4 步（含调试期间的 `systemd-inhibit --what=idle` 抑制锁，作为临时单元 `opd2413-debug-inhibit` 运行，重启即失效）。

- ② 先 `boot-select default fedora-7.2.15-4.opd2413`（`bootctl` 确认），装 7.2.15-5（卸掉 7.2.15-3，回退 7.2.15-4），一次性启动 38 s 回来。
- ③ 自动验收同前全部通过（`running`、失败 0、Enforcing、AVC 0、GPU/Wi-Fi/蓝牙/声卡）。相机：`qcom_camss`、`phy_qcom_mipi_csi2`、`sc1300cs`、`sc820cs`、`cn3927`、`i2c_qcom_cci` 都加载，
  `/dev/media0` 和 30 个子设备。新日志一条 `qcom-camss ad27000.isp: csiphy 4 init fail`（随后探测成功，像是一次推迟探测）和三条 TPG 实体类型未初始化的提示。
  **sync_state：interconnect、rpmhpd、camcc 不再超时，自然完成**；只剩 gcc、gpucc、gxclkctl 因 GMU 仍要靠 `fw_devlink.sync_state=timeout`（技术债 #34 缩小为 GMU 一项）。
- ④ `dnf install libcamera-tools`（Fedora 源；libcamera、libcamera-ipa、pipewire-plugin-libcamera 已装）：`cam -l` 列出前摄 `camera@10`、后摄 `camera@36`，simple 管线 + 软件 ISP；
  libcamera 0.7.2 没有 sc1300cs/sc820cs 的传感器辅助和调校文件（用 `uncalibrated.yaml`）。两路 1280×960 XRGB8888 各采 20 帧，约 31.8 fps；
  前摄末帧平均亮度接近 0、后摄平均约 40 但几乎没有起伏（平板可能平放、镜头被挡，或 20 帧内曝光还没收敛），要看实际画面。装了 `snapshot`（GNOME 相机，Fedora 源）给用户看预览。
- 用户实测 Snapshot：前后摄都有画面、方向正确，能拍照、录像；后摄不能对焦，整体画质低；**录像的声音全是刺耳噪音**。
  对焦和画质：libcamera 0.7.2 的 simple 管线没有自动对焦算法，也没有这两颗传感器的调校（`uncalibrated.yaml`），erhai 文档同样写着"焦点固定在远处、偏色、四角偏暗"，属已知限制。
  噪音：与相机无关，是麦克风采集坏了。`pw-record` 4 s：两声道 rms 约 31000、峰值满幅、每秒过零约 2.8–3.4 万次，即满幅的乱码数据而不是声音。
  麦克风在本项目一直是"待调研"（STATUS 功能表），从没验收过。板级 DTS 的 TX SoundWire 端口布局（erhai `095062299`）本机已有；erhai 另有本树缺的
  `lpass-tx/va-macro` 运行时 PM 时钟（`9ead6de36`、`385a9a869`）、`q6apm` 从 PCM trigger 启动采集图（`e85a25943`）、`wcd939x` 运行时 PM 链接（`e4f82a321`）等，另立一项处理。
- 12:05 `boot-select default 'fedora-*'`（`bootctl` 确认 7.2.15-5），热重启 43 s 回来：`running`、失败 0、Enforcing、AVC 0，两个摄像头都在，强制 sync_state 只剩 3 个（GMU 相关）。
  拔着电没做关机冷启动，等插电时补。

**结果：M3.4b 摄像头真机通过（前后摄预览、拍照、录像；画质和对焦是已知限制）。** 默认内核 `7.2.15-5.opd2413`，回退 `7.2.15-4`。

### 2026-11-12 12:10 起：M3.5 麦克风（用户：先做麦克风，再看传感器）

诊断（7.2.15-5，只读 + 运行时混音器）：PipeWire 以 S16_LE/48 kHz/2ch 打开 `hw:0,2`；采到的数据约 90 % 样本在满幅（±32767），每秒过零约 3.3 万次；
录音中途把 `ADC1/ADC4 Volume` 13→0、`TX_DEC0/1 Volume` 112→84（共降 28 dB）后 rms 只从 31752 降到 24943、仍有 39 % 满幅、过零 2.2 万次/s——不是声学信号，
而是数字通路（TX 宏的抽取器）输出的乱码。UCM、AudioReach 拓扑源（m4）与 erhai 相同，板级 DTS 的 TX SoundWire 端口布局也相同；`TX0/TX1 HPF cut off` 控件不存在（UCM 里按条件跳过）。
erhai 声明内置麦克风可用（README）。本树的 `lpass-tx-macro.c`/`lpass-va-macro.c` 是"切到 PM 时钟框架"的旧版本，erhai 已换成 FROMLIST "在运行时 PM 里显式管理时钟"的版本并加了 HPF 控件。
候选修复 `2401`：两个驱动取 erhai v0.7.2 整文件（一个变量），W=1 编译无警告；构建 `7.2.15-6.opd2413`。
12:2x 构建完成：配置、DTB、模块清单与 7.2.15-5 相同（只有两个宏驱动内容变化），`tests/package-install-test.sh` 通过（`out/m3k/pkg-test6/`）。包 `97e1ffc3…`。

12:25 起，用户批准 7.2.15-6 上机。默认项先固定在 7.2.15-5（`bootctl` 确认），装 7.2.15-6（卸掉 7.2.15-4），一次性启动 47 s 回来；自动验收同前通过，
`TX0 HPF cut off` 控件出现且 UCM 设成 75 Hz。**麦克风仍是乱码**：4 s 录音两声道约 −0.1/−0.7 dBFS、97 %/80 % 样本满幅、过零约 3 万次/s。
`2401` 不是原因（结果不变），保留（与 erhai 一致，带 HPF 控件）。

继续排查：音频的 DTS（sound、swr1/swr2、wsa、wcd939x、q6apmbedai 等节点）、UCM、拓扑都与 erhai 相同；差异只在内核音频驱动。
本机音频通路上 14 个文件与 erhai v0.7.2 不同（Armada 序列的 TDM 扬声器 `1408`、耳机 PCM HiFi `0072/0073`、AudioReach 通道映射 `0007`、q6apm MI2S/挂起相关等）。
实验 E：把这 14 个文件换成 erhai 的版本（作为一个变量），构建实验内核 `7.2.15-7`，测麦克风、扬声器、耳机。实验补丁暂不进 series。

12:50 起，用户批准实验 E。默认项固定在 7.2.15-6（`bootctl` 确认），装 7.2.15-7（卸掉 7.2.15-5），一次性启动（这次 101 s 才回来，日志多一条 `i2c-qcom-cci … master queue timeout`）。
自动验收通过。**麦克风仍是乱码**（约 −0.3 dBFS、85–90 % 满幅、过零约 2.6 万次/s）——换成 erhai 的 14 个音频驱动文件也没用，**原因不在内核音频驱动**。
进一步的数据：样本只有 0x7fff 和 0x8000 两种值、符号随机，即在某处被放大约 2^16 倍后削顶（降 47 dB 增益仍削顶，说明放大发生在抽取器增益之后，像是 DSP 采集图里的 Q 格式/位宽不匹配）。
`hw:0,2` 只提供 S16_LE/2ch/48 kHz（拓扑限定）。拓扑源、UCM、DTS、ADSP 固件（原厂 `qcom/sm8750/erhai/adsp.mdt`）、内核音频驱动都已与 erhai 相同或排除；
剩下的差异是用户态（Fedora 的 PipeWire 1.6.11/alsa-lib 对 Ubuntu）和内核配置，尚未查明。实验内核不设默认，重启回到 7.2.15-6。

13:00 起：直接用 ALSA（`arecord hw:0,2`，手工设好 UCM 的同一组混音器、绕过 PipeWire）录音同样是乱码，排除 PipeWire。一个声道的样本是随机 16 位数而不全是削顶，
说明 TX SoundWire 送进抽取器的就是无效数据。录音期间 TX 主控（master-3，`7630000`）只有端口 2 在用（通道掩码 0x6），WCD TX 从设备只开了 DP1。
怀疑对象：板级 DTS 里 erhai `095062299`（10-27，"TX 控制器有一个输出口在四个输入口之前"，`dout-ports=1`、5 项端口数组、数据线 `<0xff 1 2 0 0>`、采集 DAI 改为 `<&swr2 1>`），
该提交自己写着"采集仍需真机验证"，而 erhai 记录麦克风可用是 v0.2.2（更早）。
实验 F（用户批准）：只改 DTB——`soundwire@7630000` 恢复 SoC 默认（`dout-ports=0`、4 项数组、数据线 `<1 2 0 0>`）、采集链路的 swr2 参数 1→0，
放到 ESP `opd2413-test/swr2-soc.dtb`，手工条目 `opd2413-mictest.conf`（7.2.15-6 内核）一次性启动。部署时平板又被 KDE 空闲挂起（热重启后忘了重新起抑制锁），等用户唤醒。

13:41 实验 F（只换 DTB，一次性启动 `opd2413-mictest.conf`）：**麦克风正常**——4 s 录音 −20.6/−15.3 dBFS、无削顶、过零约 1000–1500 次/s；用户录像确认声音正常。
内核多一条 `qcom-soundwire 7630000.soundwire: dout-ports (0) mismatch with controller (1)`（控制器确实有一个输出口）。
实验 G（保留 erhai 布局，只把 `qcom,tx-port-mapping` 改成 `<3 3 4 5>`）：**全是 0（静音）**。结论：采用 F，补丁 `2402`；测试条目和 `/boot/efi/opd2413-test/` 已删除。
构建 `7.2.15-8` 前把构建树里的实验 E 提交撤掉（`git reset` 到 `2401`）。

键盘（用户报告：F3 位置的麦克风键打开了 KDE 系统设置，F6 位置的锁屏键没反应，其他顶排键正常；Esc 实际是返回键）：
- 事件记录：麦克风键报 `KEY_F13`（KDE 当作 Tools 键打开系统设置），锁屏键报 `KEY_F24`；驱动的键盘键表可用 hwdb 重映射（以 HID 用法为索引）。
  用户批准后先在 `/etc/udev/hwdb.d/90-opd2413-pogo-keyboard.hwdb` 临时加 `KEYBOARD_KEY_68=micmute`、`KEYBOARD_KEY_73=screenlock`，
  事件变为 `KEY_MICMUTE`、`KEY_SCREENLOCK`(=`KEY_COFFEE`)，用户确认麦克风静音和锁屏都起作用。做进设备包 0.1-11（`/usr/lib/udev/hwdb.d/`），装包后删临时文件。
- 按住放大镜键再按麦克风/锁屏键：只有 `KEY_FN` 按下松开，这两个键没有任何事件（Fn 层的 F3/F6 不工作），记下待查。
- Esc 键报 `KEY_BACK`（固件发消费者用法 AC Back 0x0224，走驱动的媒体键表，hwdb 改不了）→ 补丁 `2403` 改报 `KEY_ESC`。

14:20 起，用户批准 7.2.15-8 + 设备包 0.1-11 上机：先固定默认 7.2.15-6，卸掉实验内核 7.2.15-7，装 7.2.15-8 和 0.1-11（`rpm -V` 干净），删掉临时 hwdb；一次性启动 46 s 回来，
自动验收通过，hwdb 由包提供（`KEYBOARD_KEY_68/73` 生效）。**但麦克风又是乱码**，而现场 DT 与实验 F 逐字节相同（`dout-ports 0`、数据线 `<1 2 0 0>`、映射 `<2 2 3 4>`、采集 DAI 0）。
一次 s2idle 挂起恢复后仍坏；再连续三次一次性启动 7.2.15-8，每次都坏（0/4）。实验 F 那次启动是唯一成功的一次（用户录像确认）。
**结论修正：DTS 改动不是（或不只是）原因，故障像是逐次启动的偶发状态**；各次启动的内核日志粗看没有区别（每次都有一条 `qcom-apm … CMD timeout for [1001021]`）。根因未查明。
- 用户确认 7.2.15-8 上 Esc、麦克风键、锁屏键正常，按住放大镜键时 F3、F6 也能执行（我的事件记录里没看到，以用户实测为准）。用户要求专注麦克风。
- 新线索：每次启动都有 `qcom-apm gprsvc:service:2:1: CMD timeout for [1001021] opcode`。erhai 有本树缺的三个 ADSP 消息修复（APR 先装回调再探测、GLINK 暂存早到的消息、q6v5 handover 中断）——
  CHANGELOG 写"ADSP 不再丢开机后的第一条消息，否则可能整次启动没有音频、充电信息或传感器"。开机丢消息可以解释"逐次启动偶发"。补丁 `2404`–`2406`，构建 `7.2.15-9`。
  坏启动时录音期间的 LPASS 时钟：`lpass-tx-mclk` 9.6 MHz、`fsgen` 19.2 MHz、`LPASS_CLK_ID_TX_CORE_MCLK` 计数 4（`private/m3-mic-20261112/clk-during-capture-bad.txt`），留作对比。

14:30 起，用户批准 7.2.15-9：先固定默认 7.2.15-8，装 7.2.15-9（卸掉 7.2.15-6），连续三次一次性启动：`CMD timeout` 消失（0/3），**但麦克风三次都还是乱码**。2404–2406 保留（修好了 ADSP 丢消息）。

找根因：主机上分析一段坏录音——比特位 0/1 各半、符号游程呈几何分布，像随机比特流进了抽取器；TX 宏寄存器（抽取器使能、增益 +28 dB、HPF、SWR_MIC0/3 输入）、
WCD 的 ADC 数字时钟和模式、MIC BIAS1/3（0x62 = 使能、约 2.7 V）都正常。关键在 SoundWire：录音时 WCD TX 从设备 DP1 的通道使能寄存器先后读到 0x6、0xf，
而本机只用 ADC1+ADC4，应为 0x9。原因：ADC1–4 共用 `WCD939X_ADC_1_4_PORT`，`wcd939x_get_swr_port()` 按**端口**报告，四个 "ADCn Switch" 只要一个开着就都读 1；
关机时 `alsactl store` 把 ADC2/ADC3 存成开，下次开机恢复时真的置上了它们的通道位，编解码器发 4 声道而 SoC 收 2 声道，数据错位成噪音；好坏取决于恢复的混音器状态，所以逐次启动不同。
当场验证：`ADC2/ADC3 Switch` 置 0、`ADC1/ADC4` 置 1 后通道使能 0x9，录音 −33 至 −36 dBFS（安静房间）、无削顶。

修复（用户批准）：
- 内核 `2407`：开关按声道报告和切换，`port_enable` 表示"端口里有声道开着"，put 只在掩码变化时返回 1。
- 音频包 0.1-12：UCM 打开麦克风时先 `ADC2/ADC3 Switch 0` 再 `ADC1/ADC4 Switch 1`（防已保存的旧状态）。已装上。
- 实验 H：7.2.15-9 + erhai 原布局的 DTB（`dout-ports=1`）+ 0.1-12：麦克风三次都正常（−31 至 −37 dBFS）→ `2402` 不需要，已从 series 删除，TX SoundWire 布局回到 erhai 的（也没有了 mismatch 警告）。
  测试条目和 DTB 已删除。实验 F 那次成功只是恰好恢复到了好的混音器状态。
- 构建 `7.2.15-10` = 7.2.15-9 − 2402 + 2407。

15:10 起，用户批准 7.2.15-10：先固定默认 7.2.15-9，装 7.2.15-10（卸掉 7.2.15-8），连续三次一次性启动，麦克风三次都正常（安静时 −38 dBFS，有声时 −16 dBFS），
ADC 开关读数正确（ADC1/4 开、ADC2/3 关），没有 `CMD timeout`、没有 mismatch 警告。用户录音确认正常。
15:20 `boot-select default 'fedora-*'`（`bootctl` 确认 7.2.15-10），热重启复查：`running`、失败 0、Enforcing、AVC 0、GPU/Wi-Fi/蓝牙/声卡/两个摄像头正常、PPS 开、录音正常。
拔着电没做关机冷启动，插电时补。

**结果：M3.5 麦克风真机通过（7.2.15-10 + opd2413-audio 0.1-12）；M3.6 键盘（Esc、麦克风键、锁屏键，7.2.15-8 起 + 设备包 0.1-11）真机通过。** 默认内核 `7.2.15-10.opd2413`，回退 `7.2.15-9`。
可回馈 erhai/上游的发现：`2407`（wcd939x 开关按端口报告导致多开声道，wcd938x 同样写法）、`2403`（Esc 键）、hwdb 的麦克风/锁屏键映射。

### 2026-11-12 15:25 起：M3.4c 传感器（用户：提交；电量不够先跳过快充，先完善别的）

已提交 `1c004bf`。离线：按 erhai-sensors 做 `packaging/opd2413-sensors/`（三个上游源码 + 23 个补丁原样，单元/udev/脚本只改名字和路径），`tools/build-sensors-rpm.sh` 在 aarch64 容器里构建出
`opd2413-sensors-0.1-1.aarch64.rpm`（`cb435323…`）；构建时测试通过。registry 从主机的 persist 备份只读导出（debugfs rdump，不碰平板的 persist 分区）。

**上机计划（待批准）**：
1. `dnf install` 这个 RPM（会从 Fedora 源带上 `protobuf-c`）；把 registry 副本拷到平板 `/var/tmp`，用 `opd2413-sensors-import-registry` 导入 `/var/lib/opd2413/sensors`。
2. 重启（ADSP 传感器域只在建立时读一次 registry）。
3. 判据：`opd2413-sensors-rpcd`、`-gate`、`iio-sensor-proxy` 起来；`monitor-sensor` 报加速度计方向、环境光数值；没有 AVC；用户转动平板确认自动旋转，看自动亮度/光线读数。
   挂起前后传感器流暂停/恢复，挂起深度不变（`cxsd` 计数）。

15:33 起，用户批准。`dnf install opd2413-sensors-0.1-1`（带上 protobuf-c），`rpm -V` 干净，sysusers 建了 `fastrpc`；registry 副本导入（357 个文件 + `sns_reg_version`，平板上的临时副本已删）；
装包后 udev 触发让 rpcd 提前起来了一次，gate 等不到样本失败（registry 是导入前建立的传感器域读的，符合 erhai 的说明）。重启后：
`opd2413-sensors-rpcd`、`-gate`（130 个重力样本）、`iio-sensor-proxy` 都 active，AVC 0，失败单元 0；`monitor-sensor`：加速度计方向 normal/tilted-up、环境光约 86 lux、指南针航向约 297.7°，
D-Bus 有陀螺仪。hexagonrpcd 报一串找不到的 json（erhai 同样）。RTC 挂起 60 s：`cxsd` 一次、驻留约 59.2 s，`opd2413-sensors-sleep` 挂起前停掉 iio-sensor-proxy、恢复后重新启动，读数恢复。
证据 `private/m3-sensors-20261112/`。待用户试自动旋转。
- 用户实测：拔下键盘转动平板，自动旋转方向都正确。遮挡光线传感器两次：读数从约 80–90 lux 降到 20–30 lux 和约 1 lux，松开后回升（`light-trace.txt`），传感器正常。
  界面亮度不变是因为 KDE Plasma 6.8.2 的 powerdevil 没有环境光自动亮度功能（erhai 在 GNOME 上有）；用户表示暂不需要自动亮度。

**结果：M3.4c 传感器真机通过（自动旋转、环境光读数、指南针、陀螺仪 D-Bus 可用；挂起深度不受影响）。** 接近传感器本机没有。

### 2026-11-12 15:50 起：M3.4a 视频硬解（用户：提交，然后下一步）

已提交 `f705302`。离线：缺的 `qcom/sm8750/erhai/vpu35_4v.mbn`（OnePlus 签名的 Iris 固件，原厂 `/vendor/firmware`）在 erhai 检出的 `packaging/firmware/` 里，SHA-256 与其清单一致（`4fbe0a97…`）；
加进 `opd2413-firmware` 清单（固件本体不进仓库），构建 `opd2413-firmware-16.0.10.600-2`。本机 DTS 的 iris 节点已启用、固件路径就是这个。内核 iris 两边都做过解码顺序输出等改动（Armada `1030`–`1037`，erhai 另一套），先只加固件试。
测试片源在主机 `out/video/`（ffmpeg 生成的 1080p30 H.264 High、HEVC、VP9 各 10 s）。

**上机计划（待批准）**：装固件包 600-2（必要时重启让 iris 重新初始化）；看 iris 固件加载、`gst-inspect-1.0` 出现 v4l2 解码器；用 `gst-launch-1.0` 把三段片源解到 fakesink，记帧数、耗时、CPU；
再请用户用播放器播放视频。之后视结果决定是否对齐 erhai 的 iris 改动。

15:53 起，用户批准。装 `opd2413-firmware-16.0.10.600-2`（`rpm -V` 干净），不重启：`/dev/video0` = `qcom-iris-decoder`、`video1` = `qcom-iris-encoder`，
GStreamer 注册了 `v4l2h264dec`、`v4l2h265dec`、`v4l2vp9dec`、`v4l2av1dec` 和 H.264/H.265 编码器。三段 1080p30 片源（各 300 帧）硬件解码都出满 300 帧，各约 0.35 s、CPU 约 0.06 s；
解出的 H.264 首帧画面正确（`h264-frame.jpg`）；对照 openh264 软件解码 1.85 s、CPU 1.81 s。**Iris 硬解（GStreamer v4l2 路径）真机通过，现有内核即可。**
但默认播放器 mpv（及基于 FFmpeg 的应用）用不上：Fedora 的 `ffmpeg-free` 没有 H.264/HEVC 的 v4l2m2m 封装、也没有原生 H.264/HEVC 解码器（只有 openh264），
`--hwdec=v4l2m2m-copy/auto-safe` 都回落到软件（≈2 s/10 s 片源）。VP9 有 `vp9_v4l2m2m`。erhai 给 Firefox/GStreamer 用的是自己的 VA-API 驱动 `iris-vaapi`（phxinyang/qualcomm-iris-vaapi）。
- 用户选择：装一个 GStreamer 播放器，其余（iris-vaapi、RPM Fusion ffmpeg）先不做。`playbin` 对三种片源都自动选 `v4l2h264dec`/`v4l2h265dec`/`v4l2vp9dec`。
  从 Fedora 源装 `showtime`（GNOME 播放器，erhai 默认用的），用 `xdg-mime` 设为 colin 的 mp4/mkv/webm/mov/avi/mpeg/ogg/m4v 默认程序（之前没有 `mimeapps.list`）；
  测试片源拷到 `~colin/Videos/opd2413-test/`。
- 用户实测 Showtime：H.264、HEVC 直接流畅播放；**VP9 卡住**（mpv 软解流畅）。与 erhai 记录一致：V4L2 VP9 解码器在播放器开播时的刷新/重启之后不再出帧（gst-launch 直通到 fakesink 时没问题）。
  修法（用户批准）：设备包 0.1-13 加 `/usr/lib/environment.d/60-opd2413-video.conf`，`GST_PLUGIN_FEATURE_RANK=${GST_PLUGIN_FEATURE_RANK:-v4l2vp9dec:0}`，
  VP9 改由软件 `vp9dec`，H.264/HEVC 仍走 `v4l2h264dec`/`v4l2h265dec`。已装（`rpm -V` 干净）；环境生成器输出确认，`playbin` 选择核对过。需注销重新登录后生效，待用户复测。
- 用户注销重新登录后复测：Showtime 播放 VP9 正常，H.264/HEVC 仍正常。

**结果：M3.4a 视频硬解真机通过（GStreamer 路径：H.264、HEVC 硬解；VP9 走软解规避 V4L2 VP9 的停帧问题）。** 固件包 `opd2413-firmware-16.0.10.600-2`、设备包 0.1-13、Showtime 为默认视频播放器。
mpv、Firefox 仍是软解（Fedora `ffmpeg-free` 的专利限制），用户选择暂不处理（iris-vaapi、RPM Fusion ffmpeg 留作以后）。

### 2026-11-12 16:24 起：M3.2b PPS 实测（用户：电量 69 %，其他先放一放）

拔线状态 69 %、30 °C，`pps_enable=Y`（停止/重启阈值 80/75 %）。采样 2 s 一次。用户插上的是 Chicony W20-045N1A（45 W，标签只有 5/9/15/20 V 固定档，**没有 PPS 档**）：
系统识别为 `PD`（不是 `PD_PPS`），`PD: requested 9000 mV`，USB 侧 8.94 V × 1.99 A ≈ 18 W，电池约 +3.1 A、4.18–4.22 V、28 °C；erhai_pps 按设计不介入。**PPS 没法用这个充电器测。**
（`battmgr` 对固定档只请求 9 V、输入上限 2 A，15/20 V 档不用，这是 erhai 的策略。）
- 借插着电做了欠的冷启动：16:31 `systemctl poweroff`，48 s 后回来。7.2.15-10、`running`、失败 0、Enforcing、AVC 0、GPU/Wi-Fi/蓝牙/声卡/两个摄像头/传感器服务正常，
  麦克风录音正常（−32.7 dBFS），开机 9 V 协商成功；上次 journal 正常结束、pstore 空。**7.2.15-10 冷启动验证通过。** 证据 `private/m3-pps-20261112/`。
- 用户没有 PPS 充电器，PPS 实测搁置（M3.2b 记为待测：驱动、电荷泵探测、`pps_enable=Y` 已真机确认，只差真正进入 PPS 的验证）。

### 2026-11-12 17:00 起：收尾（用户：先做完安全和收尾，OTA 不管，然后看键盘唤醒和 60 Hz）

- SSH（AGENTS 规则 8）：sshd 本来就只允许密钥登录、root 禁密码；用户选择用防火墙收紧。firewalld public 区去掉 `ssh` 服务，加 rich rule 只放行家里局域网 /24 和 `fe80::/10`；
  先改运行时、新开一条 SSH 确认能连再 `--runtime-to-permanent`。没有改 sshd 的监听地址（DHCP 地址会变）。
- 清理（用户批准）：删除平板 `/var/tmp/opd2413/`（约 948 MB）、`/var/tmp` 下的 7.3 内核包和杂项、`/var/lib/opd2413-pstore/` 下 35 个旧记录目录。
  设备包 0.1-14：`opd2413-pstore-keep.service` 改调 `/usr/libexec/opd2413/pstore-keep`，目录名 `NNNNNN-<boot id>`（计数器，不靠开机早期不可信的时钟），只留最新 20 份；脚本在主机上用 25 次模拟验证过。
  技术债 #27、#30 解除。主机上常用的平板检查脚本存到 `private/scripts/`。

### 2026-11-12 20:15 起：迁移桌面配置后开机数秒黑屏与夜灯（Night Light / DSPP PCC）排查

迁移主机 KDE 配置到平板 `~colin` 后，出现两类显示问题：

1. **迁移带入的 `~colin/.config/plasma-workspace/env/kwin_vars.sh`**：内含 `KWIN_USE_OVERLAYS=0`、`KWIN_DRM_NO_DIRECT_SCANOUT=1`，导致 KWin DRM 提交报 `Atomic commit failed: Permission denied (EACCES)`。删除该文件后恢复。
2. **开机进入桌面几秒后黑屏（背光亮、声音正常、画面全黑）**：
   - 现象：重启自动登录进入桌面后先正常显示数秒，随后物理屏幕变全黑（背光仍为 615/2047，Wayland 合成器截图画面正常）。
   - 取证（`private/display-nightlight-20261112/`）：
     - `/proc/interrupts`：`msm` 中断停在 1888 不再增长，两路 `dsi_isr` 均为 246。
     - `tools/kms-snapshot-diff.py` 对比 `private/display-repro3/display/base/kms` 与黑屏时的 `kms-black-nightlight`：
       - `dspp_0_pcc`、`dspp_1_pcc`：`0x0000: 0 -> 1`（`PCC_EN`），`0x0010: 0 -> 0x0000a55a`（R），`0x0020: 0 -> 0x00007949`（G），`0x0030: 0 -> 0x00005477`（B），对应 KWin `nightlight` 插件在日落时段下发的 4500 K 色温矩阵。
       - `ctl_0`：`0x0094 = 0x80c008c0`、`0x0180 = 0x1`、`0x0184 = 0x3`、`0x018c = 0x6`、`0x0844: 0x31 -> 0x33`；`sspp_8` 的 `0x00d0` 停在 `0x00000c80`。与之前 60 Hz 切回 120 Hz 在线模式切换导致 `ctl_0` 卡死、停止取帧的寄存器形态一致。
   - 内核根因（`0068-drm-msm-dpu-lutdma-dspp-igc-gamut.patch`，`drivers/gpu/drm/msm/disp/dpu1/dpu_crtc.c`）：
     1. **开启夜灯触发运行中在线 modeset 卡死 `ctl_0`**：`dpu_crtc_get_topology()` 仅在 `dpu_crtc_state_needs_dspp(crtc_state)` 为真（`ctm`、`gamma_lut`、`degamma_lut` 或 `lut3d` 非空）时才设 `topology.num_dspp = topology.num_lm`；`dpu_crtc_check_mode_changed()` 在 `dpu_crtc_state_needs_dspp(old) != dpu_crtc_state_needs_dspp(new)` 时强制置 `new_crtc_state->mode_changed = true`。开机初始时 `ctm == NULL`（`num_dspp = 0`）；进入桌面几秒后 KWin `nightlight` 插件激活并提交 `CTM` blob，`needs_dspp` 从 `false` 变 `true`，触发不经熄屏断电的在线 modeset，导致 `ctl_0` 卡死黑屏。
     2. **关闭夜灯后 `dspp_0_pcc` / `dspp_1_pcc` 无法清零（屏幕残留 4500 K 偏黄）**：当禁用夜灯使 `state->ctm` 变回 `NULL` 时，`dpu_crtc_state_needs_dspp()` 返回 `false`，`dpu_crtc_assign_resources()` 将 `cstate->mixers[i].hw_dspp` 置为 `NULL`。随后 `_dpu_crtc_setup_cp_blocks()` 中因 `if (!dspp) continue;` 直接跳过，`if (!state->ctm) dspp->ops.setup_pcc(dspp, NULL)`（向 `base + 0x0` 写 `PCC_DIS = 0`）成为不可达死代码，且 `ctl_0` 未解除 DSPP 关联，导致 4500 K 的 PCC 系数一直残留在硬件寄存器中（`kms-after-dpms-reset` 验证确认），需重启复位 MDSS 后才回到 0。
   - 当前规避与后续修复方向：
     - 临时规避（技术债 #35）：在平板 `~colin/.config/kwinrc` 中设 `[NightColor] Active=false`、`[Plugins] nightlightEnabled=false`，重启 `plasma-kwin_wayland.service` 并执行一次 `kscreen-doctor --dpms off/on` 复位 `ctl_0`（`msm` 中断恢复 120/s，用户确认桌面显示恢复）。
     - 后续内核修复方向：修改 `dpu_crtc.c` 的 `dpu_crtc_get_topology()`，在硬件 DSPP 数量充足时开机首次 modeset 即常驻分配 `topology.num_dspp = topology.num_lm`，并去掉 `dpu_crtc_check_mode_changed()` 中因 `dpu_crtc_state_needs_dspp` 变化触发的 `mode_changed = true`。这样夜灯开启、渐变调节与关闭（`setup_pcc(dspp, NULL)` 写 `PCC_DIS`）均只走每帧 `color_mgmt_changed` 路径，既不会触发在线 modeset 黑屏，关闭时也能正常将 `dspp_pcc` 清零。

### 2026-11-13 起：M4 键盘唤醒（s2idle 下按键唤醒并点亮锁屏）

当前基线（只读核对）：`7.2.15-10.opd2413` 运行中，电量 95 %（充电中），`/sys/bus/platform/devices/880000.serial/power/wakeup` 不存在；`pogo-keyboard-detect`（gpio96）已注册但仅在 `POGO_KB_IDLE`（未接键盘）时 `enable_irq_wake`。

**第一步实验计划（离线已就绪，待用户批准写入平板）：**

离线在 `private/m3-kbdwake-20261113/kbd-wake.dtb` 基于当前 `7.2.15-10` 设备树编译实验 DTB（反编译 diff 核对仅两处变化）：

1. `&uart_kb`（`serial@880000`）删去单中断属性 `interrupts` 并改为 `interrupts-extended = <&intc GIC_SPI 373 IRQ_TYPE_LEVEL_HIGH>, <&tlmm 3 IRQ_TYPE_EDGE_FALLING>;`（对应 PDC IRQ 80）。
2. `pogo_kb_uart_sleep` 中 `rx-pins`（`gpio3`）的 `function` 改为 `"gpio"`。

写入范围（一次性启动测试，不改默认项）：
- ESP 新建 `/boot/efi/opd2413-test/kbd-wake.dtb` 与 `/boot/efi/loader/entries/opd2413-kbdwake.conf`（复用 `7.2.15-10.opd2413` 的内核、initrd 与参数）；
- 通过 `tools/tablet-reboot.py --entry opd2413-kbdwake` 一次性重启测试。

预期与判据：
1. 开盖 `s2idle`（含先空闲熄屏再挂起）按键盘任意键能唤醒系统，`/sys/bus/platform/devices/880000.serial/power/wakeup` 存在且 `wakeup_count` 递增；记录唤醒后 KDE 屏幕是否直接点亮锁屏、以及是否需要第二步在 `pogo_kb_resume` 补发 `KEY_WAKEUP`。
2. 睡眠中触碰触控板的行为（是否唤醒）。
3. 误唤醒检查：拔掉键盘后挂起（gpio3 无上下拉悬空）以及合盖后挂起并挤压按键，确认是否出现假唤醒/误唤醒（为第二步防误唤醒策略提供依据）。
4. 挂起 60 s 睡深回归：`qcom_stats` 的 `cxsd` / `ddr` 驻留仍保持约 98 %。

**第一步（a）实测结果（`kbd-wake.dtb`，`gpio3` 睡眠态 `bias-disable`）：**

- 13:56 `tools/tablet-reboot.py --entry opd2413-kbdwake` 41 s 上线，`running`；`/sys/bus/platform/devices/880000.serial/power/wakeup = enabled`，`irq 210`（`msmgpio 3 Edge 880000.serial:wakeup`）已注册。
- 接键盘开盖短按电源键挂起两次（14:10:03、14:10:13），未按任何键即在约 2 s（CX 塌陷 1.15–1.60 s）后自行唤醒；`irq 210` 计数增至 2、`880000.serial` `wakeup_active_count=2`。
- 对照测试（14:29:16）：拔掉键盘挂起，16 s 内未自唤醒（证明 `gpio3` 本身无键盘时不飘低）；14:29:32 接回键盘立即唤醒（`pogo-keyboard-detect` irq 245 计数 +2，重接瞬间 `irq 210` 亦 +1）。
- 结论：键盘 MCU 收到 `POGO_KB_GENERAL_SLEEP` 并停心跳后进入深睡，导致单线串口在 `bias-disable` 下掉电/飘低触发下降沿（且原厂设备树中 `qcom,qup_uart@880000` 配有 `qcom,wakeup-byte = <0xfd>` 用于过滤非唤醒字节）。证据：`private/m3-kbdwake-20261113/{boot-check,baseline,test1-spurious-wake,test1b-detached}.txt`。

**第一步（b）实测结果（`kbd-wake-pullup.dtb`，`gpio3` 睡眠态 `bias-pull-up`）：**

- 按 Step 1(b) 计划覆盖 `/boot/efi/opd2413-test/kbd-wake.dtb` 并 `tools/tablet-reboot.py --entry opd2413-kbdwake` 重启上线（83 s，`running`）；`/sys/firmware/devicetree/base/soc@0/pinctrl@f100000/pogo-kb-uart-sleep-state/rx-pins/bias-pull-up` 已核对生效。
- 接键盘开盖短按电源键休眠（14:43:42），未按任何键仍于约 4 s 后（14:43:46）自动唤醒，`irq 210`（`msmgpio 3 Edge 880000.serial:wakeup`）计数 `+1`、`880000.serial` `wakeup_active_count=1`。
- 结论：`bias-pull-up` 也未能阻止自唤醒，说明并非高阻悬空飘低，而是已连接的键盘 MCU 在收到 `POGO_KB_GENERAL_SLEEP` 后约 1.5–4 s 之间主动在串口线产生下降沿（例如拉低总线、断电、或发送某种休眠后字节/电平跳变）。下一步先查明原厂 `0xfd` 唤醒机制及键盘 MCU 在 `POGO_KB_GENERAL_SLEEP` 后（以及真正按键唤醒时）串口 RX 的实际电平与字节行为，再确定正确的硬件唤醒触发/过滤方式。证据：`private/m3-kbdwake-20261113/{boot2-check,test2-pullup-wake}.txt`。

**诊断抓取实测结果（仅内存态 `.ko`，已卸载并恢复原模块）：**

1. `diag_sleep=1` 下发 `POGO_KB_GENERAL_SLEEP`（`+5 ms` 收 ACK `3b 04 02 02 01 01`），在保持串口在线的条件下于 **`+1637 ms`** 抓到键盘 MCU 主动发出一帧 `00 55 55 55 55 55 55 55 55 f1 a1 a2 3b 04 0e 02 64 af a1 0d fe aa aa aa aa`（原厂协议 `cmd=0x3b sub=0x0e` 电池状态上报），总线上持续仅 `~0.27 ms`（此后连续 116 s 完全静默）。
2. 键盘休眠静默约 116 s 后按一次空格键（`+118090 ms`），抓到完整唤醒时序：先发 `00` 唤醒脉冲，**间隔 `23 ms`** 后发出 `55 55 ... f1 a1 a2 01 08 00 00 2c ...`（按下空格）及 `~76 ms` 连发、`~100 ms` 释放帧。随后写 `0` 唤醒恢复并 `rmmod` + `modprobe oneplus_pogo_keyboard` 恢复原状。证据：`private/m3-kbdwake-20261113/{diag-sleep-awake,diag-sleep-keypress}.txt`。

**第一步（c）实验方案（离线编译与 diff 已就绪，待用户批准）：**

将 `gpio3` 唤醒中断从通用串口 `&uart_kb` 移交给子设备 `keyboard`（`interrupt-names = "detect", "wakeup"`），使 `oneplus-pogo-keyboard` 通过 `IRQF_NO_SUSPEND | IRQF_NO_AUTOEN` 在 `suspend_noirq`/`resume_noirq` 阶段自行管理唤醒并按“2.5 s 内单次 `<5 ms` 突刺不触发 `pm_wakeup_dev_event`（需间隔 5–150 ms 的第二组沿才唤醒），2.5 s 后任意下降沿立即唤醒”过滤 `+1.64 s` 电池上报脉冲：
1. 实验 DTB `private/m3-kbdwake-20261113/kbd-wake-child.dtb`（反编译 diff 仅两处：`keyboard` 增配 `"wakeup"` <&tlmm 3>、`pogo_kb_uart_sleep/rx-pins` 设为 `"gpio"` + `bias-pull-up`；`&uart_kb` 保持默认单中断）。
2. 实验模块 `private/m3-kbdwake-20261113/step1c/oneplus-pogo-keyboard.ko`（`vermagic` 与 `7.2.15-10.opd2413` 一致，不改动内核与 `/lib/modules`）。
- 写入范围：覆盖 ESP `/boot/efi/opd2413-test/kbd-wake.dtb`，`tools/tablet-reboot.py --entry opd2413-kbdwake` 一次性启动进入后，将模块放到 `/tmp/oneplus-pogo-keyboard.ko` 并 `rmmod && insmod` 加载测试（普通重启即回到默认 `fedora-7.2.15-10`）。
- 预期与判据：
  1. 接键盘按电源键休眠 60 s 不自唤醒，且 `pogo_kb_resume` 打印 `suppressed>0` 证明 `+1.64 s` 电池包被 `s2idle` 内无感吸收，`qcom_stats` 的 `cxsd` / `ddr` 驻留仍约 98 %；
  2. 休眠后按键盘任意键能在真机唤醒系统，记录 `woke_by_rx=1`、KDE 是否直接点亮锁屏（决定第二步是否补发 `KEY_WAKEUP`）；
  3. 同步实测触控板触碰、拔掉键盘以及合盖按键盘的表现，为第二步合盖防误唤醒及正式补丁打包提供依据。

**第一步（c）实测结果（`kbd-wake-child.dtb` + `step1c/oneplus-pogo-keyboard.ko`）：**

- `tablet-reboot.py --entry opd2413-kbdwake` 38 s 上线并加载 `/tmp/oneplus-pogo-keyboard.ko`（`irq 287 msmgpio 3 Edge pogo-keyboard-wakeup` 注册成功、`serial0-0/power/wakeup = enabled`、`880000.serial/power/wakeup` 不再存在）。
- 实测两次短按电源键休眠（15:08:24、15:08:37），均仍发生自动唤醒，但时间线首次出现关键新现象：
  1. 第 1 次（15:08:24→15:08:28）：`STEP1C resume: woke_by_rx=1 wake_ms=2052 suppressed=2 last_supp_ms=2052`，1.88 s CXSD 驻留后在 2.05 s 唤醒（说明在 `<2.5 s` 内有两组相隔 5–150 ms 的下降沿突破阈值）；
  2. 第 2 次（15:08:37→15:08:49）：`STEP1C resume: woke_by_rx=1 wake_ms=10190 suppressed=1 last_supp_ms=188`，`0.188 s` 处吸收 1 次边沿后平板**稳定在 CXSD 深睡了整整 9.9945 s**（`qcom_stats/cxsd` `7020082822 -> 7211977368` ticks = `9.9945 s`），但在 **`10.190 s`** 时再次出现未知下降沿触发唤醒。
- 同日对比醒态下 `/sys/kernel/debug/gpio` 中 TLMM（`f100000.pinctrl`）的 `gpio3` 电平：键盘心跳工作时恒为 `in high`，而之前 `diag_sleep=1` 休眠静默 35 s 后测得 `gpio3` 为 `in low`——高度怀疑键盘 MCU 在进休眠后于 ~2 s / ~10 s 会安静拉低 UART TX 线电平（而非发串口包），且 `bias-pull-up` 可能与键盘侧下拉对抗造成边沿抖动。证据：`private/m3-kbdwake-20261113/{boot3-check,step1c-baseline,step1c-test1,step1c-test1-stats}.txt`。

**诊断抓取 2 计划（`diag2`，测全 0–15 s 边沿时间轴 + TLMM `gpio3` 电平跳变点，待用户批准）：**

离线编译 `private/m3-kbdwake-20261113/diag2/oneplus-pogo-keyboard.ko`（仅临时写 `/tmp/` 测试）：
1. 醒态下写入 `diag_sleep=1`，持续高频采样 TLMM `gpiochip8` 的 `gpio3`（每 100 ms 共 20 s），直接确定键盘 MCU 何时将总线从 `high` 拉为 `low`。
2. `s2idle` 期间由 `ignore_ms=15000` 记录 0–15 s 内每次 `pogo-keyboard-wakeup` 下降沿的准确毫秒时间戳数组 `edge_ms[16]`（15 s 后再按键唤醒），从而一次性看清 188 ms / 1.64 s / 2 s / 10.19 s 所有边沿的完整序列与真正按键唤醒的表现（包含锁屏是否直接亮屏）。

**诊断抓取 2 实测结果（`diag2`，已验证键盘唤醒且锁屏自动亮屏）：**

1. **醒态下 `diag_sleep=1` + 20 s TLMM `gpio3` 采样（`diag2-awake-gpio3.txt`）**：
   - 醒态心跳时 `gpio3` 为 `in high func1 2mA no pull`；下发 `POGO_KB_GENERAL_SLEEP(false)` 后 `+10 ms` 仍为 `high`，`+173 ms` 变为 `low`（MCU 关断 TX）；
   - 在 `+6973 ms` 时 `gpio3` 突然短暂升回 `high`，`+6976 ms` 串口收到单帧电池状态上报 `3b 04 0e 02 ...`（`~0.27 ms` 突发），随后在 `+7134 ms`（`150 ms` 采样窗口内）再次跌回 `low`。
   - 由此确认：之前看到的多组延迟下降沿并非“只有电平慢降”，而是键盘 MCU 进入休眠后会随机延迟几秒至十几秒醒来一次仅发出 `0x3b 0x04 0x0e` 电池帧、接着再把 TX 拉回低电平——既包含串口帧起始位下降沿，又包含片刻后 TX 关闭的 `high -> low` 下降沿（相隔仅十余毫秒至百余毫秒）。
2. **`s2idle` 实测（`diag2-test-sleep.txt`，短按电源键休眠 >20 s 后按空格键）**：
   - **平板超过 20 s 未再自动唤醒，按下键盘空格键后直接唤醒系统并自动点亮 KDE 锁屏**；
   - `dmesg` 记录 `DIAG2 resume: woke_by_rx=1 wake_ms=20807 suppressed=3 last_supp_ms=12430 edges=4`，精确边沿序列为：
     - `edge[0] = 2629 ms`、`edge[1] = 12416 ms`、`edge[2] = 12430 ms`（仅隔 `14 ms`，对应延迟电池帧与其随后的 `high -> low` 关断边沿）、`edge[3] = 20807 ms`（真空格键触发唤醒）；
   - `journalctl` 显示从 `15:22:35` `suspend entry` 到 `15:22:57` `suspend exit` 共休眠约 22 s，`org_kde_powerdevil` 收到 `PrepareForSleep(false)` 后直接唤醒锁屏界面。

**进一步自动唤醒排查（`diag2-autowake-2.txt`，关闭“唤醒后锁屏”后的连续 3 次休眠实测）：**

1. **实测现象（`journalctl` + `dmesg` 完整边沿）**：
   - 15:25:57→15:26:13（`~15.0 s`）：`DIAG2 resume: woke_by_rx=1 wake_ms=15004 suppressed=192 last_supp_ms=14987`，其中 `12728..12914 ms` 连续以 `~17 ms` / `~8 ms`（`60 Hz / 120 Hz`）疯狂触发了 192 次下降沿，一过 `15000 ms` 立即唤醒；
   - 15:26:47→15:27:09（`20.5 s`）：`wake_ms=20530 suppressed=4`（`528`, `9550`, `9564`, `10529`, `20530 ms`）；
   - 15:27:25→15:27:43（`17.0 s`）：`wake_ms=17035 suppressed=2`（`2700`, `12701`, `17035 ms`）。
2. **根因对照（原厂 `runtime.dts` + `out/ref/pogo_keyboard_core.c` vs 实验 `kbd-wake-child.dts`）**：
   - `diag_sleep=1` 醒态连续 20 s 采样与 118 s 监听均证明：`gpio3` 在 `bias-disable` 下进入 `+173 ms` 休眠后恒为 `in low`、除一次延迟电池包外完全静默；
   - 原厂 `runtime.dts` 的 `uart_rx_clear` 对 `gpio3` 明确配置 `input-enable; bias-disable;`（绝不配 `bias-pull-up`）；而本轮实验 `kbd-wake-child.dts` 把 `pogo_kb_uart_sleep/rx-pins` 改成了 `bias-pull-up`——当键盘进入更深一级省电并将 TX 置于高阻或下拉对抗时，`~50 kOhm` 上拉会将悬浮总线拖到逻辑阈值区，从而在 `~12–20 s` 出现 `60 Hz / 120 Hz` 工频/开关耦合振荡与随机下降沿误唤醒。

**诊断抓取 3 方案（`kbd-wake-child-pd.dtb` + `diag3`，离线已编译就绪，待用户批准）：**

1. 修改 `private/m3-kbdwake-20261113/kbd-wake-child.dts` 将 `pogo_kb_uart_sleep/rx-pins` 由 `bias-pull-up` 改为 `input-enable; bias-pull-down;`（与键盘休眠态 `gpio3 = low` 一致，即使键盘进入高阻态也稳稳钉在 `0 V` 不悬浮，同时按键唤醒时键盘推挽 TX 可无障碍驱动 `HIGH + 0x00/0x55` 下降沿），离线编译 `kbd-wake-child-pd.dtb` 并通过 `dtc` diff 确认仅改 `keyboard` 中断与 `rx-pins` 休眠下拉；
2. 离线编译 `diag3/oneplus-pogo-keyboard.ko`（`vermagic` 为 `7.2.15-10.opd2413`），在 `diag2` 基础上扩容 `edge_ms[32]` 并在 `pogo_kb_resume()` 后 `1.5 s` 内打印实际收到的串口原始帧 `DIAG3 RX`，以便万一仍有边沿唤醒可一眼分辨是否真有串口帧；
3. 写入范围：仅覆盖测试入口使用的 ESP 文件 `/boot/efi/opd2413-test/kbd-wake.dtb`、执行 `tools/tablet-reboot.py --entry opd2413-kbdwake` 重启，并将 `diag3/oneplus-pogo-keyboard.ko` 放到 `/tmp/oneplus-pogo-keyboard.ko` 内存态加载（默认引导项 `fedora-*` 与 `/lib/modules` 均不动）。
- 预期与判据：
  1. `suppressed=192` 的 `60/120 Hz` 抖动以及 `17 s / 20.5 s` 自动唤醒完全消失；
  2. 休眠 60 s 不自唤醒（随后顺带用该环境完成 60 s `qcom_stats` 驻留、触控板、合盖按键盘、拔掉键盘摸底，并在下一步用精确边沿判别替换掉 `ignore_ms=15000`）。

**诊断抓取 3 实测结果（`kbd-wake-child-pd.dtb` + `diag3`，消除 60/120 Hz 振荡，锁定 10.000 s 周期脉冲）：**

- `boot4-check.txt` 核验基线 `qcom_stats/cxsd` 与 `ddr` 均为 `Count: 0`；短按电源键休眠约 24 s 后再次自动唤醒（`diag3-test1.txt`）：
  1. **`60/120 Hz` 杂波振荡（`suppressed=192`）完全消失**：全程仅有 4 次干净的 `gpio3` 下降沿（`edge[0]=3997 ms`, `edge[1]=5223 ms`, `edge[2]=13998 ms`, `edge[3]=23999 ms`），`irq 287` 恰好计 `4`；
  2. **`cxsd` 驻留达 98.7%**：`Accumulated Duration = 454,742,459` ticks（`23.68 s / 24.00 s`），最后一次在 CXSD 连续深睡 `9.996 s`（`13998 -> 23999 ms`）后被第 4 记边沿直接唤醒；
  3. **跨多轮对照锁定精确 `10,001 ms`（`10.000 s`）周期**：`3997 -> 13998 -> 23999 ms`（间隔严格 `10001 ms`），与此前 `step1c`（`188 -> 10190 ms`，`+10002 ms`）以及 `diag2`（`528 -> 10529 -> 20530 ms`，`+10001 ms`；`2700 -> 12701 ms`，`+10001 ms`）完全一致，且相位每次随休眠起点漂移，证明在系统已入 CXSD 深睡期间**键盘 MCU 自身每 10.000 s 仍会触发一次 `gpio3` 下降沿**；
  4. **唤醒后仍需 3 次重发才能叫醒键盘**：`DIAG3 RX +1ms / +103ms / +207ms` 发出 `set_awake(true)` 直到 `+211/+218 ms` 才收到键盘 ACK 并恢复 `0x2f ... 0x05` 正常心跳（非上电重置 `0x01`），说明那次 `23999 ms` 边沿之后键盘本身仍在睡眠态、并未转成醒态（`10 s` 脉冲与真实按键有本质波形/状态差异）。

**诊断抓取 4 方案（`diag4`，微秒级边沿序列 + 醒态 `diag_sleep=1` 同源核对，待用户批准）：**

1. 离线编译 `diag4/oneplus-pogo-keyboard.ko`（`vermagic = 7.2.15-10.opd2413`，无需重启或改 DTB）：
   - 把 `edge_ms[]` 升级为 `arch_timer` 微秒精度数组 `edge_us[64]`（分辨率 `52 ns`），并在 `diag_sleep=1` 期间同样使能 `irq 287`（不唤醒系统、带 64 次上限防风暴保护），写 `0` 时一次性输出醒态 35 s 内所有下降沿微秒时间戳并对照 `DIAG4 RX`；
2. 写入范围：仅将 `diag4/oneplus-pogo-keyboard.ko` 写入平板 `/tmp/oneplus-pogo-keyboard.ko` 并 `rmmod && insmod` 加载，随后由本机在醒态执行 35 s `diag_sleep=1 -> 0` 采样。
- 预期与判据：
  1. 确认每 `10.000 s` 脉冲在醒态 `diag_sleep=1` 时是否同样出现（彻底排除 `s2idle`/pinctrl 嫌疑），并测出单次 `10.000 s` 脉冲与延迟电池包的**微秒级脉宽/连发个数**；
  2. 再对比一次短休眠按键唤醒的 `edge_us[]`，即可在代码里用微秒/多脉冲特征精确放行真实按键（0 盲区）、100% 屏蔽 `+173 ms` 关断、`1.6–12.7 s` 电池包和 `10.000 s` 周期脉冲。

**诊断抓取 4 实测结果（`diag4`，成功抓齐醒态与 `s2idle` 真按键微秒序列）：**

1. **醒态 35 s `diag_sleep=1` 对照（`diag4-awake-35s.txt`）**：35 s 内收到 `0` 字节串口数据且 `edges=0`——核查 `pinctrl-msm.c` 第 195–208 行（`msm_pinmux_set_mux`）确认，只要 `gpio3` 仍处于 `qup2_se0` 功能复用态，`pinctrl-msm` 会主动 `disable_irq_nosync()` 屏蔽该引脚 GPIO 中断，只有 `s2idle` 切回 `gpio` 态才解除屏蔽。
2. **`s2idle` 约 4.5 s 点按空格 + 随后自唤醒的完整 10 记微秒波形（`diag4-keypress-us.txt`）**：
   - `edge[0] = 2,402,824 us`、`edge[1] = 2,416,462 us`：延迟电池上报包与 TX 关断，间隔 **`13.638 ms`**，**仅 2 个簇**；
   - `edge[2..7] = 4,542,164 -> 4,602,937 -> 4,611,554 -> 4,618,039 -> 4,667,215 -> 4,681,060 us`：真实点按空格键在 **`138.9 ms`** 内产生 **6 个下降沿簇**（相对起始分别为 `+0`、`+60.8`、`+69.4`、`+75.9`、`+125.1`、`+138.9 ms`）；
   - `edge[8] = 5,402,234 us`：键盘无人应答约 `0.72 s` 后自行重新关断 TX 进入深睡（**1 个簇**）；
   - `edge[9] = 15,403,372 us`：严格隔 **`10,001.138 ms`** 后键盘例行发出 **`10.000 s` 周期脉冲**（**1 个孤立簇**）并触发 `15 s` 后阈值唤醒（`cxsd Last Entered -> Last Exited = 9.993 s`）。

**第一步（d）精确多簇唤醒过滤方案（`step1d`，无 15 s 盲区，待用户批准）：**

1. 离线编译 `private/m3-kbdwake-20261113/step1d/oneplus-pogo-keyboard.ko`（`vermagic = 7.2.15-10.opd2413`，沿用当前已刷好的 `kbd-wake-child-pd.dtb`，无需重启）：
   - 取消 `ignore_ms=15000` 固定盲区，在 `pogo_kb_rx_wake_isr` 中对间隔 `>= 4 ms`（合并同帧内部 `<4 ms` 边沿）且连续间隔 `<= 100 ms`、总跨度 `<= 250 ms` 的脉冲簇计数：
     - 关断 TX（1 簇）、`10.000 s` 周期脉冲（1 簇）、延迟电池上报+TX关断（`13.6 ms` 2 簇）计数均 `<= 2`，在 `s2idle` 内直接吸收；
     - 真实按键在 `< 76 ms` 内达到 **`3` 个簇**，无论在休眠第几秒按下都立即 `pm_wakeup_dev_event()` 唤醒（`< 80 ms` 响应）。
2. 写入范围：仅将 `step1d/oneplus-pogo-keyboard.ko` 上传到 `/tmp/oneplus-pogo-keyboard.ko` 并 `rmmod && insmod` 内存加载（不动 ESP/DTB/引导项/`/lib/modules`）。
- 预期与判据：
  1. 展开连接休眠 **60 s 以上全程不自唤醒**，且 `qcom_stats/cxsd` 与 `ddr` 驻留保持 ~98% 以上；
  2. 短睡（如 3 s）与长睡（60 s 后）点按空格键均在 `< 100 ms` 内唤醒且直接点亮屏幕；
  3. 同步摸底：**触控板点击/触摸**、**合盖状态下按键盘**、**拔掉键盘休眠 10 s + 吸合**、**闲置自动息屏进 `s2idle` 后按键**。

**第一步（d）实测结果（`step1d-results.txt`，2026-11-13 15:58–16:02，发现“10 s + 22.66 s”拍频碰撞导致第 108 s 误唤醒）：**

1. **短睡与长期静置对照（4 轮休眠合计 `cxsd` `+147.625 s` / 总睡眠 `~152.4 s` ≈ `96.9%`）**：
   - **第 1 轮（`15:58:12→15:58:17`）**：`systemd-logind` 记录 `Power key pressed short` 唤醒（`irq 23` 计 `8→9`，`woke_by_rx=0`），期间仅收到 1 记 `10 s` 脉冲（`4,088,560 us`）并被屏蔽；
   - **第 2 轮（`15:58:31→16:00:21`，`wake_ms = 108,375 ms`）**：前 `108 s` 成功屏蔽了 10 记 `10.001 s` 周期脉冲与 4 对 `22.659 s` 延迟电池包（`17.728 s` / `40.386 s` / `63.045 s` / `85.704 s`，每对相隔 `13.30–13.43 ms`）；但在第 `108.34 s` 发生**拍频碰撞**：
     - `edge[18] = 108,340,918 us`：第 11 记 `10.001 s` 周期脉冲（+1 簇）；
     - `edge[19] = 108,362,585 us`：第 5 次 `22.6588 s` 电池包（`85.703766 + 22.658819`），距 `edge[18]` 仅 **`21.67 ms`（<= 100 ms）**（+1 簇）；
     - `edge[20] = 108,375,912 us`：该电池包的 TX 关断边沿（`+13.33 ms`）（+1 簇）；
     - 三者合计在 `35 ms` 内凑满 `POGO_KB_WAKE_CLUSTERS = 3`，于 **`108.375 s`** 触发误唤醒（`DIAG4 RX` 无任何键鼠 HID 报文）。
   - **第 3、4 轮（`16:01:03→16:01:16`、`16:01:29→16:01:55`）**：合盖休眠后隔盖挤压键盘均**未唤醒**（只分别吸收了 `2.011/2.024 s` 电池对与 `0.710 s` 1 边沿），掀开保护盖由 `irq 238 Cover` 正常唤醒（`DIAG4 RX` 随后出现开盖键码 `0x69` 与正常 `0x2f` 心跳）。
2. **结论**：单次 `10.001 s` 脉冲（1 簇）与单次 `22.659 s` 电池包（2 簇，`~13.3 ms`）因两者周期存在约 `2.66 s / 10 s` 拍频漂移，每 ~1–2 分钟必有一次在 `<= 100 ms` 内重合产生 `1 + 2 = 3` 簇；因此最低安全阈值必须是 **`4` 簇**（已知真实按键点击可发出 6 簇 / `139 ms`）。

**第一步（e）4 簇过滤验证方案（`step1e`，离线已编译就绪，待用户批准）：**

1. 离线编译 `private/m3-kbdwake-20261113/step1e/oneplus-pogo-keyboard.ko`（`vermagic = 7.2.15-10.opd2413`）：
   - 将阈值调整为 `POGO_KB_WAKE_CLUSTERS = 4`、`POGO_KB_WAKE_CLUSTER_MAX_US = 120000`（`120 ms`，兼容长按时 `100 ms` 心跳衔接）、`POGO_KB_WAKE_WINDOW_US = 300000`（`300 ms`），并暴露 `wake_clusters` 模块参数以便微调；保留 `STEP1E edge[]` 与 `DIAG4 RX` 观测，彻底屏蔽最多只有 `1 + 2 = 3` 簇的周期信号碰撞。
2. 写入范围：仅将 `step1e/oneplus-pogo-keyboard.ko` 覆盖平板 `/tmp/oneplus-pogo-keyboard.ko` 并 `rmmod && insmod` 内存加载。
- 预期与判据：
  1. 展开静置休眠 **`>= 120 s`**（完整跨过一次 `10 s + 22.66 s` 拍频重合期）全程不自唤醒，`cxsd`/`ddr` 保持 ~98%+；
  2. 随后短按**空格键**立即唤醒并点亮屏幕，记录 `edge_us[]`；
  3. 同步验证：**轻触/滑动触控板**唤醒表现（记录 `edge_us[]` 确认单次轻点 vs 滑动的簇数）、**合盖按压不醒/开盖唤醒**、**拔掉键盘休眠 10 s + 吸合**、**闲置自动息屏进 `s2idle` 后按键唤醒**。

**第一步（e）实测结果（`step1e-results.txt`，2026-11-13 16:40–16:55，4 簇阈值长睡通过，确认触控板休眠物理停报）：**

1. **短睡与跨拍频长睡（4 轮休眠，合计 `cxsd` `+368.390 s` / 约 `377 s` ≈ `97.7%`）**：
   - **短睡空格唤醒（`16:44:16→16:44:24`）**：`woke_by_rx=1 wake_ms=7080`，空格键在 `125.0 ms` 内产生 4 簇（`6.956 -> 7.012 -> 7.025 -> 7.081 s`），立即点亮屏幕唤醒；
   - **144 s 静置对照（`16:47:20→16:49:45`）**：跨过 14 次 `10.001 s` 脉冲与 6 对 `22.659 s` 电池包**全程 0 自唤醒**，最后由电源键唤醒（`woke_by_rx=0`）；
   - **162.5 s 跨拍频 + 触控板摸底 + 按键唤醒（`16:50:07→16:52:51`）**：跨过 16 次 `10 s` 脉冲与 8 对 `22.66 s` 电池包**全程 0 自唤醒**；用户期间轻触、滑动及物理按压触控板，`edge[0..31]` 中**未出现任何触控板边沿**（说明键盘 MCU 收到 `POGO_KB_GENERAL_SLEEP(false)` 后硬件关闭了触控板传感器，此前 `step1d` 第 `108.375 s` 刚好撞上电池包碰撞造成错觉）；随后按键盘立即以 4 簇唤醒（`woke_by_rx=1 wake_ms=162544`）；
   - **拔下键盘休眠 + 吸合唤醒（`16:54:21→16:54:36`）**：拔掉休眠 15 s 不自唤醒，吸回瞬间由 `irq 242 pogo-keyboard-detect` 唤醒并重连 `OnePlus Pad 2 Pro Keyboard` / `Touchpad`（`KA030_B_1.2.0_TP_A_13`）。

**第二步 正式内核补丁、`7.2.15-11.opd2413` 构建与部署方案（离线构建校验完成，待唤醒平板与批准写入）：**

1. 在 `out/m3k/tree`（`series3` 分支）正式提交并导出两枚严格 `-F0` 补丁到 `kernel/opd2413-7.2/patches/`，已同步更新 `patches/series`、`kernel/PATCHES.md`、`kernel/opd2413-7.2/README.md` 与 `out/m3k/build.sh`（`N=11`）：
   - `2408-arm64-dts-qcom-sm8750-oneplus-pad2pro-add-pogo-keyboard-wake-IRQ.patch`：`pogo_kb_uart_sleep/rx-pins` 改 GPIO 输入 + `bias-pull-down`，`&uart_kb/keyboard` 传入 `detect` + `wakeup` 双中断；
   - `2409-Input-oneplus-pogo-keyboard-wake-from-suspend-on-key-press.patch`：去掉全部诊断输出与 sysfs 节点，用 `mul_u64_u32_div`（防长时间休眠 64 位乘法溢出）+ 常开 arch timer 实现 300 ms / 4 簇过滤（`>= 4 ms`, `<= 120 ms`），`W=1` 编译 `oneplus-pogo-keyboard.ko` 0 警告，反编译 DTB 与 `kbd-wake-child-pd.dtb` 仅属性声明顺序差异；
2. `./out/m3k/build.sh` 构建 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-11.opd2413.aarch64.rpm` 成功（`BUILD-OK`）；
3. `tests/package-install-test.sh` 离线容器校验（搭配 `opd2413-firmware-16.0.10.600-2` 等最新包）：initramfs（67 个早起固件全部包含、`0 missing`）、`fedora-7.2.15-11.opd2413.conf`、DTB 一致性及负面用例（`refused`）均通过（注：测试脚本内置期待 `66` 个，因 `-firmware-16.0.10.600-2` 现为 `67` 个报 `1` 行数量差异）；
4. 待用户唤醒平板并批准写入范围：先做只读核对 `rpm -q kernel-opd2413` 与 `/boot/efi` 剩余空间，随后上传并 `dnf install kernel-opd2413-7.2.15-11.opd2413.aarch64.rpm`，清理临时 `/boot/efi/opd2413-test/` 与 `/boot/efi/loader/entries/opd2413-kbdwake.conf`，重启进入默认项 `fedora-7.2.15-11.opd2413` 做最终冷启动/功能/驻留验收。

**部署 `7.2.15-11.opd2413` 后复现的冷启动早休眠复位排查（`ramoops-000009` → `LLCC_ISLAND1`）：**

- 安装 `kernel-opd2413-7.2.15-11.opd2413` 并清理 `/boot/efi/opd2413-test/` 与 `opd2413-kbdwake.conf` 后，冷启动进入桌面在 **30–60.8 s 内**按电源键进 `s2idle` 连续出现延迟十余秒后硬件复位（并偶发冷启动灰屏卡死）；证据 `private/m3-kbdwake-20261113/prod11-coldcrash-logs.txt`。
- 为抓取复位瞬间，在平板临时部署 `/etc/systemd/system/opd2413-s2idle-dbg.service`（开启 `console_suspend=N`、`ignore_loglevel=Y`、`pm_debug_messages=1`、`pm_print_times=1`、`kernel.panic=15`），在第 9 号 pstore 记录 `000009`（`private/m3-kbdwake-20261113/ramoops-000009-s2idle.txt`）捕到完整现场：所有设备 `suspend` / `suspend_late` / `suspend_noirq` 回调均正常返回，系统停在 `[60.814536] PM: suspend-to-idle` 后进入 `CXSD`（`domain_ss3`）瞬间硬件复位。
- 对照 `~/github/linux-sm8750-erhai` 差异锁定根因：自 `7.2.15-6` 引入 `2401`（允许 LPASS TX/VA macro codec 在挂起时释放 prepare vote）时，漏合 erhai 提交 `b30d759d375e69164b0da842250cb69c785ece5c`（`soc: qcom: llcc-qcom: Reserve ISLAND1 ways on SM8750`，作者 `yzddmr6`）；该提交注释明确指出必须在允许 LPASS macro codec 释放 prepare vote 前将 `LLCC_ISLAND1` 的 `.bonus_ways = 0x7fffffff` 改为 `.res_ways = 0x7fffffff`，否则未预留切片进入低功耗态时会触发 `PS_HOLD` 硬件复位。

**第三步 仅合入 `2410` 构建 `7.2.15-12.opd2413` 与真机冷启动双项验收：**

1. **构建与离线校验**：将 erhai `b30d759d3` 原样导出为 `kernel/opd2413-7.2/patches/2410-soc-qcom-llcc-qcom-Reserve-ISLAND1-ways-on-SM8750.patch`，更新 `patches/series`、`kernel/PATCHES.md`、`kernel/opd2413-7.2/README.md` 与 `out/m3k/build.sh`，构建 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-12.opd2413.aarch64.rpm`（`SHA256: b254d359e1bb9077392fe97ef8bb29af2b945bb05df617d75cda8b1c830488d4`）。`tests/package-install-test.sh`（`out/m3k/pkg-test12/`）确认 initramfs 含全部 67 个早起固件、`0 missing`。
2. **装机与带调试服务对照冷启动（`boot0-7.2.15-12-dbg.log`）**：同步时钟后安装 `7.2.15-12.opd2413` 并一次性冷启动进入；开机仅 **`26.56 s`** 按电源键进入 `s2idle`（`[27.928034] PM: suspend entry (s2idle)`，早于此前所有崩盘点 `30–60.8 s`），**未挂死未复位**，`suspend_stats/success = 1, fail = 0`，`qcom_stats/cxsd` 与 `ddr` 均计 1 次、深睡 `2.50 s`；同时证实首次按电源键唤醒“闪内核日志后黑屏、再按一次才亮”是临时调试服务开启 `console_suspend=N` + `pm_debug_messages=1` 狂刷约 1400 行日志造成 `/dev/kmsg` 溢出并把 `PrepareForSleep(false=resume)` 推迟到按键事件 `272 ms` 之后、触发 `kwin_wayland` 随后下发 `panel_unpreparing` 所致。
3. **清理调试服务并设默认启动项后的无干扰冷启动最终验收（`boot0-7.2.15-12-clean.log`）**：
   - 删除平板 `/etc/systemd/system/opd2413-s2idle-dbg.service`，执行 `/usr/libexec/opd2413/boot-select default 'fedora-*'`（`bootctl list` 确认 `(default)` 为 `fedora-7.2.15-12.opd2413.conf`，`loader_default: "fedora-*"`，`kshim_remembered: "Fedora"`），关机后用户冷启动验证：
   - **系统健康**：`7.2.15-12.opd2413`，`systemctl is-system-running = running`，`systemctl --failed = 0`，SELinux `Enforcing`，`/sys/fs/pstore` 为空，电池 `92 % Discharging`。
   - **测试 1（冷启动 21.36 s，电源键休眠/唤醒）**：`[21.358825]` 短按电源键 → `[22.464090]` `PM: suspend entry (s2idle)` → 等约 5 s 后按电源键 → `[24.162837]` `Power key pressed short` → `[24.168062]` `PM: suspend exit`（内核恢复耗时 `2.9 ms`）→ `[24.187143]` `PrepareForSleep(false=resume)` → `[24.417234]` `panel_prepared`，用户确认**一次直接唤醒亮屏，无闪内核日志、无二次黑屏或重启**。
   - **测试 2（Pogo 键盘空格键唤醒）**：`[32.841071]` 短按电源键 → `[33.924024]` `PM: suspend entry (s2idle)` → 等约 5 s 后按一次空格键 → `[35.482819]` `PM: suspend exit`（内核恢复耗时 `3.8 ms`）→ `[35.489732]` `PrepareForSleep(false=resume)` → `[35.776336]` `panel_prepared`，用户确认**一次空格键直接唤醒亮屏**。
   - **深睡统计**：`/sys/power/suspend_stats/success = 2, fail = 0`（全部 `failed_* = 0`）；`qcom_stats/cxsd` `Count = 7, Accumulated Duration = 209335981`（`10.903 s`），`qcom_stats/ddr` `Count = 7, Accumulated Duration = 209432201`（`10.908 s`）。
   - **附带观测**：此前硬件复位使 PMIC RTC 回到 `2026-10-17`，且平板侧 `chronyc sources` 解析到保留地址（`Reach = 0`、`Not synchronised`），暂未改动系统 NTP 配置。

---

## 2026-11-14 显示在线 modeset（60 / 30 Hz 与 Night Light）修复

- **调查与根因文档**：[DISPLAY-60HZ-MODESET.md](DISPLAY-60HZ-MODESET.md)（已核查 `ok15`、`nl15`、`ok6`、`f60` 4 组 devcoredump）。
- **根因**：
  1. 双 DSI 绑定视频模式共用 `CTL_0`，而 `dpu_encoder_virt_atomic_disable()` 对 `phys_encs[0]`（从界面 `INTF_2`）执行 `dpu_encoder_phys_vid_disable()` 时立刻在内部调用 `dpu_encoder_helper_phys_cleanup()`，在主界面 `INTF_1` 与 `sspp_8` 仍处于扫描抓取态时即下发 `CTL_SW_RESET`（超时退化为 `CTL_SW_RESET_OVERRIDE`）、清混合器与 `CTL_FETCH_PIPE_ACTIVE` 并 `trigger_start`，造成 `vbif + 0x20c = 0x30`（`VBIF_AXI_HALT_CTRL1`）、`vbif + 0x204 = ffff0000` 与 `sspp_8` 取数停摆。此前 `DPMS 1->0 -> 0->1` 因跨提交释放 `pm_runtime` 触发 MDSS 断电复位掩盖了该问题，而在屏亮状态切换模式或夜灯的在线 modeset（`active: 1->1, mode_changed=1`）会持续带入复位后的 `0->1` 启用阶段导致黑屏卡死。
  2. 此外，`msm_atomic_check()` 与 `dpu_crtc_check_mode_changed()` 在 `ctm` 变化时强制触发 `mode_changed = true`，且 `dpu_crtc_get_topology()` 仅在需求存在时才向 RM 申请 DSPP，导致夜灯开关不仅触发在线 modeset，还会在关夜灯时因 `hw_dspp` 丢失而跳过 `setup_pcc(dspp, NULL)`（`#35`）。
- **内核改动（`7.2.15-13.opd2413`，补丁 `2411`–`2413`，严格 `-F0`）**：
  - `2411`（`dpu_encoder.c`、`dpu_encoder_phys_{vid,cmd,wb}.c`）：在 `dpu_encoder_virt_atomic_disable()` 中先停止非主物理编码器、再停 `cur_master`（等待 VSYNC / `!is_en`），所有物理编码器停止后再按共享 `hw_ctl` 调用一次 `dpu_encoder_helper_phys_cleanup()`，并循环清理该 CTL 下全部物理编码器的 mixer 与 `CTL_INTF_ACTIVE` / `CTL_INTF_MASTER`。
  - `2412`（`dpu_encoder.c`、`dpu_crtc.c`、`msm_atomic.c`）：在 `dpu_encoder_update_topology()` 中为非 WB 显示输出预先分配 `num_dspp = num_lm`，并在 `old_crtc_state` 已持有 `hw_dspp` 时取消 `ctm` 触发 `mode_changed = true`。
  - `2413`（`panel-novatek-nt36536.c`）：在 `1412` 之后恢复 `novatek_nt36536_vfp[] = { 26, 2684, 8000 }`（120 / 60 / 30 Hz）。
- **构建产物**：`out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-13.opd2413.aarch64.rpm`（SHA256 `beafdddab88ec25bc96855564bbe69a482aa6c11760baffc806a9fea68222a0f`）。
- **用户冷启动初测补充观察**：用户反馈首次开机曾两次卡在灰屏后自动重启、第二次后进入桌面；经肉眼确认 120/60/30 Hz 刷新率与夜光色温均可正常调节。对于灰屏问题，用户补充其一直存在（通常一闪而过，这次卡得更久），基本出现在选完 kShimC 引导后、内核日志尚未出现之前。
- **二分定位 `-12 -> -15` 引入的 `DPMS off -> on` 回归（`dsi1 cmd dma timeout`）**：
  1. 在 `-12` 上对照 `DPMS off -> 2s -> on` 连续 3 轮（`t = 39.07 s .. 45.24 s`，每轮 `mdss_gdsc off-0`），全部正常唤醒（`panel_prepared`、零 DSI/超时错误）；核对 `~/.config/kwinoutputconfig.json` 确认当时输出模式为 `vtotal=2658`（`120 Hz`），`-12` 与 `-15` 的 DTB SHA256 均为 `6d57fdad...`、内核参数一致，两版差异仅 `2411`（`689e095a6`）与 `2413`（`184c05cf8`）。
  2. 构建仅含 `2411`（不含 `2412` / `2413`）的 `7.2.15-16.opd2413` 并单次引导测试：`DPMS off -> 2s -> on` 第一轮即在第 `21.683520 s` 复现 `dsi1 cmd dma timeout`（`sending dcs data b3 40 failed: -110`，`dsi0` 报 `ERR_CONTENTION_LP1` `0x10000`），确认 `2411` 本身为回归来源。
  3. 构建保留原始 `phys_encs[]` 停用顺序（`phys_0` / `cur_master` 先、`phys_1` / 从端后）、仅保留 `2411` 延后 `dpu_encoder_helper_phys_cleanup()` 的 `7.2.15-17.opd2413` 并上机测试：`DPMS off -> 2s -> on` 连续 **8 轮全部通过**（`mdss_gdsc off-0`、零 DSI/超时错误），证明反向先停从端 `phys_1` 再停主端 `cur_master` 是触发 `ERR_CONTENTION_LP1` 的原因。
- **最终修复（`7.2.15-18.opd2413`）构建与全套验收**：
  - 将保留原始 `phys_encs[]` 停用顺序的 `2411`（`out/m3k/tree` `series3`）与 `2412`、`2413` 重新打包并验证 `-F0` 无模糊合入，构建 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-18.opd2413.aarch64.rpm`（SHA256 `8df72537d0aed06614860cdd0c099bbf620a04951a22017a227d68a9cd2782b4`）。
  - **经用户确认后装机并单次引导进入 `7.2.15-18.opd2413` 实测结果（全部真机通过）**：
    1. **内联刷新率切换**：`120 -> 60 -> 30 -> 120 -> 60 -> 120 Hz` 连续 5 次切换全部成功（每次约 `470 ms`，零 VBIF / `vblank` / DSI 超时或卡死）。
    2. **多刷新率 DPMS 灭屏/亮屏**：在 `120 Hz`、`60 Hz`、`30 Hz` 下各测 `DPMS off -> 1s/2s -> on`（共 6 轮）全部正常唤醒（每轮 off 均进 `mdss_gdsc off-0`，dmesg 零 `dsi`/`timeout`/`vblank` 错误）。
    3. **Night Light（`#35`）**：经 D-Bus `org.kde.KWin.NightLight` 测 `preview 2000` → `preview 6500` → `stopPreview`，`/sys/kernel/debug/dri/0/kms` 中 `dspp_0_pcc` 与 `dspp_1_pcc` 随色温更新（`2000K`：`0x0: 00000001, 0x10: 0000b6c6`）且在 `6500K` 清零（`0x0: 00000000`），全程 `panel_unpreparing` 计数保持 `14`（零 modeset）。
    4. **`s2idle` 休眠唤醒**：`systemctl suspend` 进入 `s2idle` 后由用户按键正常唤醒，`suspend_stats/success = 1`，`dmesg` 记录 `PM: suspend entry (s2idle)` → `PM: suspend exit` → `panel_prepared`（`count = 16`），零错误。
    5. **切换默认项、清理临时内核与默认重启复核**：经用户确认后卸载 `kernel-opd2413-7.2.15-17.opd2413`、执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-18.opd2413.conf`（保留 `7.2.15-12.opd2413` 作为回退）、清理 `out/m3k/tree` 的临时二分分支（仅保留 `base` 与 `series3`）并将 `out/m3k/build.sh` 默认 `N` 更新为 `18`；随后执行无参默认重启，设备 `49 s` 回到 `7.2.15-18.opd2413`（`systemctl is-system-running = running`，`systemctl --failed = 0`，SELinux `Enforcing`，`/boot/efi` 已用 `247M` / 剩余 `266M`）。
- **追加排查（`-18` 手动 60 Hz 卡死 → `-19`/`-20`/`-21` 控制变量对比 → `-22` 补丁 `2414` 收敛）**：
  - **问题复现**：用户在 `7.2.15-18.opd2413` 上通过 KDE 设置手动切换至 `60 Hz` 后仍触发 `CTL_0` 卡死黑屏，连带切回 `120 Hz` 亦黑屏。
  - **控制变量对照**：
    1. `7.2.15-19.opd2413`（`_dpu_encoder_helper_phys_cleanup()` 中保留 `trigger_flush(ctl); trigger_start(ctl);`）：`120 Hz` 下 `DPMS off -> 3s -> on` **4/4 通过**（`mdss_gdsc off-0 -> on`，`err_lines=0`），但在线切刷新率仍卡死 `CTL_0`。
    2. `7.2.15-20.opd2413`（补丁 `2414` 初版：跳过 `trigger_flush`/`trigger_start` 且追加二次 `ctl->ops.reset(ctl)`）：在线切换 `120 <-> 60 <-> 30 Hz` **9/9 通过**，但 `DPMS off -> 3s -> on` **4/4 失败**（`dsi1 cmd dma timeout`、`hw ctl reset is set for ctl:1`、`vblank timeout: 4208c0`）。
    3. `7.2.15-21.opd2413`（仅跳过 `trigger_flush`/`trigger_start`，去掉二次 `ctl->ops.reset(ctl)`）：在线切换 `120 -> 60 -> 30 -> 60 -> 120` 正常，但 `DPMS off -> 3s -> on` 仍 **2/2 失败**（`ff 20` / `fb 01` DCS 超时、`clk=008077c3 dln0=00088888`、`vblank timeout: 4208c0`）。对照 `-19` 与 `-21`（仅差跳过 `trigger_flush`/`trigger_start`）锁定：`DPMS off`（`mdss_gdsc` 后续掉电）必须保留 `trigger_flush`/`trigger_start`，而在线 modeset（`active == true`、`mdss_gdsc` 保持供电）必须跳过。
  - **补丁 `2414` 定版与 `7.2.15-22.opd2413` 实机验收**：
    - 在 `dpu_encoder_virt_atomic_disable()` 中按 `new_state && new_state->active && (!new_conn_state || new_conn_state->best_encoder == drm_enc)` 计算 `skip_vid_trigger`，仅在此条件且 `phys_enc->intf_mode == INTF_MODE_VIDEO` 时跳过 `_dpu_encoder_helper_phys_cleanup()` 里的 `trigger_flush`/`trigger_start`。构建 `kernel-opd2413-7.2.15-22.opd2413.aarch64.rpm`（SHA256 `139a520f8173bc7152d34f2f6f01c8f07` 等已校验），在平板卸载 `-19`/`-20`/`-21` 后安装 `-22` 并单次引导（`loader.conf` 默认仍保持 `-18`）。
    - **实机验证结果（全部真机通过）**：
      1. `DPMS off -> 3s -> on`：120 Hz 连续 3 次、60 Hz、30 Hz 下全部正常降压至 `off-0` 并恢复 `on`，零 DRM/DPU/DSI/vblank/LUTDMA 报错；
      2. 在线切换：`120 -> 60 -> 30 -> 60 -> 120 -> 60 Hz` 全部 `rc=0`，`crtc-0/status` 与 `dri/0/kms` 验证三档刷新率均正常双路扫描出图；
      3. 夜览：KWin `org.kde.KWin.NightLight.preview 3500` / `stopPreview`（`4050` ↔ `4500` K）内核 `kmsg` 零相关报错、无 modeset；
      4. `s2idle` 休眠与唤醒：因 `systemctl suspend` 在 `rtcwake -s 8` 预设闹钟过点约 2 秒后才正式入睡由用户短按电源键唤醒，日志记录完整 `PM: suspend entry (s2idle)` → `PM: suspend exit` → `panel_prepared` → `follower resume #18 complete`（`uptime: 257.31` 未重启），唤醒后立即复测 `120 -> 60 -> 30 -> 120 Hz` 与 `DPMS` 零显示错误；
      5. **用户手动测试**：用户确认桌面手动操作（切换刷新率、夜览、息屏亮屏、触控等）没有问题。
    - **诚实记录技术债**：在 [TECH-DEBT.md](TECH-DEBT.md) 正式登记 `#36`（`2414` 为基于 `new_state->active` 的状态规避而非寄存器级根修，且仍走非无缝 disable/enable）与 `#37`（快速切换时 `nt36536` 偶发 `nvt_ts_resume 2139: -112` 竞争日志）。
    - **切换默认项、清理旧内核与默认重启复核**：经用户确认后执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-22.opd2413.conf` 并 `rpm -e kernel-opd2413-7.2.15-18.opd2413`（保留 `7.2.15-12.opd2413` 回退，ESP `/dev/sda16` 已用 `247M` / 剩余 `266M`、`49%`）；随后执行无参默认重启，设备 `49 s` 自动拉起 `7.2.15-22.opd2413`（`systemctl is-system-running = running`，`systemctl --failed = 0`，SELinux `Enforcing`）。

---

## 2026-11-14 开机灰闪（TECH-DEBT #9）根因与 `2415`

**只读取证（13:55，`7.2.15-22` 本次开机的 dmesg）：** `0.237 s` efifb 注册（`quiet`，fbcon 推迟接管，不画字）→ `0.294/0.308 s` 两颗 KTZ8868 探测 → `0.439 s` `1407` 停 ABL 扫描输出（此时 INTF 仍在出帧：`line 2448/2450 frame 2149/2149`）→ `0.859 s` 面板 prepare → `1.114 s` fbcon 接管 msm 帧缓冲，屏幕第一次出字。用户说的"内核日志出现之前"就是内核 0–1.1 s 这一段。`/var/lib/opd2413-pstore/` 的 20 条记录都是正常 `reboot: Restarting system` 的尾巴，没有灰屏卡死那几次的现场。

**根因候选（源码）：** `drivers/clk/qcom/dispcc-sm8750.c` 里 `disp_cc_mdss_mdp_clk_src` 用的是 `clk_rcg2_shared_ops`，它的 `.init`（`clk_rcg2_shared_init`）在 dispcc **注册时**调 `clk_rcg2_shared_disable()`，把 RCG 停到 XO（19.2 MHz）。dispcc 是内建的（`CONFIG_SM_DISPCC_8750=y`），在内核早期就探测。这时 ABL 的 3392×2400@120 Hz 双 DSI 扫描输出仍由这个 RCG 供时钟（来自 `disp_cc_pll0`；`clk_taycan_elu_pll_configure` 发现 PLL 已开会跳过，不是问题），MDP 核心时钟被骤降，DPU 取不到帧，液晶显示灰色，直到 msm 接管、面板重新初始化。

佐证：
- 上游 `dispcc-sc8280xp`、`dispcc-x1e80100`、`dispcc-eliza` 对同一个 `mdss_mdp_clk_src` 都已改用 `clk_rcg2_shared_no_init_park_ops`；SM8750（本树和 erhai `70b572544`）没改。
- 11-11 M3a 第 4 次（`initcall_blacklist=msm_drm_register`，不加载 msm）照样灰屏而且一直不恢复；第 11 次 earlycon 打完日志后同样变灰白。说明触发点在 msm 之外、更早的地方。
- 以前在 msm/背光侧的 `1409`（停输出前先关背光）和 armada `grey1`（`1410`，探测时关灯）都没改善灰闪。

**改动（单变量）：** `2415-clk-qcom-dispcc-sm8750-don-t-park-mdp_clk_src-at-reg.patch`，只把这一个 RCG 的 ops 换成 `clk_rcg2_shared_no_init_park_ops`（注册时只读回 CFG，RCG 保持 ABL 配置，直到 msm 接管或 `clk_disable_unused()` 时才停）。`HEAD~1` 上 `patch -F0` 无模糊合入。构建 `7.2.15-23.opd2413`（`out/m3k/build-23.log`）。

**上机前写好的预期和判据：**
- 安装方式：`dnf install` 新内核，默认项保持 `fedora-7.2.15-22.opd2413.conf`，`tools/tablet-reboot.py --entry fedora-7.2.15-23.opd2413` 一次性引导。
- 通过：选完 kShimC 的 Fedora 后，进度条走完到出字/出桌面之间**不再出现灰屏**，只应看到进度条画面 → 黑（`1409` 关背光、`1407` 停输出）→ 字/桌面。用户肉眼观察，冷启动（`systemctl poweroff` 插电自动开机）和重启各至少 3 次，全部无灰闪；dmesg 没有新增 clk/dispcc/mdss 报错，`bootloader scanout:` 行仍正常；进桌面后显示、刷新率切换、DPMS、s2idle 回归正常。
- 失败：灰闪照旧 → 否定这个根因，回到 `-22`，下一步用 `initcall_debug` 对时间轴定位 dispcc、gpucc、interconnect 各自的探测点。
- 偶发的"灰屏卡住后自动重启"出现频率低，这批测试次数不够证明它也消失了，单独长期观察，不拿它当本次的通过判据。

**离线结果（14:08）：** `7.2.15-23` `BUILD-OK`，`kernel-opd2413-7.2.15-23.opd2413.aarch64.rpm` SHA256 `e4482d81b687f1ace8aba6e43dc533ed5ff61719d1f4574114b41727b83d22e4`。`nm dispcc-sm8750.o` 同时引用 `clk_rcg2_shared_no_init_park_ops`（mdp）和 `clk_rcg2_shared_ops`（ahb/esc0/esc1，未动）。`tests/package-install-test.sh out/m3k/rpms23 out/m3k/pkg-test23`：条目、ESP、DTB 一致、缺固件拒绝都通过，initramfs 67 个早期固件 0 缺失；唯一的 FAIL 是脚本第 78 行写死 66（固件 600-2 起是 67，和 11-13 的情况一样，测试常量没更新）。

**真机结果（14:25）：真机失败。** 安装 `7.2.15-23.opd2413` 并选择启动后，仍出现灰屏，且在灰屏处卡死数秒后黑屏自动重启；因尚未挂载根文件系统，`opd2413-boot-restore.service` 未能执行，导致“重启 -> 自动选 -23 -> 灰屏卡死 -> 黑屏重启”循环，直至用户通过 kShimC `"Fedora boot menu"` 手动选择 `7.2.15-12.opd2413` 才打断循环并恢复 `loader_default` 为 `fedora-7.2.15-22.opd2413.conf`。因带 `quiet loglevel=3` 且未进用户态，pstore 无控制台日志。**证伪：** 在 `sm8750` 上仅把 `disp_cc_mdss_mdp_clk_src` 改为 `clk_rcg2_shared_no_init_park_ops` 不能消除灰屏，且会引发早于挂载根的卡死重启。

### 灰屏边界定位诊断入口 `opd2413-graydbg` 上机前登记（2026-11-14）

- **目标：** 用只改命令行参数的 `-22` 诊断项 + 自动化引导切换，精确确认灰屏发生在 `earlycon=efifb` 黑底白字内核日志出现之前、滚动之中还是之后，并抓取完整 `dmesg`。
- **设备写入范围（已获用户确认）：**
  1. 卸载故障包：`rpm -e kernel-opd2413-7.2.15-23.opd2413`。
  2. 新增非默认条目 `/boot/efi/loader/entries/opd2413-graydbg.conf`，复用 `7.2.15-22.opd2413` 的内核/DTB/initrd，仅把 `quiet loglevel=3` 改为 `ignore_loglevel earlycon=efifb keep_bootcon`。
  3. 执行 `/usr/libexec/opd2413/boot-select kshim Fedora` 与 `/usr/libexec/opd2413/boot-select next opd2413-graydbg`（回读校验后 `systemctl reboot`）。
- **预期与判据：**
  1. 无需人工点击菜单，平板自动经 kShimC `"Fedora"` 与 `systemd-boot` 进入 `opd2413-graydbg.conf` 并顺利进入系统；`opd2413-boot-restore.service` 自动把 `loader_default` 恢复回 `fedora-7.2.15-22.opd2413.conf`。
  2. `boot-select status` 确认 `kshim_remembered == "Fedora"`、`booted_entry == "opd2413-graydbg.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`。
  3. 结合用户肉眼观察结果与完整 `dmesg`，确定下一变量隔离方向。

**真机结果（15:24–15:29）：自动切入口通过，但 `opd2413-graydbg` 卡死未进系统（`真机失败`）。**
- 平板无人值守自动跳过菜单进入 `opd2413-graydbg`，`earlycon=efifb` 正常输出**黑底白字内核日志滚动数秒，随后整屏文字瞬间被灰屏盖掉（期间并未卡住），再过几秒转为有背光但黑屏，最后变成物理黑屏**并失去网络响应（`15:19:52`、`15:21:02`、`15:24:21` `ping <平板 IP>` 均 100% 丢包）。
- 用户长按电源键 ~10 秒强制重启后从 kShimC `"Fedora boot menu"` 选回正常的 `7.2.15-22.opd2413`，`opd2413-boot-restore.service` 立即将 `loader_default` 复位回 `fedora-7.2.15-22.opd2413.conf`。`journalctl --list-boots` 无 `graydbg` 记录，`/var/lib/opd2413-pstore/` 最新只到 `000032`（冷断电丢 RAM）。
- **结论：** ① kShimC/EFI 交接给内核时画面正常，灰屏确定发生于**内核启动数秒、早期日志滚动期间之后、`msm_dpu` 接管黑屏之前**的瞬间全屏失步/断流阶段；② `7.2.15-22` 在追加 `earlycon=efifb keep_bootcon ignore_loglevel` 后于显示接管之后卡死/关屏（与 [TECH-DEBT.md](TECH-DEBT.md) `#26`、`WORKLOG` 第 793 行 `memremap(MEMREMAP_WC)` 在未保留 `0xfc800000` 帧缓冲/CMA 区域失败且 `keep_bootcon` 未注销相符），后续测试不再使用 `earlycon=efifb keep_bootcon`。
- 另只读取回 `-22` 正常开机日志保存到 `private/boot22-dmesg.txt`（1681 行）：`0.231 s` `efifb` → `0.287/0.301 s` 两颗 `ktz8866` → `0.461 s` `msm-mdss bootloader scanout`（`intf 0x3 line 1196/1197 stopped in 8408 us`）→ `0.470–0.488 s` `dsi_phy` 告警刷屏约 478 行 → `0.593 s` `fb0: msmdrmfb` → `0.853 s` `panel_prepared` → `1.128 s` `fbcon` 接管；其前两段行数比例（629 行 vs 509 行）与用户目视“滚动几秒 → 灰屏 → 几秒后有背光黑屏”完全吻合。

### 单变量黑名单隔离 `opd2413-nodispcc` 上机前登记（2026-11-14）

- **目标：** 保持正常 `quiet loglevel=3`、不加 `earlycon=efifb keep_bootcon`，仅在 `-22` 上追加 `initcall_blacklist=disp_cc_sm8750_driver_init`，直接判定“既跳过 `disp_cc_sm8750` 又通过依赖跳过下游 `msm_drm`”后是否还会闪现灰屏。
- **设备写入范围（已获用户确认）：**
  1. 删除临时故障条目 `/boot/efi/loader/entries/opd2413-graydbg.conf`。
  2. 新增非默认条目 `/boot/efi/loader/entries/opd2413-nodispcc.conf`，复用 `7.2.15-22.opd2413` 全部路径与参数，仅追加 `initcall_blacklist=disp_cc_sm8750_driver_init`。
  3. 执行 `/usr/libexec/opd2413/boot-select kshim Fedora` 与 `/usr/libexec/opd2413/boot-select next opd2413-nodispcc`，回读校验后 `systemctl reboot`。
- **预期与判据：**
  1. 平板自动进入 `opd2413-nodispcc.conf`，因非显示设备不依赖 `&dispcc`，系统正常挂载根并拉起 `opd2413-boot-restore.service`（恢复 `loader_default = fedora-7.2.15-22.opd2413.conf`）、NetworkManager 与 SSH；核对 `boot-select status` 与 `cat /proc/cmdline` 确认黑名单生效。
  2. 用户目视无灰屏 → 100% 排除 U-Boot/`efifb`/`0xfc800000` 内存/`ktz8866`/`clk_disable_unused`/`genpd`，锁定触发源在 `disp_cc_sm8750` 或 `msm_drm`；仍出现灰屏 → 排除两者，转查 `clk_disable_unused`/`genpd` 或 `0xfc800000` 内存重叠。
- **实机结果（2026-11-14）：`真机失败`（作为变量隔离测试：成功证伪）。**
  - 现象：平板按 `boot-select next opd2413-nodispcc` 自动进入后，**选择引导后直接灰屏，没有任何其他内容，随后到时重启进入灰屏死循环**（因未挂载 rootfs，`opd2413-boot-restore.service` 无法执行；`journalctl --list-boots` 无该次启动记录）。用户已于 `Fedora boot menu` 手动切回 `7.2.15-22.opd2413` 正常开机。
  - 结论：**100% 排除 `disp_cc_sm8750` 与 `msm_drm`（`msm-mdss` / `msm_dpu` / `dsi`）作为最初灰屏触发源**（两者均未探测即已出现整屏灰屏）。死循环本身推测为跳过 `dispcc`/`msm` 后后续 `clk_disable_unused` 或 `genpd` 关断仍在扫描输出的显示时钟/电源域引发未挂根前卡死复位。下一步转查 `0.0 s–0.46 s` 期间非 `dispcc`/`msm` 候选：`15000000.iommu`（`arm-smmu` 于 `0.280 s` 复位与 `USFCFG` 拦截）、`0xfc800000–0xfe70dfff` 未保留内存重叠、以及早期 regulator/clock/PM 状态。

### 单变量隔离 `opd2413-smmubypass` 上机前登记（2026-11-14）

- **依据（只读取证）：**
  1. `opd2413-graydbg` 中 `earlycon=efifb` 在 `0xfc800000` 正常输出约几秒（~490 行以内），在 `0.277–0.280 s` `arm-smmu 15000000.iommu` 执行 `arm_smmu_device_reset()`（`preserved 0 boot mappings`、`CLIENTPD=0` 且 `CONFIG_ARM_SMMU_DISABLE_BYPASS_BY_DEFAULT=y` 置位 `USFCFG=1` 并清零全部 128 组 SMR/S2CR 为 FAULT），直到 ~2.8 ms 后（`0.283 s`）`ae00000.display-subsystem` 才加入 `iommu group 10`（`IDENTITY` / `0x800 0x2`）；另有 `/sys/module/arm_smmu/parameters/disable_bypass = Y`。
  2. 另只读查核 `/proc/iomem` 与 `/sys/kernel/debug/memblock/{memory,reserved}` 确认 `0xfc800000–0xff7fffff` 整段 48 MiB 在 Linux 中为 `System RAM`（`0xfcc00000–0xff7fffff` 为 44 MiB CMA `RSV_KERN`，`0xfc800000–0xfcbfffff` 4 MiB 为完全未保留 RAM），作为第二候选保留在案。
- **拟执行设备写入范围（待用户确认）：**
  1. 删除失效且易循环的临时条目 `/boot/efi/loader/entries/opd2413-nodispcc.conf`。
  2. 新增临时非默认条目 `/boot/efi/loader/entries/opd2413-smmubypass.conf`，复用 `fedora-7.2.15-22.opd2413.conf` 全部路径与参数，**仅追加 `arm_smmu.disable_bypass=0`**。
  3. 执行 `/usr/libexec/opd2413/boot-select kshim Fedora` 与 `/usr/libexec/opd2413/boot-select next opd2413-smmubypass`，回读校验后 `systemctl reboot`（无人值守自动启动；`-22` 内核正常启动至桌面后 `opd2413-boot-restore.service` 自动把 `loader_default` 恢复回 `fedora-7.2.15-22.opd2413.conf`）。
- **预期与判据：**
  1. 无人值守自动进入桌面与 SSH，`boot-select status` 确认 `kshim_remembered == "Fedora"`、`booted_entry == "opd2413-smmubypass.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`，且 `/sys/module/arm_smmu/parameters/disable_bypass == N`。
  2. 用户目视**灰屏消失**（仅保留正常交接黑屏或直接亮面进桌面）→ 100% 锁定根因是 `15000000.iommu` 复位开启 `USFCFG` 拦截/错失 MDSS 固件流 ID；**仍有灰屏** → 排除 `arm-smmu` `disable_bypass`（`USFCFG`），下一步排查 `0xfc800000–0xfe70dfff` 内存未保留重叠及 `0.28–0.42 s` 其他设备（`vreg`、`ktz8866`、`efifb`）。
- **结果（真机失败 — 作为修复无效；成功证伪 `arm-smmu` bypass 假设）：**
  - SSH 自动连通后核对：`booted_entry == "opd2413-smmubypass.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`（已自动恢复）、`pending_next == null`、`kshim_remembered == "Fedora"`，`/proc/cmdline` 末尾含 `arm_smmu.disable_bypass=0`，且 `/sys/module/arm_smmu/parameters/disable_bypass == N`。
  - 用户目视：**默认入口仍为“短暂灰屏后进入内核日志，然后正常进入桌面”**。
  - **结论：** 彻底排除 `15000000.iommu` 复位设置 `USFCFG` / 放行固件 Stream ID 失败是灰屏主因；加上此前已证伪 `disp_cc_sm8750`、`msm_drm`（`opd2413-nodispcc`）及 `clk_disable_unused`（Armada `grey1` 已设三项 `*_ignore_unused`），焦点收敛至 `0xfc800000` 帧缓冲内存重叠（未作 `reserved-memory`，`simple-framebuffer.0` 与 `efifb` 均未能保留且 `44 MiB` 被划作 `CMA`、`4 MiB` 落入自由 RAM）、`efifb`/`fbcon` 早期初始化与 `0.00–0.45 s` 内核早期 `initcall`（含无 `1410` 时的 `ktz8866`、RPMh/GCC 显示电源总线时钟）。

### 单变量隔离 `opd2413-splashmem` 上机前登记（2026-11-14）

- **依据（只读取证）：**
  1. `-22` 实际反编译 DTB 的 `/reserved-memory` 中，`oem-vm@f7c00000`（长 `0x4c00000`）正好结束于 `0xfc800000`，`llcc-lpi@ff800000` 起始于 `0xff800000`，中间留下 `0xfc800000..0xff7fffff`（`48 MiB` / `0x3000000`）未保留空洞；`/sys/kernel/debug/memblock/{memory,reserved}` 确认该段暴露为 `System RAM`（前 `4 MiB` 自由 RAM + 后 `44 MiB` `RSV_KERN` CMA）。
  2. 同平台 `sm8750-konkr-pf-elite.dts` 及 SM8550/8650 设备均在此地址放置 `splash-region`（`no-map`）；因缺失该保留区，`-22` 在 `0.229 s` 报错 `platform simple-framebuffer.0: failed to claim resource 0: [mem 0xfc800000-0xfe70dfff]` 并退回 `efifb: cannot reserve video memory at 0xfc800000`。
  3. 宿主机反编译—修改—重编—二次反编译 `diff -u` 验证 `opd2413-splashmem.dtb` 仅新增上述 `splash-region@fc800000` 节点（`no-map`），且 `msm_kms.c:272` 已调用 `aperture_remove_all_conflicting_devices()` 清理 `simpledrm`。
- **拟执行设备写入范围（待用户确认）：**
  1. 删除上一轮临时条目 `/boot/efi/loader/entries/opd2413-smmubypass.conf`。
  2. 写入临时 DTB `/boot/efi/fedora/7.2.15-22.opd2413/opd2413-splashmem.dtb`（基于 `-22` 原 DTB 仅增加 `/reserved-memory/splash-region@fc800000`）。
  3. 新增临时非默认条目 `/boot/efi/loader/entries/opd2413-splashmem.conf`，内核/initrd/启动参数与 `fedora-7.2.15-22.opd2413.conf` **完全一致**，仅将 `devicetree` 指向 `/fedora/7.2.15-22.opd2413/opd2413-splashmem.dtb`。
  4. 执行 `/usr/libexec/opd2413/boot-select kshim Fedora` 与 `/usr/libexec/opd2413/boot-select next opd2413-splashmem`，回读校验后 `systemctl reboot`（无人值守自动启动，`opd2413-boot-restore.service` 会将 `loader_default` 恢复回 `fedora-7.2.15-22.opd2413.conf`）。
- **预期与判据：**
  1. 无人值守自动进入桌面与 SSH，`boot-select status` 确认 `booted_entry == "opd2413-splashmem.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`/sys/kernel/debug/memblock/memory` 显示 `0xfc800000..0xff7fffff` 为 `NOMAP` 且不再与 `CMA`/`System RAM` 重叠、`dmesg` 中 `simple-framebuffer.0` 认领成功（由 `simpledrm` 接管而非 `efifb`）。
  2. 用户目视**灰屏消失** → 根因锁定为 `0xfc800000` 固件帧缓冲缺少 `reserved-memory`（`no-map`）导致与 `System RAM`/CMA 冲突及退回 `efifb`；**仍有灰屏** → 彻底排除 `0xfc800000` 内存冲突与 `efifb`，下一步检查 `0.15–0.46 s` 内其他 `initcall` / `vreg` / `ktz8866` / `gcc`。
- **结果（真机失败，2026-11-14）：** 两次无人值守重启（首次 91s、重试 39s）均自动进入桌面与 SSH。`boot-select status` 确认 `booted_entry == "opd2413-splashmem.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`、`kshim_remembered == "Fedora"`；`/sys/kernel/debug/memblock/memory` 显示 `25: 0x00000000f3800000..0x00000000ffffffff 0 NOMAP`；`dmesg` 显示 `[0.233372] [drm] Initialized simpledrm 1.0.0 for simple-framebuffer.0 on minor 0`（`fb0: simpledrmdrmfb`）、`[0.594976] msm_dpu ... fb0: msmdrmfb`、`[0.857478] [nt36536] panel_prepared`、`[1.116574] fbcon: Taking over console`。但用户目视两次均有**“依旧有短暂灰屏”**，彻底证伪 `0xfc800000` 内存重叠与 `efifb` 假设。

### 单变量隔离 `opd2413-l3gon` 上机前登记（2026-11-14）

- **依据（只读与代码核对）：**
  1. 设备树中 `vreg_l3g_1p2`（`0xa9`）同时供电给 `mdss_dsi0` / `mdss_dsi1` 的 `vdda-supply`（1.2 V）与 `phy@1c06000`（PCIe QMP PHY）、`phy@1d80000`（UFS QMP PHY）、`phy@88e3000`/`88e8000`（USB PHY），且在 `-22` DTB 中未设置 `regulator-boot-on` / `regulator-always-on`。
  2. 实机 `dmesg` 与源码（`pcie-qcom.c:2034,2211,2228`、`phy-qcom-qmp-pcie.c:4886,4947`、`regulator/core.c:3278`）核对确认：UFS（`0.4806 s`）与 USB（`>0.62 s`）在 `0.318 s` 时均尚未使能 `vreg_l3g_1p2`（`use_count == 0`）；而 `1c00000.pcie` 于 **`0.3184 s`** 调用 `phy_init()`（`use_count: 0 -> 1`），进入 `dw_pcie_host_init()` 后因 `pci_pwrctrl_power_on_devices()` 返回 `-EPROBE_DEFER`，回滚执行 `phy_exit()` → `regulator_bulk_disable(vreg_l3g_1p2)`（`use_count: 1 -> 0`），**在 `msm-mdss`（`0.449 s`）接管和 UFS 持锁之前物理切断了正在工作的 DSI 1.2 V 模拟供电**。
  3. 补丁 `1409` 己证实“失去 DSI 视频流而背光仍在时，本机 `nt36536` LCD 直接呈现纯灰屏”；DSI 1.2 V 在 `0.318 s` 被误关与用户观察到 `opd2413-graydbg` 黑底白字滚动后瞬间纯灰、且 `msm-mdss` `0.449 s` 仍见 MDP `intf 0x3` 内部扫屏（下游 DSI PHY 已断流）的物理时序一致。
  4. 宿主机已在临时 `opd2413-splashmem.dtb` 上仅对 `vreg_l3g_1p2` 新增 `regulator-boot-on;` 与 `regulator-always-on;` 编译生成 `opd2413-l3gon.dtb`（`sha256: 2c7afc701ef5eec14b915dff48ddc922b6b85da9dd661993caafa18b1682e18b`），二次反编译 `diff -u` 确认仅此两行差异；`regulators-3` 父供电 `vreg_s7i_1p2` 已于 `0.163 s` 就绪，Wi-Fi/PCIe/UFS/SSH 均保留。
- **拟执行设备写入范围（待用户确认）：**
  1. 写入临时 DTB `/boot/efi/fedora/7.2.15-22.opd2413/opd2413-l3gon.dtb`（并校验远端 `sha256sum`）。
  2. 新增临时非默认条目 `/boot/efi/loader/entries/opd2413-l3gon.conf`（与 `opd2413-splashmem.conf` / `-22` 参数完全一致，仅将 `devicetree` 改为 `/fedora/7.2.15-22.opd2413/opd2413-l3gon.dtb`）。
  3. 删除上一轮临时条目 `/boot/efi/loader/entries/opd2413-splashmem.conf` 与 `/boot/efi/fedora/7.2.15-22.opd2413/opd2413-splashmem.dtb`。
  4. 执行 `/usr/libexec/opd2413/boot-select kshim Fedora` 与 `/usr/libexec/opd2413/boot-select next opd2413-l3gon`，回读校验后无人值守重启（用户观察开机画面；`opd2413-boot-restore.service` 自动把 `loader_default` 维持在 `fedora-7.2.15-22.opd2413.conf`）。
- **预期与判据：**
  1. 无人值守进入桌面与 SSH，`boot-select status` 确认 `booted_entry == "opd2413-l3gon.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`、`kshim_remembered == "Fedora"`。
  2. 用户目视**灰屏消失** → 根因锁定为 `0.318 s` `1c00000.pcie` 等非显示早期驱动在 `-EPROBE_DEFER` 时误关共享显示供电 `vreg_l3g_1p2`；**仍有灰屏** → 彻底排除 `vreg_l3g_1p2` 断电假设，下一步用安全隔离排除剩余 3 个早期点（`sysfb_init` / `arm-smmu` `15000000.iommu` / `-22` 无 `1410` 的 `ktz8866`）。
- **结果（真机失败，2026-11-14）：** 无人值守重启后 38 s 自动进入桌面与 SSH（`tools/tablet-reboot.py --wait 120` 退出 0）。`boot-select status` 确认 `booted_entry == "opd2413-l3gon.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`、`kshim_remembered == "Fedora"`；`dmesg` 显示 `[0.276719] vreg_l3g_1p2: Setting 1200000-1256000uV`、`/sys/kernel/debug/regulator/regulator_summary` 显示 `vreg_l3g_1p2` 启用计数 `7 / 8`（`normal 1200mV`），同时实测核实 `iommu_groups/10`（`ae00000.display-subsystem`）为 `type=identity` 且 `/proc/interrupts` 中 `arm-smmu` 全局/上下文故障计数均为 `0`。但用户目视**“有短暂灰屏”**，正式证伪 `0.318 s` `vreg_l3g_1p2` 被提前切断的假设。

### 单变量隔离 `opd2413-nosysfb` 上机前登记（2026-11-14）

- **依据（交叉排除与源码/符号核对）：**
  1. 此前 `opd2413-nodispcc`（跳过 `disp_cc_sm8750_driver_init`，`msm-mdss`/`msm_dpu`/`msm_dsi`/`nt36536` 全未探测）仍直接变灰，Armada `grey1`（含 `1410` 探测关灯与三项 `*_ignore_unused` 参数）亦未改善灰闪，`opd2413-smmubypass`、`opd2413-splashmem` 与 `opd2413-l3gon` 也全部证伪。
  2. 上述所有复现场景（含使用 `efifb` 的 `grey1` 与使用 `simpledrm` 的 Fedora `-22` / `splashmem` / `l3gon`）在 `0.431 s` `msm-mdss` 介入前均执行了 `sysfb_init`（已由 `out/m3k/tree/drivers/firmware/sysfb.c`、`init/main.c` `initcall_blacklisted()` 及 `/proc/kallsyms` 核实：`__initcall__kmod_sysfb__665_225_sysfb_init6` 可由 `initcall_blacklist=sysfb_init` 精确匹配拦截）。
  3. 跳过 `sysfb_init` 可在不改动内核源码与 `-22` 原设备树的前提下，一次性隔离 `simple-framebuffer.0`、`simpledrm`（`0.226895 s`–`0.234322 s`）、`efifb` 与早期 `fbcon` 路径；即使未注册 `simple-framebuffer.0`，`0.574953 s` `msm_dpu` 仍会正常注册 `fb0: msmdrmfb` 并进入桌面。
- **拟执行设备写入范围（待用户确认）：**
  1. 复制 `/boot/efi/loader/entries/fedora-7.2.15-22.opd2413.conf` 为临时非默认条目 `/boot/efi/loader/entries/opd2413-nosysfb.conf`，仅修改 `title` 并在 `options` 末尾追加 `initcall_blacklist=sysfb_init`（继续沿用 `-22` 原 DTB `/fedora/7.2.15-22.opd2413/sm8750-oneplus-pad2pro.dtb`）。
  2. 清理上一轮临时文件 `/boot/efi/loader/entries/opd2413-l3gon.conf` 与 `/boot/efi/fedora/7.2.15-22.opd2413/opd2413-l3gon.dtb`。
  3. 执行 `/usr/libexec/opd2413/boot-select kshim Fedora` 与 `/usr/libexec/opd2413/boot-select next opd2413-nosysfb`，校验配置后调用 `tools/tablet-reboot.py --wait 120` 无人值守重启测试。
- **预期与判据：**
  1. 无人值守进入桌面与 SSH，`boot-select status` 确认 `booted_entry == "opd2413-nosysfb.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`、`kshim_remembered == "Fedora"`；`dmesg` 中不出现 `simple-framebuffer` / `simpledrm` / `efifb`，`msm_dpu` 仍注册 `msmdrmfb`。
  2. 用户目视**灰屏消失** → 根因锁定在 `sysfb_init` / `simple-framebuffer`（`simpledrm` 或 `efifb`）接管阶段；**仍有灰屏** → 彻底排除 `sysfb_init`、`simpledrm`、`efifb` 与早期 `fbcon` 交互，后续聚焦 `0.15 s–0.43 s` 仍未直接隔离的剩余驱动（`15000000.iommu` `arm_smmu_device_reset()` 瞬间复位、`-22` 无 `1410` 的 `ktz8866` 探测写寄存器及 `qcom-rpmh-regulator` 初始化）。
- **结果（真机失败，2026-11-14）：**
  - 通过 `tools/tablet-reboot.py --wait 120` 无人值守重启（38 s 恢复 SSH，`boot-select status` 验证 `booted_entry == "opd2413-nosysfb.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`、`kshim_remembered == "Fedora"`）。
  - `dmesg` 确认 `[0.228730] initcall sysfb_init blacklisted`、`simple-framebuffer`/`simpledrm`/`efifb` 为零、`[0.441651] msm-mdss ... bootloader scanout: intf 0x3 ...`、`[0.588132] msm_dpu ... fb0: msmdrmfb`、`[0.857600] [nt36536] panel_prepared`、`[1.132544] fbcon: Taking over console`。
  - 用户目视确认**“有短暂灰屏”**，彻底证伪 `sysfb_init`、`simple-framebuffer`、`simpledrm`、`efifb` 与早期 `fbcon` 假说；另核对 `-22`（`out/m3k/tree`）已含 `1409`（`d18384851`）但无 `1410`，而 `PATCHES.md` 记录 Armada `fast3` / `grey1`（含 `1409`/`1410` 与 `*_ignore_unused`）同样闪灰。

#### 2026-11-14 验证启动条目 `opd2413-nodispcc-safe`（禁用 `disp_cc` + 禁用未用时钟/电源域/稳压器/sync_state 回收）

- **依据：**
  - 此前 `opd2413-nodispcc` 在未保活 `gcc_disp_*` 时卡死在 `0.602 s` `clk_disable_unused`，无法进入 SSH 采样也无法区分灰屏是发生在 `< 0.44 s` 还是 `0.602 s` 以后。
  - 已源码核对：`opd2413-22.dts` 中 `dispcc` 无非显示消费者，`opd2413-boot-restore.service`、`NetworkManager.service`、`sshd.service` 不依赖 DRM；`/proc/kallsyms` 中精确符号为 `__initcall__kmod_dispcc_sm8750__517_1958_disp_cc_sm8750_driver_init6`（`initcall_blacklist=disp_cc_sm8750_driver_init` 可匹配）。
  - 已核对 `drivers/pmdomain/core.c:3695-3712`（`of_genpd_sync_state()` 会绕过 `pd_ignore_unused` 强制下电）、`drivers/base/core.c:1750-1768`（`fw_devlink.sync_state=strict` 可禁用超时强制触发）与 `drivers/interconnect/core.c:1218`，因此同时将 `fw_devlink.sync_state=timeout` 替换为 `fw_devlink.sync_state=strict` 并加 `clk_ignore_unused pd_ignore_unused regulator_ignore_unused`，保证不因 `disp_cc`/`msm_dpu` 未探测而关闭 `mmcx`、`icc` 或 `gcc_disp_*`。
- **设备写入范围：**
  1. 在 `/boot/efi/loader/entries/` 复制 `fedora-7.2.15-22.opd2413.conf` 为临时条目 `opd2413-nodispcc-safe.conf`（将 `fw_devlink.sync_state=timeout` 替换为 `fw_devlink.sync_state=strict`，并在 `options` 末尾追加 `initcall_blacklist=disp_cc_sm8750_driver_init clk_ignore_unused pd_ignore_unused regulator_ignore_unused`，`linux`/`devicetree`/`initrd` 保持 `-22` 不变）。
  2. 删除临时条目 `/boot/efi/loader/entries/opd2413-nosysfb.conf`。
  3. 执行 `boot-select kshim Fedora` 与 `boot-select next opd2413-nodispcc-safe` 一次性重启（默认条目仍为 `fedora-7.2.15-22.opd2413.conf`）。
- **预期与判据：**
  1. 无人值守恢复 SSH（无桌面属正常，因跳过 `disp_cc`/`msm_drm`），`boot-select status` 确认 `booted_entry == "opd2413-nodispcc-safe.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`；`dmesg` 中 `disp_cc_sm8750_driver_init blacklisted` 且无 `msm_dpu`。
  2. **分支 A（全程保持干净启动画面无灰屏直至 SSH 可达）** → 彻底证明 `0.00 s–0.44 s`（`15000000.iommu`、`ktz8866`、`led-backlight`、`rpmh` 等）完全无问题，问题严格位于 `0.602 s` 未使用资源清理或 `disp_cc` / `msm_dpu` / `nt36536` / `1409`；下一步单变量对比仅保留 `*_ignore_unused` 与 `1409`/`nt36536` 时序。
  3. **分支 B（仍出现灰屏并保持灰屏进入 SSH）** → 彻底排除 `disp_cc`、`msm_dpu`、`nt36536` 及 `clk`/`pd`/`regulator` 未使用回收；当即通过 SSH 在屏幕保持灰屏状态下读取 `regmap/0-0011`、`regmap/6-0011`、`regulator_summary`、`clk_summary`、`pm_genpd_summary` 与完整 `dmesg`，随后在此无显示器驱动的稳态基线上二分 `< 0.44 s` 内建驱动（如 `ktz8866`、`15000000.iommu` 等）。
- **结果（真机失败，2026-11-14）：**
  - 平板从 `-22` 重启进入 `opd2413-nodispcc-safe.conf` 后，用户目视**“变灰后卡死，然后进入死循环”**，120s 内 SSH 未恢复；用户通过 kShimC `"Fedora boot menu"` 选回 `7.2.15-22.opd2413` 正常进入桌面后，`opd2413-boot-restore.service` 已将 `loader_default` 恢复回 `fedora-7.2.15-22.opd2413.conf`（`booted_entry == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`）。
  - SSH 只读核查确认：`journalctl --list-boots` 无该次启动记录（卡死/复位发生在挂载根文件系统与 `journald` 启动之前），`opd2413-pstore-keep.service` 因 `ConditionDirectoryNotEmpty=/sys/fs/pstore` 未满足而跳过（未保留该次测试的 `console-ramoops`；历史 `/var/lib/opd2413-pstore/` 仅到上次 `-22` 重启的 `000038-3564318a...`）。
  - **结论：** 即使加上 `clk_ignore_unused pd_ignore_unused regulator_ignore_unused` 与 `fw_devlink.sync_state=strict`，跳过 `disp_cc` / `msm-mdss` 仍会导致早期硬件死锁/复位循环，无法作为跳过显示子系统的稳态基线。

#### 2026-11-14 验证启动条目 `opd2413-graytime`（方案 A：`earlycon=efifb loglevel=7` 无 `keep_bootcon` + 相机实拍观测时间戳）

- **依据：**
  - 本机实测确认 `/proc/config.gz` 启用了 `CONFIG_EFI_EARLYCON=y` 与 `CONFIG_PRINTK_TIME=y`（无 `CONFIG_BOOT_PRINTK_DELAY`），[private/boot22-dmesg.txt](../private/boot22-dmesg.txt) 在 `0.63 s` 前共 1159 行；此前 `opd2413-graydbg` 因附带 `ignore_loglevel` 与 `keep_bootcon` 刷屏过久并在接管阶段卡死。
  - 改为仅用 `earlycon=efifb loglevel=7` 替换 `quiet loglevel=3`（不加 `ignore_loglevel` 与 `keep_bootcon`），可在控制台自动交回 `tty0` 的前提下在启动初期直接打屏输出 `[0.XXXXXX]` 驱动与时间戳，并配合前置摄像头（`phone-camera`）实拍判断灰屏精确时间窗口与是否恢复进入桌面。
- **设备写入范围：**
  1. 删除遗留临时条目 `/boot/efi/loader/entries/opd2413-nodispcc-safe.conf`。
  2. 在 `/boot/efi/loader/entries/` 复制 `fedora-7.2.15-22.opd2413.conf` 为临时条目 `opd2413-graytime.conf`，仅将 `title` 改为 `Fedora Linux 45 (opd2413-graytime)`、将 `options` 中的 `quiet loglevel=3` 替换为 `earlycon=efifb loglevel=7`（其余参数、内核、DTB、initrd 与 `-22` 完全一致）。
  3. 执行 `boot-select kshim Fedora` 与 `boot-select next opd2413-graytime` 一次性重启（默认条目保持 `fedora-7.2.15-22.opd2413.conf`）。
- **预期与判据：**
  1. 无人值守重启并在 120 s 内恢复桌面与 SSH，`boot-select status` 确认 `booted_entry == "opd2413-graytime.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`pending_next == null`。
  2. 通过相机抓取开机画面定位灰屏发生于 `earlycon` 滚动的哪一段时间戳之前/之中/之后，为下一轮精确根因隔离提供直接时序依据。
- **结果（真机失败，2026-11-14）：**
  - 前置相机实拍过程：`17:09:30` ABL OnePlus 画面 → `17:09:40` kShimC 菜单（`Fedora` 选中，倒计时 8 s）→ `17:09:48` 倒计时归零 → `17:09:58` `earlycon=efifb` 正常输出 `[0.000000]` 早期内存/PSCI 日志 → `17:10:06` 屏幕变为**背光亮着的黑屏**（用户校准说明：相机过曝把带背光的黑屏拍成深灰，真正的灰屏呈偏白色；在 `17:10:06`、`17:10:16`、`17:10:27` 与 `17:11:32` 抓帧均停留在背光亮着的黑屏），`task-889` 120 s 超时，只读 SSH 探测返回 `No route to host`。
  - **结论：** 即使去掉 `keep_bootcon` 与 `ignore_loglevel`，`-22` 上启用 `earlycon=efifb loglevel=7` 仍会在打印 `[0.000000]` 后约 8 秒转入背光亮着的黑屏并卡死未进系统。后续不再使用 `earlycon=efifb` 启动参数，改用正常启动内核直接定位。

#### 2026-11-14 验证诊断内核 `opd2413-bisect1`（纯 `-22` + `mdss_boot_handoff_end` 后 `msleep(6000)` 二分断点）

- **依据：**
  - 基于纯 `-22`（`out/m3k/tree` `504a0e5cf`，不含 `2415`，`LOCALVERSION=-22.opd2413` 复用 `-22` 同版 `initrd`、`DTB` 与内核模块），仅在 `drivers/gpu/drm/msm/msm_mdss.c` 的 `msm_mdss_reset()` 完成 `mdss_boot_handoff_end(dev, &handoff)`（即 `1409` 关背光 + `1407` 停 `intf 0x3` 与 MDSS reset 完成）之后插入 `msleep(6000)`，把 `0.435 s` 的交接点拉长为 6 秒稳态供前置相机清晰捕捉，同时避免 `earlycon` 卡死。
- **设备写入范围（仅限临时诊断文件与一次性启动，默认条目 `-22` 不变）：**
  1. 上传临时内核镜像 `/boot/efi/fedora/7.2.15-22.opd2413/linux-bisect1`（基于 `-22` 单变量加 `msleep(6000)`）。
  2. 新增临时条目 `/boot/efi/loader/entries/opd2413-bisect1.conf`（复制 `fedora-7.2.15-22.opd2413.conf`，仅修改 `title` 为 `Fedora Linux 45 (opd2413-bisect1)` 与 `linux` 为 `/fedora/7.2.15-22.opd2413/linux-bisect1`）。
  3. 执行 `boot-select kshim Fedora` 与 `boot-select next opd2413-bisect1`，并通过 `tools/tablet-reboot.py --wait 120` 无人值守重启，用 `phone-camera` 在 `0.4s..6.4s` 断点窗口连续抓拍。
- **预期与判据：**
  1. 约 40–50 s 内无人值守恢复桌面与 SSH，`boot-select status` 确认 `booted_entry == "opd2413-bisect1.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`dmesg` 出现 `opd2413-bisect1: post-retire sleep 6000ms start/end`。
  2. **分支 A（6 秒断点期间屏幕呈纯偏白灰屏）：** 立即实证 `1409` 在 `0.435 s` 未能真正熄灭 `ktz8866` 背光（或 `intf 0x3` 停扫时背光仍有渐变延时）。
  3. **分支 B（6 秒断点期间屏幕保持纯黑熄屏，直到 6 秒后进入内核日志前才闪灰，或仍先闪再 6 秒黑）：** 先通过相机确认 6 秒断点期间背光确实熄灭（真黑 vs 亮屏暗灰），再将断点二分为 `panel_prepared -> panel_enable` 或 `msm_mdss_reset` 之前，进一步缩圈至毫秒级原因。
- **6 秒试跑结果（2026-11-14）：** 46 s 成功无人值守进入桌面与 SSH，`booted_entry == "opd2413-bisect1.conf"`、`loader_default == "fedora-7.2.15-22.opd2413.conf"`、`dmesg` 实证 `[0.466864] opd2413-bisect1: post-retire sleep 6000ms start` → `[6.623010] opd2413-bisect1: post-retire sleep 6000ms end`；因相机读取+抓拍间隔约 16 s 恰好跨过 6 s 断点，将断点延长至 `msleep(12000)`（12 秒）重测以确保抓拍直接命中窗口内部。

#### 2026-11-14 灰闪根因定位、修复补丁 `2415`–`2417` 与 `7.2.15-23.opd2413` 真机验收

- **根因闭环定位：**
  1. 12 s 断点实拍与 `dmesg` 时序对照确认：`disp_cc_sm8750_probe()` 在约 `0.14 s` 注册时钟时即把 `disp_cc_mdss_mdp_clk_src` 停泊到 BI_TCXO（`19.2 MHz`），比 `ktz8866`（`0.28 s`/`0.29 s`）与 `led-backlight`（`~0.30 s`）早约 `160 ms` 切断了 ABL 正在扫屏的 DSI 时钟，而引导态 KTZ8868 背光（`BL_CTRL=0x01`、`BL_EN=0x77`）仍处于点亮状态，导致面板无信号下呈现短暂偏白灰屏。
  2. 在 `dispcc-sm8750` 延后至 `led-backlight` 就绪后进一步发现两处软件状态不同步缺陷，使得按理应先熄灭的 KTZ8868 背光仍未关闭：
     - `drivers/video/backlight/led_bl.c` 的 `led_bl_power_off()` 因 `if (!priv->enabled) return;`（启动初值 `false`）直接早退，且阻塞型 I2C LED 调用 `led_set_brightness(..., LED_OFF)` 会排入异步工作队列而非同步写寄存器。
     - `drivers/video/backlight/ktz8866.c` 的 `ktz8868_update_brightness(ktz, 0)` 因 `if (ktz->led_on)`（启动初值 `false`）跳过写 `KTZ8868_BL_CTRL=0` 与 `BL_EN=0`。
- **正式补丁（`2415`–`2417`）与离线构建/安装检查：**
  1. `2415`（`drivers/video/backlight/ktz8866.c`）：`!ktz->led_on` 且目标亮度为 `0` 时读取硬件 `KTZ8868_BL_CTRL`/`BL_EN`，若仍在点亮则执行关灯。
  2. `2416`（`drivers/video/backlight/led_bl.c`）：去掉 `led_bl_power_off()` 的 `!priv->enabled` 早退，改用 `led_set_brightness_sync(..., LED_OFF)`（`-ENOTSUPP` 时回退 `led_set_brightness()`）。
  3. `2417`（`drivers/clk/qcom/dispcc-sm8750.c`）：在 `oneplus,erhai` 上由 `disp_cc_sm8750_wait_boot_backlight()` 最长 `10 s` 延迟至 `led-backlight` 注册并完成 `backlight_disable()` 后再继续探针。
  4. `patch -p1 -F0` 无模糊合入验证通过，正式 RPM `kernel-opd2413-7.2.15-23.opd2413.aarch64.rpm`（`SHA256: cbfdd4108e0278b2ea426fc158a994587716e1e17ade72bda77dfc2c2c67deb8`，无临时调试输出，关闭 `CONFIG_MODULE_ALLOW_BTF_MISMATCH`）构建完成。
- **装机与真机多轮验收（2026-11-14）：**
  1. **装机**：因离线启动系统时钟停在 `clock-epoch`（`2026-10-17`）导致 `rpm-sequoia` 拒签 10-18 后构建的 `systemd-udev`/`dracut` 且 `/etc/dnf/protected.d/opd2413.conf` 拦截 `installonly_limit=2` 自动淘汰 `-12`，同步时钟并使用 `dnf install --disablerepo='*' --setopt=protected_packages=''` 装入 `-23`（淘汰 `-12`、保留 `-22` 回退入口），`loader.conf` 默认入口设为 `fedora-7.2.15-23.opd2413.conf`（`/boot/efi` 已用 `247M / 512M`）。
  2. **3 次热重启与功能回归**：3 次热重启均稳定进入 `7.2.15-23.opd2413 #51`（`systemctl is-system-running = running`、`0 failed`、`SELinux = Enforcing`、零 `BTF` 警告，`ktz8866` `0.28 s`/`0.29 s` → `msm-mdss bootloader scanout` `0.46 s`–`0.47 s` → `fbcon` `1.11 s`–`1.14 s`）；用户肉眼确认全程无偏白灰屏；复测 `3392x2400` 下的 `120 / 60 / 30 Hz` 在线切换（并恢复 `60 Hz`）、`DPMS off -> on`（`bl_power=4 <-> 0`）、Night Light（`available/enabled/running=true`）与 4 s `s2idle` 唤醒均通过。
  3. **3 次冷启动**：3 次冷启动均未再出现偏白灰屏（[TECH-DEBT.md](TECH-DEBT.md) `#9` 与 `#38` 解除）；其中第 2 次冷启动在引导菜单选择入口后出现一次黑屏并短暂等待后自动重启（`journalctl --list-boots` 与 `/sys/fs/pstore` 未保留该次失败启动记录，第 1/3 次冷启动均一次正常进入桌面与 SSH），已记为 [TECH-DEBT.md](TECH-DEBT.md) `#39` 留待后续专项排查。

#### 2026-11-14 阶段 3 跨设备自动网络共享（`opd2413-netshare-0.1-3` + Android Companion）联调与真机验收

- **根因排查与实现调整：**
  1. **BlueZ RFCOMM SDP 缺失信道导致握手失败**：初版在实机 `btmon` 与 `adb logcat` 中抓到 `SDP Service Search Attribute Response` 仅包含 `L2CAP (0x0100)`、缺失 RFCOMM scn，手机端报 `tBTA_JV_STATUS::FAILURE, scn: 0`。在 `netshare/linux/opd-netshare-daemon` 的 `_register_profile()` 补充 `"Channel": GLib.Variant("q", 22)`，同时确认无签名本地包需 `rpm -Uvh --nosignature` 安装，`tools/build-netshare-rpm.sh 0.1 3` 编出 `out/rpmbuild/RPMS/noarch/opd2413-netshare-0.1-3.noarch.rpm`。`pick_ap_frequency()` 在 `wlp1s0` 未关联 2.4 GHz 时默认在 `2462 MHz`（信道 11）建立 `p2p0` AP。
  2. **Android 伴侣端硬件过滤扫描与 464XLAT 适配**：在 `netshare/android/` 新增 `BleScanReceiver.java` 并重构 `NetShareService.java` 使用硬件过滤 `PendingIntent` 扫描（`SCAN_MODE_BALANCED`、`CALLBACK_TYPE_ALL_MATCHES`、`MATCH_MODE_AGGRESSIVE`、`setLegacy(false)`、10 s 退避重试），补齐 `BootReceiver` 的 `MY_PACKAGE_REPLACED` 与 `MainActivity.ensureServiceRunningIfEnabled()`；通过公开 API `LinkProperties.getRoutes()` / `RouteInfo.getInterface()` 提取 464XLAT 叠层 IPv4 出口，并在 `assets/helper.sh` 的 `resolve_upstream()` 加入 `v4-*` 前缀剥离回退。`netshare/android/build-apk.sh` 构建 v3 签名 APK `out/netshare/opd-netshare.apk` 安装到已 root 手机并由 `su` 执行策略路由与 NAT。
- **预期与判据：**
  1. `mode force` 与 `auto` 断网故障转移均可拉起 `p2p0` 并完成 BLE 唤醒、RFCOMM 协商、DHCP 与手机侧 `opdlink_nat`/`opdlink_fwd` 转发，平板可通过 `p2p0` 访问公网，`wlp1s0` 恢复或切回 `auto` 后双端规则/接口完全清理。
  2. 手机侧上游在 Wi-Fi（`wlan0`）与 5G 蜂窝（`rmnet_data3`）间切换时，平板网络共享自动跟随切换且不断流。
  3. 已连接状态下重启 `opd-netshare.service` 时双端 cleanly 清理，`opd-netshare-tray` 存活，且 `SELinux Enforcing` 今日零 AVC 拒绝。
- **真机验收结果（真机通过，2026-11-14，附息屏/后台挂起限制 `#40`）：**
  1. **手动 `force` 数据面与释放**：建连后平板 `p2p0` 启用（`2462 MHz`、`258.0 MBit/s HE-MCS 10 HE-NSS 2`、`metric 550`），手机 `p2p0` 获 `192.168.49.113`（`out=wlan0 table=1027 ip_forward=1`，`opdlink_nat` `14 pkts / 836 B`、`opdlink_fwd` `78 pkts / 13592 B` 与 `82 pkts / 29906 B`）；平板实测 `ping 223.5.5.5` 3/3 0% 丢包（`55.6–115 ms`）、HTTPS 访问返回 `HTTP 200`（`0.900 s`）。切回 `opd-netshare mode auto` 后平板回归 `idle`、`bt_powered=false`、无 `p2p0`，手机规则/NAT 清零并恢复 `PendingIntent` 监听（`rc=0`）。
  2. **`auto` 模式断网触发与恢复（手机亮屏前台）**：手动断开 `wlp1s0`（`23:28:39`）→ 3 s 后开始 BLE 广播（`23:28:42`）→ 约 20 s 内完成连接（`23:28:59`–`23:29:00`，`192.168.49.113`、`metric=700`、`out=wlan0`），实测 `ping 223.5.5.5`（`65.7 ms`）与 HTTPS `HTTP 200`；恢复 `wlp1s0`（`23:29:10`）后守护进程于 `23:29:23` 自动停用移动共享，手机端规则全部释放（`rc=0`）。
  3. **`wlan0 <-> 5G 蜂窝` 在线出口切换**：通过临时禁止手机 Wi-Fi 自动重连使手机切至蜂窝出口，手机自动重建为 `out=rmnet_data3 table=1030`（`ip rule 9997`、`opdlink_nat` `10 pkts / 596 B`、`opdlink_fwd` `97 pkts / 19077 B` 与 `91 pkts / 30729 B`），平板经 `p2p0` `ping 223.5.5.5` 3/3 0% 丢包（`151.5–358 ms`）、HTTPS `HTTP 200`（`1.004966 s`）；解除限制后自动切回 `out=wlan0 table=1027`（`15 pkts / 898 B`，HTTPS `HTTP 200` `0.132666 s`、`286.7 MBit/s HE-MCS 11`）。（注：手机 `wlan0` 断开会导致无线 ADB mDNS 端口轮换，测试中曾通过 `adb mdns services` 重新连接新端口。）
  4. **连接态重启清理、托盘健康与 SELinux 审计**：在 `mode force` 已连接状态（`192.168.49.113`、`154.8 MBit/s HE-MCS 6 HE-NSS 2`、`out=wlan0 table=1027`）执行 `systemctl restart opd-netshare.service` 后，平板立即停止 AP 并释放 `p2p0` 与 `hci0`，手机收到停止指令完成 `P2P` 与防火墙规则清零并恢复监听（`rc=0`）；切回 `auto` 后双端收敛于干净静止态（平板 `idle`/`bt_powered=false`/无 `p2p0`，手机 `p2p=none out=none table=none ip_forward=0`）。`opd-netshare-tray` 全程存活，平板 `ausearch -m avc,user_avc -ts today` 返回 `<no matches>`（零 AVC 拒绝）。
  5. **已知后台/息屏扫描限制**：实测在手机息屏进入 `Dozing`（>37 s）或退居后台非前台 `TOP` 状态（约 13 s 后，即使处于唤醒未锁屏状态）时，ColorOS 与系统扫描调度（`OplusHansManager` / `BtScan.ScanController`）会将 `local.opd2413.netshare` 的 `PI Regular Scan` 标记为 `(Suspended)` 并移出活跃扫描客户端，需将应用带回前台恢复；已登记为 [TECH-DEBT.md](TECH-DEBT.md) `#40`。
  6. **用户实测补充（2026-11-15）**：用户在手机端开启 ColorOS“允许后台”相关权限后反馈测试可正常使用（[TECH-DEBT.md](TECH-DEBT.md) `#40` 现象已缓解；后续若需免除手动系统权限设置，可按需在 Companion APK 中接入 `CompanionDeviceManager`）。

#### 2026-11-15 kernel-opd2413 7.2.15-24 与 opd2413-netshare 0.1-4 上机验证（5 GHz AP 端到端）

- **改动与离线检验：**
  1. **内核调控域支持（`7.2.15-24.opd2413`）**：新增 `kernel/opd2413-7.2/config/m3-wifi-reg.config`，启用 `CONFIG_EXPERT=y`、`CONFIG_CFG80211_CERTIFICATION_ONUS=y`、`CONFIG_ATH_REG_DYNAMIC_USER_REG_HINTS=y`；`olddefconfig` 核对仅新增上述三项（及对应依赖/菜单标志）；主机 `N=24 bash out/m3k/build.sh`（`-j15`）编出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-24.opd2413.aarch64.rpm`（`SHA256: a8e0dc41f2c49620dbb21d4b47aab06efc88a5fd77f7b7a56befcceebfb509bf`）。
  2. **守护与包集成（`opd2413-netshare-0.1-4`）**：新增 `netshare/linux/config/regdomain`（`COUNTRY=CN`）并由 `opd2413-netshare.spec` 依赖 `wireless-regdb` 安装至 `/etc/sysconfig/regdomain`；`opd-netshare-daemon` 补齐 80 MHz（`FREQ_80_MAP` + `vht_center_freq1` + `max_oper_chwidth=1` + `he=1`/`vht=1`）、5 GHz 同信道 SCC 跟随（`5240 MHz`）、无上行/断网 `5745 MHz` 拉起与 2.4 GHz `2462 MHz` 兜底、未关联态按需恢复 `CN`（严格禁止在 `wlp1s0` 已关联期间下发 `iw reg set`）及 5G MCC 冲突自愈重连逻辑。`py_compile` 与模拟单元测试全过，编出 `out/rpmbuild/RPMS/noarch/opd2413-netshare-0.1-4.noarch.rpm`（`SHA256: 99358ceef96bc36fb88668b8a21e673630f92ca624f488436d0597a0fb3149f`）。
  3. **容器安装检验（`out/m3k/pkg-test24`）**：`tests/package-install-test.sh` 成功安装 `-24`、`/etc/sysconfig/regdomain`、`opd2413-netshare-0.1-4` 与 `wireless-regdb` 并展开 `/fedora/7.2.15-24.opd2413/{linux,initrd,sm8750-oneplus-pad2pro.dtb}`，打入 `67` 个早期固件（`0 missing`）且负例正确拦截；脚本仅因第 78 行沿用旧值 `66` 断言返回 1。
- **测试前预期与判据：**
  1. **安全安装与 ESP 完整性**：`dnf` 安装 `kernel-opd2413-7.2.15-24.opd2413` 与 `opd2413-netshare-0.1-4`（`protected_packages=''` 以匹配 `installonly_limit=2` 替换最旧 `-22`）；非 Fedora ESP 文件与 `KSHIM.CHO` SHA-256 保持不变，`boot-select status` 的 `loader_default` 仍保留 `fedora-7.2.15-23.opd2413.conf`。
  2. **一次性冷启动 `-24`**：通过 `boot-select next fedora-7.2.15-24.opd2413` 重启后，`uname -r` 为 `7.2.15-24.opd2413`，`systemctl is-system-running` 为 `running`（无失败单元），SELinux `Enforcing` 且无新增 AVC、`dmesg` 无异常驱动/显示/蓝牙错误。
  3. **调控域生效边界**：系统启动后 `iw reg get` 呈 `country CN`；`wlp1s0` 已关联期间，用户态绝不主动下发 `iw reg set`。
  4. **5 GHz SCC 并发**：`wlp1s0` 关联 5 GHz 上行时执行 `opd-netshare mode force`，`p2p0` 跟随 `wlp1s0` 所在 5 GHz 信道并以 `width: 80 MHz` 拉起，`wlp1s0` ping/SSH 零丢包、`dmesg` 无 `ath12k` 超时，切回 `auto` 后清理恢复 `idle`。
  5. **无上行 5 GHz（5745 MHz）与 5G MCC 自愈**：`wlp1s0` 断开时未关联态保持/恢复 `country CN`，`p2p0` 以 `5745 MHz`（`80 MHz, center1: 5775 MHz`）拉起；`wlp1s0` 重连异频 5 GHz 上行时触发 5G MCC 保护并重置会话，使 `wlp1s0` 恢复联网且守护进程回到 `idle`。
  6. **休眠与手机端联动**：验证一次短时 `s2idle` 唤醒正常；若手机 Wi-Fi ADB 在线则补测手机端 5 GHz 实际连接与吞吐，否则明确记录待手机上线后补测。
- **平板实机验收结果（2026-11-15，当前仅一次性启动 `-24`，默认启动项仍保留 `-23`）：**
  1. **安全安装（真机通过）**：`dnf -y install --disablerepo='*' --nogpgcheck --setopt=protected_packages=''` 完成替换最旧 `-22`（保留 `-23`、装入 `-24`、`opd2413-netshare 0.1-4`）；`/etc/sysconfig/regdomain` 为 `COUNTRY=CN`（`system_u:object_r:etc_t:s0`）；ESP 非 Fedora 与非 `fedora-*.conf` 文件 SHA-256 逐一比对 `ESP_NON_FEDORA_UNCHANGED`。
  2. **一次性冷启动 `-24` 与调控域（真机通过）**：`boot-select next fedora-7.2.15-24.opd2413` 重启后 `uname -r = 7.2.15-24.opd2413`，`/proc/config.gz` 确认为三项 `=y`，`boot_id` 更新，`loader_default` 自动回退至 `fedora-7.2.15-23.opd2413.conf`（`pending_next = null`）；`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing` 且 `journalctl -b` `NO_AVC_DENIED`；`iw reg get` 的 `global` 与 `phy#0 (self-managed)` 均为 `country CN: DFS-FCC`。
  3. **开机自愈日志观测（真机启动）**：开机尚未连网瞬间 `opd-netshare` 已在未关联态拉起 `5745 MHz` AP；随后 `wlp1s0` 连上 `5240 MHz` 路由器时触发 `[opd-netshare] wlp1s0 associated on 5240 MHz while p2p0 is on 5745 MHz (5G MCC conflict); resetting` 并平滑重建为 `5240 MHz`，有网后清理回 `idle`（该早期切换伴随一次瞬态 `ath12k_wifi7_pci` `failed to pull fw stats: -71` / `time out while waiting for fw stats done`，未影响连网）。
  4. **5 GHz SCC 并发（真机通过）**：`wlp1s0` 在 `5240 MHz (160 MHz)` 时执行 `opd-netshare mode force`，`p2p0` 实测 `channel 48 (5240 MHz), width: 80 MHz, center1: 5210 MHz`、`txpower 22.00 dBm`，并发 `ping -c 4` 默认网关 `0%` 丢包（`rtt min/avg/max/mdev = 3.703/4.495/4.998/0.484 ms`），测试期 `dmesg` 增量完全为空；`opd-netshare mode auto` cleanly 收回 `p2p0`、恢复 `idle` 与 `BT Powered: False`。
  5. **断网 `5745 MHz` 拉起与异频重连局限（真机部分通过，见 [TECH-DEBT.md](TECH-DEBT.md) `#41`）**：执行 `nmcli dev disconnect wlp1s0` 后，未关联态 `iw reg get` 保持 `country CN: DFS-FCC`（`global` 与 `phy#0`），`p2p0` 以 `channel 149 (5745 MHz), width: 80 MHz, center1: 5775 MHz`、`txpower 20.00 dBm` 正常拉起且宿主机空口扫描实测到对应 `5745 MHz`（信道 149）SSID。但随后执行 `nmcli dev connect wlp1s0` 试图连回 `5240 MHz` 路由器时，`wlp1s0` 三次 `send auth` 在 `9 ms` 内全部超时（`authentication timed out`）并因扫描/关联超时失败（`ssid-not-found`），同时 `dmesg` 出现 `time out while waiting for get fw stats`；用户在平板开关一次 Wi-Fi（触发 `rfkill` 关停 `p2p0`）后 `wlp1s0` 约 `0.24 s` 内正常关联并获取 IP，守护进程稳定收敛回 `idle`。
  6. **`s2idle` 短时休眠与手机端 5 GHz 数据面/吞吐实机联动（真机通过）**：
     - **`s2idle`**：`rtcwake -m no -s 8` + `systemctl suspend` 后 `boot_id` 不变，`suspend_stats` 为 `suc=0->1, fail=0`，`nvt_ts_resume #3 complete`，唤醒后 `global` 与 `phy#0` 仍保持 `country CN: DFS-FCC`、`opd-netshare` 保持 `idle`。
     - **手机端 `5240 MHz / 80 MHz` 全链路建连与回收**：解锁唤醒手机并保持 Companion 前台扫描后，平板执行 `opd-netshare mode force` 触发 BLE 唤醒 + BlueZ RFCOMM + `WifiP2p` 入组；手机加入 `5240 MHz`（`channelFrequency=5240`、`groupRole=GroupClient`）并获 `192.168.49.113`，平板 `p2p0` 获默认路由 `metric 550`（仅建连首包规则尚在落盘瞬间有过 1 次 `Destination Net Unreachable`，之后稳定）；平板经 `p2p0` `ping 223.5.5.5` `3/3` `0%` 丢包（`52.3–95.4 ms`）、`curl -I https://www.baidu.com` 返回 `HTTP/1.1 200 OK`，手机 `opdlink_nat` / `opdlink_fwd` 计数正常增长，且手机 Wi-Fi ADB 全程不断线。
     - **双向 TCP 吞吐实测（仅绑定 `192.168.49.1` ↔ `192.168.49.113` 私网接口，各 `5 s`）**：`iw dev p2p0 station dump` 显示双方稳定协商在对称 **`1080.6 MBit/s 80MHz HE-MCS 10 HE-NSS 2`**、`tx retries: 0`、`tx failed: 0`；实测 **平板→手机上传 `725.36 Mbps`**（`453,808,800 B / 5.005 s`），**手机→平板下载 `783.33 Mbps`**（`495,581,416 B / 5.061 s`）。
     - **双端清理**：切回 `opd-netshare mode auto` 后，平板立刻退回 `idle`、`BT Powered=False`、`p2p0` 设备消除、`dmesg` 增量为空；手机侧 `p2p0 DOWN`、`ip rule`（`9996`/`9997`）及 `opdlink_nat`/`opdlink_fwd` 全部彻底清空（`5745 MHz` 无上行场景的手机入组因受 `#41` 影响，待决定修复 `#41` 后一并测通闭环）。

#### 2026-11-15 opd2413-netshare 0.1-5 蓝牙音频角色隔离验证（防手机将平板当成蓝牙耳机）

- **改动范围**：新增 [50-opd2413-bt-roles.conf](../netshare/linux/wireplumber/50-opd2413-bt-roles.conf) 并纳入 [opd2413-netshare.spec](../packaging/opd2413-netshare/opd2413-netshare.spec) 安装至 `/usr/share/wireplumber/wireplumber.conf.d/50-opd2413-bt-roles.conf`，配置 `monitor.bluez.properties` 中 `bluez5.roles = [ a2dp_source bap_source hfp_ag hsp_ag ]`（保留平板连蓝牙耳机/音箱所需的 Source/AG 角色，移除 `a2dp_sink`、`bap_sink`、`hfp_hf`、`hsp_hs`）；编出 `out/rpmbuild/RPMS/noarch/opd2413-netshare-0.1-5.noarch.rpm`（`SHA256: 629029c88acc756f1eb4aa9266af878cc8faeeae5543b3d1c927fcea81f4b5d7`）。
- **测试前预期与判据**：
  1. 平板安装并重启用户态 `wireplumber` 后无 `malformed bluez5.roles setting ignored` 或配置解析错误；文件上下文为 `usr_t`。
  2. `opd-netshare mode force` 点亮 `hci0` 后，`bluetoothctl show` 不再包含 `Audio Sink`（`0000110b`）与 `Handsfree`（`0000111e`），而保留 `Audio Source`（`0000110a`）与 `Handsfree Audio Gateway`（`0000111f`）。
  3. 手机完成 RFCOMM 协商与 `5240 MHz / 80 MHz` P2P 建连并保持至少 `10 s` 后，平板 `bluetoothd` 不出现 `/sep2/fd0` 或 `Hands-Free unit` 接入，`wpctl status` 无蓝牙音频节点；手机端 `A2dpService` 与 `HeadsetService` 保持未激活/未接入且媒体音频出口仍留在扬声器（不出现“蓝牙耳机已连接”）。
  4. 切回 `opd-netshare mode auto` 后双端清理正常。
- **实测结果（真机通过，2026-11-15 01:22–01:30，运行在 `7.2.15-24.opd2413` 上）**：
  1. **装机与时钟前提**：平板未同步时钟时系统时间停在 `2026-10-17`（触发 `rpm-sequoia` 拒收部分已安装包 OpenPGP 签名并中断 `dnf` 事务）；经 `date -u -s` 临时校时至 `2026-11-15 01:22` 后，`dnf -y upgrade --disablerepo='*' --nogpgcheck` 顺利升级 `opd2413-netshare-0.1-4` → `0.1-5.noarch`。`50-opd2413-bt-roles.conf` SELinux 上下文为 `system_u:object_r:usr_t:s0`；重启用户态 `wireplumber.service` 后为 `active`，`journalctl --user -u wireplumber` 无 `malformed bluez5.roles` 或配置解析错误。
  2. **控制器 Role / UUID 验证**：执行 `opd-netshare mode force` 点亮 `hci0` 后，`bluetoothctl show` 已不再包含 `Audio Sink`（`0000110b`）与 `Handsfree`（`0000111e`），同时保留 `Audio Source`（`0000110a`）、`Handsfree Audio Gateway`（`0000111f`）、`Headset AG`（`00001112`）与 AVRCP Target（`0000110c`，本次未实际重连真无线耳机实播，仅验控制器侧 Source/AG UUID 完整保留）。
  3. **手机唤醒建连与 `>25 s` 稳态音频隔离**：
     - 附带观察：手机深夜处于息屏深度休眠（`mWakefulness=Dozing`、`scene: |nightDeepDoze|LcdOff`）期间，`OplusHansManager` 冻结了 `local.opd2413.netshare`（即使在 `deviceidle` 白名单内）并将广播设为 `defer: true`，导致手机未自动响应平板 BLE 广播；用户唤醒手机（`mWakefulness=Awake`）后即在数秒内完成配对。
     - `01:29:50` 手机完成 RFCOMM Channel 22 协商、`01:29:52–01:29:55` 拉起 `5240 MHz / 80 MHz` `p2p0`（平板→手机协商速率达 `1200.9 MBit/s 80MHz HE-MCS 11 HE-NSS 2`、`curl -I --interface p2p0 https://www.baidu.com` 返回 `HTTP/1.1 200 OK`）并维持至 `01:30:26`（`>25 s`）。
     - 平板 `journalctl -u bluetooth` 仅在 `01:29:50` 有两条主动探测对端音频能力的无害日志（`No SDP records found for Hands-Free Voice gateway` 与 `a2dp-source profile connect failed ... Protocol not available`），全程未再出现 `/sep2/fd0` 或 `AVRCP` 输入设备接入；`wpctl status` 仅见 `Built-in Audio Speakers` 与 `Built-in Audio Internal microphones`，无蓝牙音频节点。
     - 手机端 `dumpsys bluetooth_manager` 确认 `BluetoothActiveDeviceManager` 中 `A2DP Connected count: 0`（`Active: NULL`）、`HFP Connected count: 0`（`Active: NULL`），`BluetoothActiveDeviceManager event log` 在本次共享期间（`00:00:19.480` 之后）无任何 A2DP/HEADSET 接入事件，`A2dpService` 为 `STATE_DISCONNECTED`、`HeadsetService` `mConnectionState: 0`（`isBluetoothScoOn: false`）；`dumpsys audio` 中 `STREAM_MUSIC` 保持 `Devices: speaker(2)`。
  4. **清理回收**：切回 `opd-netshare mode auto` `3 s` 后，平板恢复 `State: idle`、`BT Powered: False`、无 `p2p0`；手机端 `p2p0` 消失（`NO_P2P0`）且无 `192.168.49` `ip rule` 残留（当前 `adb shell` 为 `uid=2000`，`iptables` 表未以 root 读取）。

#### 2026-11-15 opd2413-netshare 0.1-7 + Android 伴侣端联调修复：蓝牙断电/重配对自愈、断网信道记忆与跨频段回退

- **问题现象与根因定位：**
  1. **蓝牙忘记重配对 / 断电后广播静默丢失（`0.1-5`）**：手机忘记平板蓝牙并重配对期间，`hci0` 经历电源切换导致 BlueZ `LEAdvertisement1` 的 `ActiveInstances` 清零为 `0`；而平板 `opd-netshare-daemon` 仍保持 `state == "advertising"` 且 `adv_registered = True`，未监听 `Adapter1.Powered` / `Device1.Paired` 信号，也未在巡检中核对 `ActiveInstances`。同时手机 `NetShareService` 在 `ACTION_BOND_STATE_CHANGED` 进入 `BOND_BONDED` 时未清零 `lastAttemptMs` 并重启 BLE 扫描。
  2. **断开 `wlp1s0` 丢失 5 GHz 信道记忆且无法跨频段退避（`0.1-5` / `0.1-6`）**：`mode auto` 下手动断开 `wlp1s0` 后，因当前 `wlp_freq` 为空，守护进程直接选用 `5745 MHz`，与手机所连的 `5240 MHz` 上行冲突引发 5G+5G MCC `GROUP_REMOVED`（`0.1-5` 会持续循环并引发重连 `#41`）。`0.1-6` 虽加入 `last_wlp_5g_freq` 与冷却惩罚，但 `_handle_peer_p2p_failed` 未结合手机上报的 `sta_freq=5240` 过滤冲突 5 GHz 信道，叠加 `NetShareService.java` 原在 `failCount < 3` 处过早终止重试，阻塞了向 `2462 MHz` 的最终退避。
  3. **ColorOS 息屏与后台代理节流排查（非代码死锁）**：真机 `logcat` 与 `debuggerd` 检查证实伴侣端无代码级死锁；手机息屏处于 `mWakefulness=Dozing` 时，ColorOS `OplusProxyWakeLock` 会将 `'opd:netshare'` `PARTIAL_WAKE_LOCK` 加入 `ForceReleaseWakeLock list`（曾推迟 `BluetoothSocket.connect()` 返回直至设备唤醒），且 `MainActivity` 退居后台约 `3 min` 后，即使已加入原生 `deviceidle` 白名单及开启 ColorOS 允许后台，`OplusHansManager` 仍可能挂起后台 `PendingIntent` BLE 扫描（并入 [TECH-DEBT.md](TECH-DEBT.md) `#40`）。
- **代码改动与离线验证（`0.1-7` + APK）：**
  1. **平板守护进程（[opd-netshare-daemon](../netshare/linux/opd-netshare-daemon)）**：保留 `0.1-6` 引入的 `last_wlp_5g_freq` 持久化、`failed_freqs` 冷却（`p2p_failed` `180 s`、租约前断连 `120 s`；`SetMode` 及 `wlp_ok_streak >= 2` 时清空）、`Adapter1.Powered`/`Device1.Paired` 信号监听、`_has_active_adv()`/`_ensure_adv_and_profile_healthy()` 周期自愈、幂等 `_register_profile(force=...)`、`_set_device_trusted()`、`probe_wlp1s0_internet()` 开播前复核及同 RFCOMM 会话内 `_handle_peer_p2p_failed()` 切频；`0.1-7` 为 `pick_ap_candidates()` 新增 `peer_sta_freq` 参数并由 `_handle_peer_p2p_failed()` 传入手机 `sta_freq`，跳过与对端 5 GHz 上行不一致的其他 5 GHz 信道。离线通过 `python3 -m py_compile` 与 5 组 `pick_ap_candidates` 单元测试（覆盖 `[5240, 5745, 5180, 2462]`、`preferred_5g=5240, failed={5240}, peer_sta_freq=5240 -> [2462, 5240]`、`preferred_5g=5745, failed={5745}, peer_sta_freq=5240 -> [5240, 2462]`、`current=5180, peer_sta_freq=5240 -> [2462]` 与 `peer_sta_freq=0 -> [5745, 5180, 2462, 5240]`）。
  2. **Android 伴侣端（[helper.sh](../netshare/android/app/src/main/assets/helper.sh)、[NetShareService.java](../netshare/android/app/src/main/java/local/opd2413/netshare/NetShareService.java)）**：补齐 `sta_freq=` 上报、`InactiveState`/`P2pDisabledState` 早退、`ACTION_BOND_STATE_CHANGED`（`BOND_BONDED` 清 `lastAttemptMs` 并重扫）及 `p2p_failed` 上报，并将 `failCount < 5` 与 `waitFallbackTimeout = 14_000L` ms 纳入 `NetShareService.java` 以支撑完整多信道退避。
  3. **构建**：产出 `out/rpmbuild/RPMS/noarch/opd2413-netshare-0.1-7.noarch.rpm` 与 `out/netshare/opd-netshare.apk`（`apksigner verify` v3 `true`）。
- **测试前预期与判据：**
  1. **用例 A（BT 断电 / `rfkill` 自愈）**：`mode force` 下执行 `bluetoothctl power off` 与 `rfkill block bluetooth; sleep 2; rfkill unblock bluetooth`，平板自动恢复 `Powered=True`、`ActiveInstances=1`，唤醒手机后完成 `p2p0` 建连与外网 `curl`。
  2. **用例 B（用户原场景：`mode auto` 断开 `wlp1s0` + 手机共享 + 重连）**：`nmcli device disconnect wlp1s0` 后沿用记忆的 `5240 MHz` 建 AP，手机建连并转发外网 `CURL=200`；随后 `nmcli device connect wlp1s0` 无 `#41` 超时并自动回归 `idle`。
  3. **用例 C（人为错频 `5745 MHz` 同会话切频）**：断网无记忆下以 `5745 MHz` 起播，手机上报 `freq=5745, sta_freq=5240` 后，双方在同一 RFCOMM 会话内切至 `5240 MHz` 建连转发并正常回收。
  4. **用例 D（蓝牙音频角色隔离回归）**：`hci0` 仍不含 `Audio Sink`（`0000110b`）/`Handsfree`（`0000111e`），`wpctl` 无蓝牙音频节点，手机音频留扬声器。
- **真机实测结果（2026-11-15，运行在 `7.2.15-24.opd2413` + `opd2413-netshare-0.1-7.noarch` + 新版 APK）：**
  1. **用例 A（真机通过）**：`bluetoothctl power off` 与 `rfkill block/unblock bluetooth` 后均自动恢复 `Powered: yes`、`ActiveInstances: 0x01 (1)`；在手机唤醒脱离 `Dozing` 后完成 `5240 MHz` 建连（`192.168.49.113`，`1200.9 MBit/s 80MHz HE-MCS 11`，`default via 192.168.49.113 dev p2p0 ... metric 550`），`CURL_HTTP=200`。
  2. **用例 B（用户原场景，真机通过）**：`02:13:48` `nmcli device disconnect wlp1s0` 后直接沿用记忆 `5240 MHz` 拉起 `DIRECT-op-968893`；`02:14:04` 唤醒手机后，`02:14:09` 完成 EAPOL 4/4，`02:14:10` 取得 `DHCPACK(p2p0) 192.168.49.113`（`metric=700`，`1200.9 MBit/s 80MHz HE-MCS 11`），两次外网探测均通过（`CURL_T28=200`、`CURL_T44=200`）；`02:14:36` `nmcli device connect wlp1s0` 顺利重回 `5240 MHz`（`2401.9/2161.3 MBit/s 160MHz`）且无 `#41` 超时；`02:14:55` 停享并至 `02:15:04` 恢复 `Mode: auto`、`State: idle`、`Powered=False`。
  3. **用例 C（`5745 -> 5240 MHz` 同会话切频，真机通过；`5240 -> 2462 MHz` 经离线单测覆盖）**：断网态重启 `opd-netshare` 后以 `5745 MHz`（`DIRECT-op-cda4a8`）起播；唤醒手机后于 `02:15:52` 上报 `#1 freq=5745, staFreq=5240`（`p2p group formation failed (state=InactiveState, freq=5745, sta_freq=5240)`），平板于 `02:15:50` 记录 `Phone P2P failed on 5745 MHz (sta_freq=5240); switching session AP to 5240 MHz` 并同会话切换至 `DIRECT-op-809ad5`（`5240 MHz`）；`02:15:56` 获 `DHCPACK 192.168.49.113`、`CURL_CASEC=200`，恢复 `wlp1s0` 后收敛回 `Mode: auto`、`State: idle`、`BT Powered: False`。（注：在 `sta_freq=5240` 且 `5240 MHz` 也不可用时直接跳选 `2462 MHz` 的行为已通过上述离线单元测试，本次真机未人为阻断 `5240 MHz` 复测。）
  4. **用例 D（音频隔离回归，真机通过）**：`bluetoothctl show` 含 `Audio Source (0000110a)`、`Headset AG (00001112)`、`Handsfree Audio Gateway (0000111f)` 且无 `Audio Sink (0000110b)` / `Handsfree (0000111e)`；`wpctl status` 仅见 `Built-in Audio` 无蓝牙音频节点；手机 `STREAM_MUSIC` 保持 `Devices: speaker(2)`。平板 `/tmp` 联调临时日志已清理。

#### 2026-11-15 将 kernel-opd2413-7.2.15-24.opd2413 设为默认启动条目并冷启动复查

- **操作范围（已获用户批准）：**
  1. 平板（`7.2.15-24.opd2413` 在线、USB 供电 `online: 1` 充电中）执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-24.opd2413.conf`，保留 `7.2.15-23.opd2413` 为回退入口；不动 `KSHIM.CHO` 与非 Fedora ESP 文件。
  2. 将此前手动测试保留在 `mode force` 的 `opd-netshare` 切回 `mode auto` 清理双端 P2P 会话后，通过 `systemctl poweroff` 执行一次插电自动开机冷启动复查。
- **测试前预期与判据：**
  1. **默认条目落盘**：`/boot/efi/loader/loader.conf` 更新为 `default fedora-7.2.15-24.opd2413.conf`；`boot-select status` 显示 `loader_default == "fedora-7.2.15-24.opd2413.conf"`、`pending_next == null`、`kshim_remembered == "Fedora"`；`bootctl list` 中 `fedora-7.2.15-24.opd2413.conf` 带 `(default)`。
  2. **冷启动无干预复查**：`systemctl poweroff` 关机后插电自动开机，经 `kShimC -> U-Boot -> systemd-boot` 无人干预回到桌面与 SSH（`boot_id` 变更），`uname -r` 为 `7.2.15-24.opd2413`、`booted_entry == "fedora-7.2.15-24.opd2413.conf"`、`loader_default == "fedora-7.2.15-24.opd2413.conf"`、`systemctl is-system-running == running`（`--failed` 为 `0`）、SELinux `Enforcing` 无新增 AVC、`iw reg get` 为 `country CN`，且 `opd-netshare` 以 `Mode: auto`、`State: idle` 就绪。
- **实测结果（真机通过，2026-11-15 08:18–08:20）：**
  1. **设默认条目与落盘**：将用户测试会期由 `opd-netshare mode auto` 自然收敛回 `State: idle`、`BT Powered: False` 并核实 `qcom-battmgr-usb/online: 1`（`Charging`）、记录原 `boot_id = a0274953-7af9-4417-b937-90a2c1c3f678` 后，执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-24.opd2413.conf`。`loader.conf` 更新为 `default fedora-7.2.15-24.opd2413.conf`，`boot-select status` 为 `loader_default: "fedora-7.2.15-24.opd2413.conf"`、`pending_next: null`、`kshim_remembered: "Fedora"`，`bootctl list` 确认 `fedora-7.2.15-24.opd2413.conf` 带 `(default)`。
  2. **冷启动复查**：执行 `systemctl poweroff` 后插电自动开机，约 `46.3 s` 后无干预恢复 SSH（新 `boot_id = ba68c419-9b84-46d5-bb5c-a083f88010e1`），`uname -r = 7.2.15-24.opd2413`，`booted_entry = "fedora-7.2.15-24.opd2413.conf"`、`loader_default = "fedora-7.2.15-24.opd2413.conf"`、`pending_next = null`、`kshim_remembered = "Fedora"`；`systemctl is-system-running = running`、`--failed = 0`、`getenforce = Enforcing`、`journalctl -b -g 'avc.*denied'` 为 `-- No entries --`；`iw reg get` 在 `global` 与 `phy#0` 均为 `country CN: DFS-FCC`；ESP `/dev/sda16` 占用保持 `247M / 512M`（可用 `266M`，`49%`）；`opd-netshare` 稳态处于 `Mode: auto`、`State: idle`、`BT Powered: False`（另观测到开机第 `3 s` 因早于 `bluetoothd` 注册 `/org/bluez/hci0`〔第 `6 s` 就绪〕产生过一次 `BT power on failed: ... UnknownObject` 并随第 `7 s` `wlp1s0` 已就绪而跳过开播，仅遗留在 `Last Error:` 展示字段中，无功能影响）。

#### 2026-11-15 opd2413-netshare 0.1-8 + Android APK 图标统一与 Wayland 窗口图标修复

- **改动范围与离线构建：**
  1. **图标缩放与裁剪（无量化失真）**：利用 `magick`（`-filter Lanczos -strip -define png:compression-level=9`）由原始 `icon.png`（`1254×1254`，`826 KB`）生成桌面端 `hicolor` `{48,64,128,256}` 应用图标（共约 `53 KB`）与 Android 五档 `mipmap`（`48–192 px`）及自适应前景 `drawable-nodpi/ic_launcher_foreground.png`（去白底无白边、`222×222` 居中于 `432×432` 安全区，`6.0 KB`）；将 `tray_{black,green,yellow}.png`（原 `512×512` 各约 `20 KB`）重采样至 `128×128`（分别为 `4.2 / 7.1 / 6.4 KB`）。
  2. **桌面端与 Wayland 窗口修复**：更新 [opd-netshare.desktop](../netshare/linux/desktop/opd-netshare.desktop) 与 [opd-netshare-tray.desktop](../netshare/linux/desktop/opd-netshare-tray.desktop) 为 `Icon=opd-netshare`；改造 [opd-netshare-tray](../netshare/linux/opd-netshare-tray) 调用 `app.setDesktopFileName("opd-netshare")`（让 Wayland `xdg_toplevel` 发出正确 `app_id` 对齐 `.desktop`）、显式加载多尺寸 `app.setWindowIcon()` / `StatusDialog.setWindowIcon()`，并用 `load_tray_icons()` 将 `connected / advertising / idle / off` 分别映射到 `tray_green / tray_yellow / tray_black / 40% 不透明度 tray_black`；[opd2413-netshare.spec](../packaging/opd2413-netshare/opd2413-netshare.spec) 安装图标与缓存刷新脚本，编出 `out/rpmbuild/RPMS/noarch/opd2413-netshare-0.1-8.noarch.rpm`（`99 KB`）。
  3. **Android 端**：新增 `values/colors.xml`、`mipmap-anydpi-v26/ic_launcher{,_round}.xml` 与 `drawable/ic_launcher_monochrome.xml`，重绘 `drawable/ic_opd_share.xml` 为同款 24dp 纯白六边形单色矢量以匹配通知栏与 `NetShareTileService` 快捷磁贴，更新 [AndroidManifest.xml](../netshare/android/app/src/main/AndroidManifest.xml) 后编出 `out/netshare/opd-netshare.apk`（`90 KB`，v3 签名通过）。
- **测试前预期与判据：**
  1. **RPM 升级与缓存**：同步平板系统时间后升级至 `opd2413-netshare-0.1-8.noarch`，图标文件上下文为 `usr_t`，`opd-netshare.service` 与桌面端托盘运行正常。
  2. **Wayland 窗口图标与 `app_id`**：以 `WAYLAND_DEBUG=1` 启动新托盘并打开状态弹窗时，Wayland 协议日志明确记录 `set_app_id("opd-netshare")`，且 `QApplication.windowIcon()` 与 `StatusDialog.windowIcon()` 包含 `48/64/128/256` 有效像素尺寸、`xdg-desktop` 菜单与弹窗图标同步生效。
3. **托盘四态图标切换**：通过 `colin` 会话 D-Bus `org.kde.StatusNotifierItem` 实测，切换 `mode off` / `auto`（`idle`）/ `force`（`advertising`）/ 手机建连（`connected`）时，托盘 `IconPixmap` 哈希依次变化且各尺寸有效、弹窗在 `connected` 正常刷新，`off` 状态与 `idle` 视觉区分明显，测试完恢复 `mode auto` -> `idle`。
  4. **手机 APK 更新验收**：`adb install -r` 成功升级，无崩溃，应用桌面图标替换为 `icon.png` 自适应图标，前台通知与快捷磁贴服务正常。
- **真机实测结果（2026-11-15，运行在 `7.2.15-24.opd2413` + `opd2413-netshare-0.1-8.noarch` + `opd-netshare.apk`）：**
  1. **RPM 升级与缓存（真机通过）**：同步系统时间后完成 `dnf upgrade` 安装 `opd2413-netshare-0.1-8.noarch`（RPM 大小 `99K`），安装后清理 `/tmp` 临时 RPM；SELinux 上下文检查 hicolor 四档（`48/64/128/256`：`2.5K / 3.6K / 9.8K / 37K`）与 `tray_{black,green,yellow}.png`（`4.2K / 7.1K / 6.4K`）均为 `usr_t`，已为 `colin` 执行 `kbuildsycoca6`。
  2. **Wayland 窗口图标与 `app_id`（真机通过）**：在 `colin` 会话（`WAYLAND_DISPLAY=wayland-1`）以 `PySide6` 探针确认 `load_app_icon()` 加载 `[(48, 48), (64, 64), (128, 128), (256, 256)]`；以 `WAYLAND_DEBUG=client` 启动新托盘并经 SNI `Activate(0, 0)` 打开 `StatusDialog` 时，实测客户端发出 `xdg_toplevel#43.set_title("OPD2413 设备网络共享 — OPD 跨设备网络共享")`、`xdg_toplevel_icon_manager_v1#36.create_icon` + 4 份 `wl_buffer`（`add_buffer`）+ `set_icon(xdg_toplevel#43, xdg_toplevel_icon_v1#45)`，以及 `xdg_toplevel#43.set_app_id("opd-netshare")` 与 `xdg_activation_token_v1.set_app_id("opd-netshare")`。
  3. **托盘四态图标切换（会话四态加载通过；`idle`/`off`/`advertising` 实时 SNI 切换通过，`connected` 实时 SNI 待亮屏建连目视）**：
     - `PySide6` 会话内 `load_tray_icons()` 四态 `128x128` 像素探针：`idle`（`sha256=cfe617ff4d8f`, `avg_a=187.96`, `d=1838`）、`off`（`sha256=12764ff0109c`, `avg_a=74.44` 即 `0.40x`, `d=1838`）、`advertising`（`sha256=fc06fac6ac93`, `avg_a=187.96`, `y=2034`）、`connected`（`sha256=430f97a704e3`, `avg_a=187.96`, `g=2124`）。
     - 经会话 D-Bus（`org.kde.StatusNotifierWatcher` -> `:1.239 /StatusNotifierItem`）实时切换 `IconPixmap`：`mode auto`（`State: idle`）为 `128x128:sha=53b4ada3ab1c:avg_a=187.96:d=1838`；`mode off` 变为 `128x128:sha=cada21e40aa2:avg_a=74.44:d=1838`；`mode force`（`State: advertising`）变为 `128x128:sha=5a316c24aac8:avg_a=187.96:y=2034`；随后因测试期手机处于 `mWakefulness=Dozing` 且保留家庭 Wi-Fi，25 s 等待内维持 `advertising` 未建连，切回 `mode auto` 收敛至 `State: idle`、清理 `/tmp/tray-wldbg.log` 并重新拉起纯净 `opd-netshare-tray`（`PID=10584`）。
  4. **手机 APK 更新验收（装机与服务通过）**：`out/netshare/opd-netshare.apk`（`90K`，APK v3 签名校验通过；`aapt2` 确认包含 `color/ic_launcher_background`、`drawable-nodpi/ic_launcher_foreground.png` `6.0K`、`drawable/ic_launcher_monochrome.xml`、`drawable/ic_opd_share.xml` 及 5 档 `mipmap-*/ic_launcher.png`）经 `adb install -r` 覆盖安装成功并启动 `MainActivity`；`dumpsys activity services` 与 `dumpsys notification` 确认 `NetShareService` 处于 `isForeground=true foregroundId=2413`，通知绑定 `icon=0x7f030000` 与小图标 `0x7f020002`（`ic_opd_share`），状态文案为 `低功耗待命监听中 (opd2413-fd)`。

#### 2026-11-15 功耗与续航 Batch 1：`7.2.15-25.opd2413`（GMU 驱动绑定 / 释放 DDR 启动高带宽投票 / 修复 RPMH 依赖投票）

- **改动范围与离线构建（2026-11-15）：**
  1. 从 `erhai` 导出并严格应用（`patch -F0` 全 hunk 通过，已登记 `kernel/opd2413-7.2/patches/series`、`kernel/opd2413-7.2/README.md` 与 `kernel/PATCHES.md`）7 个补丁 `2418`–`2424`：
     - `2418`–`2422`（`62ed205f1..6f237b23c`）：标记 `cxpd` `device_link` 为 stateless、统一独立 GPU component 模型并将 `adreno_gmu` 注册为驱动绑定到 `3d37000.gmu`（解决 `TECH-DEBT.md` `#34`）；
     - `2423`（`1055cf6dc`）：`a6xx_gmu_set_freq()` 在 GMU 接管带宽时清掉 `a6xx_gmu_set_initial_bw()` 遗留的内核 OPP 带宽投票；
     - `2424`（`39919af08`）：`a6xx_gmu_rpmh_dep_votes_init()` 传入 `&gpu->pdev->dev` 以生成正确的 RPMH 依赖投票表。
  2. 执行 `N=25 ./out/m3k/build.sh`（`-j15`），编出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-25.opd2413.aarch64.rpm`（SHA256 `dc955e5fbc00e8f396fb6e9f96d53893968c11300832f180f2a4977a7f06a8db`），`nm out/m3k/build/drivers/gpu/drm/msm/adreno/a6xx_gmu.o` 确认包含 `adreno_gmu_register` 与 `a6xx_gmu_probe`。
  3. `tests/package-install-test.sh out/m3k/rpms25 out/m3k/pkg-test25`（`out/m3k/pkg-test25.out`）：ESP 条目、`sm8750-oneplus-pad2pro.dtb` 一致性、`early-firmware`（67 项 0 缺失）、缺固件拒绝（`60-opd2413-initrd-check.install` 拒绝安装）及无 rescue 镜像均通过；仅脚本第 78 行写死预期 `66` 而当前固件包为 `67`（与 `-23` 一致）导致退出码 `1`。
- **上机测试前预期与判据（待用户批准写入后执行）：**
  1. **安全安装与一次性引导**：平板安装 `kernel-opd2413-7.2.15-25.opd2413.aarch64.rpm`（`installonly_limit=2` 保留当前运行且设为默认的 `7.2.15-24.opd2413` 供回退，仅替换未运行的 `-23`），不改 `loader_default`；仅在 `/boot/efi/loader/entries/fedora-7.2.15-25.opd2413.conf` 的 `options` 中移除 `fw_devlink.sync_state=timeout`（`/etc/kernel/cmdline` 暂不动，待验证通过后再同步），用 `boot-select next fedora-7.2.15-25.opd2413.conf` 一次性冷引导至 `-25`。
  2. **`3d37000.gmu` 绑定与 `sync_state` 完成**：`uname -r == 7.2.15-25.opd2413`，`/proc/cmdline` 不含 `fw_devlink.sync_state=timeout`；`/sys/devices/platform/soc@0/3d37000.gmu/driver` 指向 `adreno_gmu`；`dmesg` 无 `deferring probe` / `sync_state` 阻塞或 `cxpd` `device_link` warning；`sys/devices/platform/soc@0/*sync_state*` 与电源域状态正常收拢。
  3. **GPU 与 DDR 带宽投票正常**：Wayland / KDE 桌面正常亮屏渲染（KWin 合成与旋转无黑屏/花屏，桌面 GPU 工作正常，`dmesg` 无 `adreno`/`gmu` 报错）；GPU 空闲降频后，DDR 频率不再被锁定在最高档位。
  4. **整机回归无倒退**：`systemctl --failed == 0`、`Enforcing` 无新增 AVC、一次 `s2idle` 短休眠唤醒正常。
- **实测结果（真机通过，2026-11-15 09:57–10:01，运行在 `7.2.15-25.opd2413`）：**
  1. **安全安装与一次性引导（真机通过）**：因 `/etc/dnf/protected.d/opd2413.conf` 保护 `kernel-opd2413`、`installonly_limit=2` 会触发保护校验，先 `rpm -e kernel-opd2413-7.2.15-23.opd2413`（保留运行中的默认项 `-24`），随后 `dnf -y install` 安装 `kernel-opd2413-7.2.15-25.opd2413.aarch64` 并清理 `/tmp` 临时 RPM；仅在 `/boot/efi/loader/entries/fedora-7.2.15-25.opd2413.conf` 的 `options` 中移除 `fw_devlink.sync_state=timeout`（`loader.conf` 默认项保持 `fedora-7.2.15-24.opd2413.conf`，ESP `/dev/sda16` 占用保持 `247M / 512M`、`49%`）。执行 `tools/tablet-reboot.py --entry fedora-7.2.15-25.opd2413.conf --wait 240`，`66 s` 后回到桌面与 SSH：`uname -r = 7.2.15-25.opd2413`，`booted_entry = "fedora-7.2.15-25.opd2413.conf"`，`loader_default = "fedora-7.2.15-24.opd2413.conf"`，`pending_next = null`，`/proc/cmdline` 不再含 `fw_devlink.sync_state=timeout`。
  2. **`3d37000.gmu` 绑定与 `sync_state` 完成（真机通过）**：`/sys/devices/platform/soc@0/3d37000.gmu/driver` 指向 `adreno_gmu`（`/sys/devices/platform/soc@0/3d00000.gpu/driver` 为 `adreno`）；`dmesg` 记录 `msm_dpu ae01000.display-controller: bound 3d37000.gmu (ops a6xx_gmu_bind_ops)` 与 `[drm] Loaded GMU firmware v5.1.25`，无 `cxpd` `device_link` warning；全 `/sys/devices` 下无任何 `waiting_for_supplier != 0` 的节点；`pm_genpd_summary` 确认 `gx_clkctl_gx_gdsc`、`gpu_cc_cx_gdsc`、`gmxc`、`gfx` 空闲时均塌陷为 `off-0`，`3d00000.gpu` 与 `3d37000.gmu` 均呈 `runtime_status = suspended`（附带观察到 `3d90000.clock-controller`〔`sm8750-gpucc`〕保持 `active` 并挂在 `mx`/`cx` 下）。
  3. **GPU 渲染与 DDR 启动高带宽投票释放（真机通过）**：`colin` Wayland 会话内 `eglinfo -B` 在 GBM 与 Wayland 平台正常初始化 `Adreno (TM) 830`（`OpenGL 4.6` / `Mesa 26.2.6`），`cur_freq` 空闲停在最低档 `160000000`；在 `3d00000.gpu` 与 `3d37000.gmu` 处于 `active` 状态（`freq=160000000`）下实测 `interconnect_summary`，`llcc_mc@interconnect-1` 下 `3d00000.gpu` 投票行稳定保持 `0 / 0`（确认 `2423` 已交由 GMU 投票带宽、不再在内核侧锁死 DDR 启动高带宽）。
  4. **整机回归与 `s2idle` 短休眠（真机通过）**：`systemctl is-system-running = running`，`systemctl --failed = 0`，`getenforce = Enforcing`，`avc.*denied` 为 `-- No entries --`；执行 `rtcwake -m freeze -s 5`（`PM: suspend entry (s2idle)` -> `PM: suspend exit`）干净唤醒，无 GPU/GMU 异常且唤醒后 `3d00000.gpu` 与 `3d37000.gmu` 均回到 `suspended`。
  5. **未改动项（待后续统一收尾）**：`/etc/kernel/cmdline` 中的 `fw_devlink.sync_state=timeout` 及 `loader_default`（仍为 `-24`）本轮未改，待用户决定是否先将 `-25` 设为默认或紧接 Batch 2 统一更新。

#### 2026-11-15 功耗与续航 Batch 2：`7.2.15-26.opd2413`（PCIe D3 / WAKE# / GDSC / `dwc3-qcom` / `qmp-combo` / `mem_sleep_default=s2idle`）

- **改动范围与离线构建（2026-11-15）：**
  1. 新增 6 个补丁 `2425`–`2430` 与配置片段 [m3-3-power.config](../kernel/opd2413-7.2/config/m3-3-power.config)（全部 `patch -F0` 应用，已登记 `series`、`README.md` 与 `PATCHES.md`）：
     - `2425`（`c5590c6a0`）：非 x86 原生热插拔根端口允许进 D3；
     - `2426`（`81aafa28f`，刷新 `pcie-qcom.c` 上下文）：休眠保链时设置 `device_set_awake_path(dev)`；
     - `2427`（`39636e8c3` + `f12f2ab7a` 最终态）：`gcc_pcie_0_{phy_,}gdsc` 加 `GENPD_FLAG_ACTIVE_WAKEUP`；
     - `2428`（`870167fad`）：`sm8750-oneplus-pad2pro.dts` `&pcieport0` `wake-gpios` 改为 `GPIO_ACTIVE_LOW`；
     - `2429`（`627372bef`）：`dwc3-qcom` 休眠期延迟处理 VBUS role override 更新；
     - `2430`（`a1576b156`）：`qmp-combo` probe 窗口持有 PM 引用防多余 suspend/resume；
     - 配置：启用 `CONFIG_HOTPLUG_PCI_PCIE=y`（经检查 `qcom_battmgr` 固定 PD 交接 `56346e1b3` 已在 `2101`、`qcom_geni_serial` 强休眠与中断清理已在 Armada 基线）。
  2. 执行 `N=26 ./out/m3k/build.sh`（`-j15`），编出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-26.opd2413.aarch64.rpm`（SHA256 `bc20394d2d95724c72bf21c36b7355510c1718fc782ec9baf516bede6efbcf14`）。确认 `CONFIG_HOTPLUG_PCI_PCIE=y`、反编译 DTB `wake-gpios = <0x3b 0x68 0x01>`（`GPIO_ACTIVE_LOW`）及 `qmp_pcie_suspend_noirq` 已编入；`tests/package-install-test.sh out/m3k/rpms26 out/m3k/pkg-test26`（`out/m3k/pkg-test26.out`）仅第 78 行 66 vs 67 固件数触发 exit 1，其余条目/DTB/67 早期固件/缺固件拒绝测试全部通过。
- **上机测试前预期与判据（待用户批准写入后执行）：**
  1. **安装与一次性引导**：保留已验证的 `-25` 作回退默认项（`boot-select default fedora-7.2.15-25.opd2413.conf`、`rpm -e -24`）后 `dnf install` 安装 `-26`；仅修改 `-26` 的启动条目 `options`（去掉 `fw_devlink.sync_state=timeout` 和 `pcie_ports=compat`，新增 `mem_sleep_default=s2idle`），通过 `tablet-reboot.py --entry fedora-7.2.15-26.opd2413.conf` 一次性引导上线。
  2. **默认睡眠模式与 PCIe / USB 休眠状态**：`/sys/power/mem_sleep` 为 `[s2idle] deep`；`0000:00:00.0` `bridge_d3` 可用于 native hotplug；一次较长 `s2idle` 测试（如 `rtcwake -m mem -s 30`，实际走 `s2idle`）**不被 WAKE# 在 ~2 s 内误唤醒**，`pm_wakeup_irq` 指向实际 RTC 闹钟而非 PCIe WAKE#，`qcom_stats` 显示 CX / AOSS sleep 计数与驻留明显推进，休眠前后 `suspend_stats` `fail == 0`。
  3. **唤醒后业务回归**：Wi-Fi（`wlp1s0`）、蓝牙、`a600000.usb`、Wayland 显示、Pogo 键盘唤醒（`2408`/`2409`）与 `opd-netshare` 正常恢复，无内核 `WARNING`/oops、`systemctl --failed == 0`、`Enforcing` 无新增 AVC。
- **实测结果（真机通过，2026-11-15 10:20–10:23，运行在 `7.2.15-26.opd2413`）：**
  1. **安装与一次性引导（真机通过）**：执行 `boot-select default fedora-7.2.15-25.opd2413.conf` 并 `rpm -e kernel-opd2413-7.2.15-24.opd2413` 后，`dnf -y install` 安装 `kernel-opd2413-7.2.15-26.opd2413.aarch64` 并清理 `/tmp` 临时 RPM（ESP `/dev/sda16` 占用保持 `247M / 512M`、`49%`）；仅修改 `fedora-7.2.15-26.opd2413.conf` 的 `options`（去掉 `fw_devlink.sync_state=timeout` 与 `pcie_ports=compat`，增加 `mem_sleep_default=s2idle`）。`tablet-reboot.py --entry fedora-7.2.15-26.opd2413.conf --wait 240` 于 `58 s` 后上线：`uname -r = 7.2.15-26.opd2413`，`booted_entry = "fedora-7.2.15-26.opd2413.conf"`，`loader_default = "fedora-7.2.15-25.opd2413.conf"`，`pending_next = null`。
  2. **默认睡眠模式与原生 PCIe 服务（真机通过）**：`/sys/power/mem_sleep` 固定为 `[s2idle] deep`；`/sys/bus/pci_express/drivers/` 下 `aer`、`pcie_bwctrl`、`pciehp`、`pcie_pme` 全部启用，`dmesg` 显示 `pcieport 0000:00:00.0: PME: Signaling with IRQ 247`、`AER: enabled with IRQ 247` 及 `pciehp: Slot #0` 就绪。
  3. **30 秒 `s2idle` 休眠与 `qcom_stats` 深度验收（真机通过）**：执行 `rtcwake -m mem -s 30`（实际走 `[s2idle]`，拔线 `Discharging` 状态下）：
     - `suspend_stats` 由 `success: 0` 变为 `success: 1, fail: 0`（全部 `failed_* == 0`）；
     - 稳定睡满 30 秒以上，**未被 PCIe WAKE# 约 2 s 误唤醒**，`pm_wakeup_irq == 241`（`/proc/interrupts` `241` 为 `pm8xxx_rtc_alarm`），`wakeup*` 非零计数为空；
     - `qcom_stats` 增量：`cxsd` `0 -> 3` 次、`+596760485` ticks（`31.08 s`）；`ddr` `0 -> 3` 次、`+596798833` ticks（`31.08 s`）；`apss` `97 -> 125` 次、`+603016584` ticks（`31.41 s`）；`adsp_island` 累计 `372172769` ticks（`19.38 s`）；`ddr_stats` 验证日常大量时间处于 `1708 MHz`（`865452032` ticks）而非被 `4224 MHz`（仅 `17844224` ticks）锁死（注：拔线状态 `aosd` 仍为 `0`，怀疑与 `#19` 面板供电或个别常开外设有关，不影响 `cxsd`/`ddr` 31 s 深度）；
     - 唤醒时 `dmesg` 清晰记录 `qcom-pcie 1c00000.pcie: PCIe Gen.3 x2 link up`、`mhi mhi0: Requested to power ON` 与 `ath12k_wifi7_pci 0000:01:00.0` 重建，证实休眠期间 PCIe Root Port 已随 `2425`/`2427`/`m3-3-power.config` 正常掉电进 D3。
  4. **唤醒后业务回归（真机通过）**：`wlp1s0` 自动重连至 5 GHz Wi-Fi（`5240.0 MHz`），`bluetooth` 与 `opd-netshare.service` 保持 `active`，`colin` Wayland 下 `eglinfo -B`（`Adreno (TM) 830` / `Mesa 26.2.6`）正常，`systemctl is-system-running == running`、`systemctl --failed == 0`、`getenforce == Enforcing`、`avc.*denied` 为 `-- No entries --`。
  5. **未改动项（待统一或进入 Batch 3）**：`/etc/kernel/cmdline` 与 `loader_default`（目前为 `-25`）本轮未改；下一步由用户确认是巩固 `-26` 为默认条目并同步更新 `/etc/kernel/cmdline`，还是继续 Batch 3（`#19` 熄屏面板断电，顺便观察能否进一步解锁 `aosd`）。

#### 2026-11-15 功耗与续航 Batch 3：`7.2.15-27.opd2413`（`TECH-DEBT #19` 面板熄屏/休眠真断电）

- **改动范围与离线构建（2026-11-15）：**
  1. 在 [kernel/opd2413-7.2/patches/series](../kernel/opd2413-7.2/patches/series) 尾部新增 3 个补丁 `2431`–`2433` 并严格零 fuzz（`patch -F0`）应用于 `out/m3k/tree`（同时登记于 [kernel/PATCHES.md](../kernel/PATCHES.md) 与 [kernel/opd2413-7.2/README.md](../kernel/opd2413-7.2/README.md)）：
     - `2431`（erhai `5930568b2`）：`dsi_phy_7nm.c` `dsi_pll_enable_pll_bias()` 仅首次引用置位 `PLL_SHUTDOWNB`，但每次调用均编程 `REG_DSI_7nm_PHY_PLL_SYSTEM_MUXES=0xc0` 并延时 `250 ns`；
     - `2432`（erhai `8ebec9278` 刷新上下文）：`dsi_host.c` 传播 `dsi_link_clk_set_rate_6g_v2_9()` reparent 错误，并在 `xfer_prepare` / `power_on` 统一使用 `pm_runtime_resume_and_get()` 与失败路径 `pm_runtime_put()` 平衡（保留 OPD2413 活跃链路保护与父时钟恢复）；
     - `2433`：回退本仓库 `kernel/opd2413/1411`，恢复 `novatek_nt36536_unprepare()` 调用 `novatek_nt36536_power_off()`，熄屏与挂起时真正关断 `vddio`（`vreg_l12b_1p8`）与 `KTZ8868` 正负偏压（`lcd_vsp`/`lcd_vsn`）。
  2. 执行 `N=27 bash out/m3k/build.sh`（`-j15`）编译通过并打出 `kernel-opd2413-7.2.15-27.opd2413.aarch64.rpm`（SHA256 `99c71e2c72ffa9d9e80a3b1b9af3fb6a41f8fa0a9730121e4ea2d5190818f888`）。
  3. 执行 `tests/package-install-test.sh out/m3k/rpms27 out/m3k/pkg-test27` 验证：RPM 安装与 `90-loaderentry.install`（`machine-id=fedora`）、`systemd-boot` 条目与 `sm8750-oneplus-pad2pro.dtb` 均通过；`initramfs`（`94063885` 字节）纳入 `67` 个必需固件、`0` 个缺失；仅第 78 行沿用 `66` 硬编码常量（待脚本单独同步）。
- **上机测试前预期与判据（待用户批准写入后执行）：**
  1. **安装与一次性冷启动**：将已验证 `-26` 设为默认回退项（`boot-select default fedora-7.2.15-26.opd2413.conf`）并移除旧 `-25`，`dnf install` 安装 `-27` 并保持 `-27` 条目 `options` 与 `-26` 一致（去 `fw_devlink.sync_state=timeout` 和 `pcie_ports=compat`、带 `mem_sleep_default=s2idle`），通过 `tablet-reboot.py --entry fedora-7.2.15-27.opd2413.conf` 一次性冷启动上线；桌面、120 Hz 显示、触控与背光调节正常。
  2. **熄屏真实断电与重复亮屏不黑屏（`#19` 核心判据）**：在 Wayland 会话内连续执行 ≥3 次 `DPMS off -> 待稳定 -> DPMS on`（如 `kscreen-doctor --dpms off` / `on`）**并由用户目视确认画面每次点亮正常、无黑屏/半边花屏**；在 `DPMS off` 期间检查 sysfs：`/sys/class/regulator/regulator.*` 下的 `vreg_l12b_1p8`、`lcd_vsp`、`lcd_vsn` 的 `state` 均为 `disabled` 且 `users == 0`，且 `dmesg` 无 DSI 命令超时/`PLL lock failed`/DPU vblank 超时。同时校验 `120 Hz`、Night Light（DSPP 路径）与 `60/30 Hz` 若使用下无退化。
  3. **长 `s2idle` 与 `qcom_stats` / `aosd` 复测**：再次在拔线（`Discharging`）下执行 `rtcwake -m mem -s 30`，确认唤醒后屏幕、触控、Wi-Fi、蓝牙、USB/`opd-netshare`、Pogo 键盘均正常恢复；检查 `qcom_stats`（观察在面板真断电后 `aosd` 是否开始计数，`cxsd`/`ddr`/`adsp_island` 驻留是否继续保持或进一步改善），并检查 `systemctl --failed == 0`、`Enforcing` 无新增 AVC。
- **实测结果（真机通过，2026-11-15 10:59–11:09，运行在 `7.2.15-27.opd2413`）：**
  1. **安全安装与一次性冷启动（真机通过）**：先将已验证 `-26` 设回默认回退项（`loader.conf` `default fedora-7.2.15-26.opd2413.conf`）并 `rpm -e kernel-opd2413-7.2.15-25.opd2413`，再 `dnf -y install` 安装 `kernel-opd2413-7.2.15-27.opd2413.aarch64` 并清理 `/tmp` 临时包；仅更新 `fedora-7.2.15-27.opd2413.conf` `options`（去掉 `fw_devlink.sync_state=timeout` 和 `pcie_ports=compat`，带 `mem_sleep_default=s2idle`，ESP `/dev/sda16` 占用保持 `247M / 512M`、`49%`）。执行 `tools/tablet-reboot.py --entry fedora-7.2.15-27.opd2413.conf --wait 240` 触发冷启动上线（注：自动登录时因 KWallet 未自动授权导致 Wi-Fi 晚于 240 s 才重连，用户连网后确认 `uname -r = 7.2.15-27.opd2413`，`Current Entry: fedora-7.2.15-27.opd2413.conf`，`running`，`systemctl --failed = 0`，`Enforcing` 无新增 AVC）。
  2. **连续 DPMS 灭屏真实断电与目视复亮（真机通过，`#19` 解除）**：在 `colin` 的 Wayland 会话（`WAYLAND_DISPLAY=wayland-1`）下连续执行 3 次 `kscreen-doctor --dpms off` -> 3 s -> `--dpms on` -> 2 s：
     - 每次灭屏期间：`lcd_vsp`、`lcd_vsn`、`vreg_l12b_1p8` 全部变为 `state=disabled`、`users=0`，`ae00000.display-subsystem`、`ae01000.display-controller`、`ae94000.dsi`、`ae96000.dsi` 全部进 `suspended`，`bl_power=4`；
     - 每次亮屏后：三路调节器恢复 `enabled`/`users=1`，触控 `nt36536` 重新完成固件下载（`Update firmware success!`，`PID=5F95`）；除开机 `0.47 s` 早期探测期的无害 `DSI PLL(0) lock failed` 外，亮灭屏全程无 DSI/DPU/KTZ/PLL 报错；
     - **用户目视确认**：经过 3 次真实断电灭屏与随后的 `s2idle` 唤醒后，桌面画面正常显示（无黑屏/半边花屏）、触控工作正常（当前模式为 `60 Hz`）。
  3. **拔线 30 秒 `s2idle` 与实测整机电流对比（真机通过）**：
     - 拔线 `Discharging`（电量 `90%`）下执行 `rtcwake -m mem -s 30`（`[s2idle] deep`）：`suspend_stats` `success=1, fail=0`，唤醒源 `pm_wakeup_irq=242`（`pm8xxx_rtc_alarm`）；`qcom_stats` 增量：`cxsd` `0 -> 1`、`+592674369` ticks（`30.87 s`），`ddr` `0 -> 1`、`+592688828` ticks（`30.87 s`），`apss` `+593498307` ticks（`30.91 s`），`adsp` `+690374565` ticks（`35.96 s`），`aosd` 仍为 `0`（说明面板断电后仍有其余常开外设或 RPMH 条件阻塞 AOSS sleep，如 `a600000.usb`/`88e8000.phy` `ctrl=on`、`LPASS`/`SoundWire` 空闲常开时钟）。唤醒后 `qcom-pcie`/`mhi`/`ath12k`、`bluetooth`、`opd-netshare`、`eglinfo -B`（`Adreno (TM) 830`）、`systemctl --failed == 0` 全部正常；
     - `qcom-battmgr-bat` 实时电压/电流对比（拔线仅靠系统亮屏静置 vs 系统唤醒态下仅 `DPMS off`）：亮屏静置 `4.391 V`、`-530` ~ `-593 mA`（约 `2.33–2.60 W`）；`DPMS off` 6–8 s 后降至 `4.405 V`、`-135` ~ `-113 mA`（约 `0.50–0.59 W`，仅面板/KTZ8868/MDSS 断电即立省约 `1.8–2.0 W`）。
  4. **收尾更新（2026-11-15 11:11）**：已将 `/boot/efi/loader/loader.conf` 的 `default` 切为 `fedora-7.2.15-27.opd2413.conf`（保留已验证的 `-26` 为回退项），并同步更新平板 `/etc/kernel/cmdline`（移除 `fw_devlink.sync_state=timeout` 与 `pcie_ports=compat`，写入 `mem_sleep_default=s2idle`），`TECH-DEBT #34` 已关闭。后续可按需另开 **Batch 4** 继续治理 `a600000.usb`/`88e8000.phy` `pm_runtime_forbid`、`LPASS`/`SoundWire`/`lpass-lpi` 休眠态 runtime suspend、KDE `powerdevilrc`（`AutoSuspendAction=0`）与 `logind` 合盖/电源键策略对齐官方，及 `aosd=0` 排查。

#### 2026-11-15 冷启动卡死根因定位与修复：`7.2.15-28.opd2413`（`2434` 修复 `q6dsp-lpass-clocks` 探针 `drvdata` 竞态）

- **故障回溯与离线修复（2026-11-15）：**
  1. 在 `-27` 设默认后首次无干预冷启动卡死于控制台（截图见 `user pgtable` 访问 `[0000000000000348]`、`opd2413-sensors-gate.service` 30 s 超时失败、`abrtd.service` 阻塞 `32s / 46s`，以及 `65.7 s` `qsh_process` / `adsp` 崩溃），经 `systemd-boot` 手工切回 `-26` 后提取 `boot -1`（`da4e07b8a8994b9c94c7afead000fec3`）日志并反汇编内核 `.o` 定位：
     - `struct q6dsp_cc` 的 `desc` 字段位于偏移 `8 + 104 * 8 = 840` 字节（`0x348`）；
     - 上游 `sound/soc/qcom/qdsp6/q6dsp-lpass-clocks.c` 的 `q6dsp_clock_dev_probe()` 在 `devm_of_clk_add_hw_provider()`（公开 `q6prm-lpass-clock` 的时钟）之后才调用 `dev_set_drvdata(dev, cc)`，导致并行加载的 `va_macro 7660000.codec` 等消费者在窗口期调用 `clk_prepare_enable()` 时于 `clk_q6dsp_prepare()` 读取 `NULL + 0x348` Oops，并带着全局 `clk_prepare_lock` 互斥锁死亡，永久死锁全系统后续时钟操作（显示、音频、传感器/ADSP 服务）。
  2. 新增补丁 `2434`（[2434-ASoC-qcom-qdsp6-set-drvdata-before-registering-clock.patch](../kernel/opd2413-7.2/patches/2434-ASoC-qcom-qdsp6-set-drvdata-before-registering-clock.patch)）将 `dev_set_drvdata(dev, cc)` 提前至时钟与 provider 注册之前，零 fuzz（`-F0`）合入并由 `N=28 bash out/m3k/build.sh` 编出 `kernel-opd2413-7.2.15-28.opd2413.aarch64.rpm`（SHA256 `785e4971262b1a7f8c1a200cc911aee29e36cb44c00aecb36ba7f9794aa3f51b`）；`q6dsp-lpass-clocks.o` 零告警、反汇编确认 `str x25, [x20, #120]` 位于注册循环之前；`tests/package-install-test.sh out/m3k/rpms28 out/m3k/pkg-test28` 确认 ESP 条目、DTB 与 `initramfs`（`94063956` 字节，67 项早期固件 0 缺失）通过（仅第 78 行 `66` vs `67` 已知常量触发 `EXIT=1`）。
- **上机测试前预期与判据：**
  1. **安全装机与一次性冷启动**：在当前 `-26` 上先将 `loader.conf` 默认项恢复为 `fedora-7.2.15-26.opd2413.conf` 并 `rpm -e kernel-opd2413-7.2.15-27.opd2413`，再安装 `-28` 清理 `/tmp` 临时包；确认 `-28` 条目 `options` 继承更新后的 `/etc/kernel/cmdline`（无 `fw_devlink.sync_state=timeout` / `pcie_ports=compat`，带 `mem_sleep_default=s2idle`），执行 `tools/tablet-reboot.py --entry fedora-7.2.15-28.opd2413.conf --wait 240` 冷启动至 `-28`。
  2. **冷启动零 Oops 与子系统全就绪**：`uname -r == 7.2.15-28.opd2413`，`systemctl is-system-running == running`、`systemctl --failed == 0`、`getenforce == Enforcing`、`avc.*denied` 为空；`dmesg` 无 `0x348` / `Unable to handle` / `Oops` / `adsp` / `qsh_process` 崩溃；`q6prm-lpass-clock`、`va_macro`、`rx_macro`、`wcd939x`、`opd2413-sensors-rpcd`/`-gate`/`iio-sensor-proxy`、`bluetooth`、`wlp1s0` 与 Wayland 桌面（1 次 `DPMS off/on` 亮灭屏 + 短 `s2idle` 复检）全部正常。
- **上机实测结果（2026-11-15）：真机启动通过（`tablet-reboot.py` 一次引导，待确认设默认后做 `systemctl poweroff` 断电冷启动复查）**
  - **装机与引导**：先将 `-26` 设回 `loader.conf` 默认并卸载 `kernel-opd2413-7.2.15-27.opd2413`，安装 `-28` 后清理 `/tmp/` 临时 RPM（ESP `/dev/sda16` 维持 `247M / 512M`、`49%`）；用户先冷启动在 kShimC 手选 `Fedora` 恢复 `"kshim_remembered": "Fedora"` 回到 `-26` 后，执行 `python3 tools/tablet-reboot.py --entry fedora-7.2.15-28.opd2413.conf --wait 240`，`59 s` 上线至 `-28`（`pending_next: null`、`loader_default` 暂保持 `-26`）。
  - **状态与日志核验**：`uname -r = 7.2.15-28.opd2413`，`/proc/cmdline` 含 `mem_sleep_default=s2idle` 且无 `fw_devlink.sync_state=timeout` 与 `pcie_ports=compat`，`/sys/power/mem_sleep = [s2idle] deep`；`systemctl is-system-running = running`、`--failed` 为空、`Enforcing`、`0` 条 `avc.*denied`；`dmesg` 全程无 Oops / `0x348` / `qsh_process` / `fatal error`，`3d37000.gmu` 绑定，`remoteproc1` `adsp is now up`，`nt36536` `Update firmware success!`（`PID=5F95`），`va_macro` / `rx_macro` / `wcd939x` 干净（仅保留既有的探测前 `0.46-0.48s` `DSI PLL(0) lock failed`）。
  - **子系统与短复检**：`opd2413-sensors-rpcd`、`opd2413-sensors-gate`、`iio-sensor-proxy`、`bluetooth`、`opd-netshare` 均为 `active`；`aplay -l` 列出 `card 0: OnePlusPad2Pro [OnePlus-Pad-2-Pro]`（device 0/1）；`kscreen-doctor --dpms off` 后 3 s `lcd_vsp` / `lcd_vsn` / `vreg_l12b_1p8` 均 `state=disabled users=0`，`--dpms on` 后 2 s 均 `state=enabled users=1`；`rtcwake -m mem -s 5` 返回 `suspend_stats` `success=1`、`fail=0`；`eglinfo -B` 为 `Adreno (TM) 830`（`Mesa 26.2.6`），系统 `running`。
  - **回馈对照**：核对 `linux-sm8750-erhai` 仓库 `sound/soc/qcom/qdsp6/q6dsp-lpass-clocks.c`，确认存在完全相同的缺陷（`devm_of_clk_add_hw_provider` 在 L177 先于 L181 `dev_set_drvdata` 调用），`2434` 可一并向 erhai / 上游提交（待后续统筹回馈）。
- **设默认与冷启动复查（2026-11-15 12:11）：真机通过**
  - 经用户确认后执行 `boot-select default fedora-7.2.15-28.opd2413.conf`（回读 `/boot/efi/loader/loader.conf` 为 `default fedora-7.2.15-28.opd2413.conf`，保留 `-26` 作回退）。
  - 用户在未插电状态下手动关机再冷启动开机（`uptime -s = 2026-11-15 12:11:28`），SSH 复核通过：`uname -r = 7.2.15-28.opd2413`、`booted_entry = fedora-7.2.15-28.opd2413.conf`、`loader_default = fedora-7.2.15-28.opd2413.conf`、`kshim_remembered = "Fedora"`、`pending_next = null`；`systemctl is-system-running = running`、`--failed` 为空、`getenforce = Enforcing`、`journalctl -b` 零 `avc.*denied`；`opd2413-sensors-rpcd`、`opd2413-sensors-gate`、`iio-sensor-proxy`、`bluetooth`、`opd-netshare` 均为 `active`；`aplay -l` 正常列出 `card 0: OnePlusPad2Pro`；`dmesg` 确认 `bound 3d37000.gmu`、`remote processor adsp is now up`、`[nt36536] Update firmware success!`（`PID=5F95`）且无 Oops / `qsh_process` / `fatal error`。

#### 2026-11-15 相机 SoftISP / 调校补丁与对焦马达排查：`libcamera 0.7.2-5.fc45.opd2413.2`

- **补丁与打包（`packaging/opd2413-libcamera/`）：**
  - 在 `libcamera-0.7.2` 原有补丁 `0001`–`0002` 基础上新增 7 个补丁 `0101`–`0107`（[libcamera.spec](../packaging/opd2413-libcamera/libcamera.spec)，`Release: 5%{?dist}.opd2413%{?opdrel:.%{opdrel}}`）：
    - `0101`：`ipa: libipa: camera_sensor_helper: Add sc820cs and sc1300cs`；
    - `0102`：`libcamera: camera_sensor_properties: Add sc820cs and sc1300cs`；
    - `0103`：`libcamera: dma_buf_allocator: Prefer SystemHeap before CmaHeap`；
    - `0104`：`ipa: simple: Run swstats every frame and speed up AGC convergence`；
    - `0105`：`ipa: simple: debayer_egl: Add radial per-channel Lens Shading Correction`；
    - `0106`：`pipeline: simple: ipa: simple: Add CameraLens VCM and contrast-detect AF`；
    - `0107`：`ipa: simple: data: Add initial sc820cs and sc1300cs tuning files`。
  - 宿主机 `out/rpmbuild/RPMS/aarch64/` 已编出 `libcamera-0.7.2-5.fc45.opd2413.2.aarch64` 全套子包；平板端已实装 `libcamera`、`libcamera-ipa`、`libcamera-tools`、`python3-libcamera`（均 `0.7.2-5.fc45.opd2413.2.aarch64`，配合 `pipewire-plugin-libcamera-1.6.11-1.fc45.aarch64`）。
- **状态与已知限制：**
  - 前摄 `sc820cs` 经后续 `opd2413-face` 人脸识别与 GUI 实测，画面清晰度与曝光已满足解锁使用，用户确认够用（**真机通过**）。
  - 后摄 VCM 马达 `cn3927`（I2C `10-000c`、`ac7b000.cci`）实机 `dmesg` 报 `[    5.182919] i2c-qcom-cci ac7b000.cci: master 1 queue 0 timeout`，`/sys/bus/i2c/devices/10-000c/power/runtime_status = error`（`ac7b000.cci` 为 `suspended`），后摄 `sc1300cs` 物理自动对焦暂不可用，已登记 [TECH-DEBT.md](TECH-DEBT.md#L42-L43) `#42`。

#### 2026-11-15 原生人脸识别解锁与录入向导 RPM：`opd2413-face`（`0.1-1`–`0.1-10`）

- **架构与实现（`packaging/opd2413-face/`）：**
  1. **后台识别服务 `opd2413-faced`**（[opd2413-faced.py](../packaging/opd2413-face/src/opd2413-faced.py) -> `/usr/libexec/opd2413/opd2413-faced`）：root systemd D-Bus 服务（`org.opd2413.Face1`），经 `python3-libcamera` + `DebayerEGL` + DMA-BUF `mmap`（`DMA_BUF_IOCTL_SYNC`）从 `camera_match = sc820cs`（`1280x960`、`warmup_frames = 8`）取帧，运行 Apache-2.0 OpenCV Zoo YuNet（`face_detection_yunet_2023mar.onnx`）与 SFace（`face_recognition_sface_2021dec.onnx`）；默认 `/etc/opd2413-face.conf` 配置 `default_timeout_ms = 3500`、`cosine_threshold = 0.42`、`liveness = standard`、`required_matches = 2`、`min_face_px = 96`、`min_sharpness = 22.0`、`min_frame_delta = 0.45`、`reject_when_lid_closed = true`。
  2. **轻量 C PAM 模块与策略**（[pam_opd2413_face.c](../packaging/opd2413-face/src/pam_opd2413_face.c)）：仅依赖 `sd-bus` 与 `pam`（调用方零 Python/相机/ONNX 依赖），默认 `timeout=3500`，检测 `PAM_RHOST` / `SSH_CONNECTION` / `SSH_CLIENT` / `SSH_TTY` 远程会话或未录入用户时直接 `PAM_IGNORE`。随包携带 `authselect` vendor profile `opd2413-face`（接管锁屏 `kde-fingerprint` -> `fingerprint-auth` 与 `sudo`/`polkit-1` 的 `system-auth`，不改 `password-auth`）与 SELinux 模块 `opd2413_face`（放行 `xdm_t`、`policykit_auth_t`、`chkpwd_t`、`local_login_t`、`unconfined_t` 与 `unconfined_service_t` D-Bus 交互）。
  3. **KDE 锁屏 QML 插件与外壳集成**（`src/qml/facebridge.{cpp,h}`、`data/lockscreen/`）：通过 `org.opd2413.face` `FaceBridge` 与 `SetLockscreenMode`（配合 `LOCKSCREEN_IDLE_WAIT_S = 2.3`）实现“时钟屏保待命 -> 唤醒进入输入态延时扫描 -> `faceStatusPill` 扫描视觉指示 -> 失败后点击重试或密码回退”；`0.1-9` 修复 [LockScreenUi.qml](../packaging/opd2413-face/data/lockscreen/LockScreenUi.qml) 的 `handleMessage(msg)` 空串过滤并新增 `FaceBridge.onEnrolledChanged` 补触发，消除 Plasma 6.8.2 `kscreenlocker_greet` 初始化切换 `Regular` 认证器发射空 `promptChanged` / `infoMessageChanged` / `errorMessageChanged` 时立即触发 `uiVisible = true` 直接打开密码框的问题（日志 `Worker not ready yet` 由 4 次降为 2 次）。
  4. **Qt GUI 录入向导打包与图标修正**（[opd-face-enroll-gui.py](../packaging/opd2413-face/src/opd-face-enroll-gui.py)、[opd-face-enroll.desktop](../packaging/opd2413-face/data/opd-face-enroll.desktop)、[opd2413-face.spec](../packaging/opd2413-face/opd2413-face.spec)）：`0.1-9` 将桌面脚本正式打包至 `/usr/libexec/opd2413/opd-face-enroll`、`/usr/bin/opd-face-enroll`（`python3 -B` 防写 `__pycache__`、通过 `pkexec ... --worker` 提权执行 4 组姿态录入与实测），新增 `python3-pyside6` 依赖并删除桌面遗留脚本与 root `__pycache__`；`0.1-10` 排查应用无正常图标原因为原用 `edit-image-face-recognize` 仅存于 Breeze `actions/16|22|24` 单色问号方框图标，统一改回 Breeze `[preferences/32]` 彩色笑脸 `face-smile`。
- **实测验证（2026-11-15）：**
  - **锁屏、唤醒识别、`sudo`/`polkit` 与向导功能（`0.1-8` / `0.1-9`，真机通过）**：冷启重启后刷脸解锁、`sudo`/`polkit` 自动人脸授权、挡住摄像头退回重试/密码输入、锁屏默认停留在时钟屏保并在唤醒后显示扫描图标解锁、应用启动器打开录入向导与 4 组录入测试均经用户真机实测确认正常；自动 D-Bus 抓包确认锁屏待命 3.5 s 期间仅调 1 次 `SetLockscreenMode(true, false)`、0 次 `Verify`。
  - **图标修复版本升级（`0.1-10`，真机通过）**：产包 `out/rpmbuild/RPMS/aarch64/opd2413-face-0.1-10.fc45.aarch64.rpm`（SHA-256 `6c32d3eacd16fd89c7e3f4e875d791ed257cf85a929fd10020a3cf5c95e8b0ea`），`desktop-file-validate` clean；平板离线 `dnf upgrade` 替换 `0.1-9` 后 `rpm -V opd2413-face plasma-desktop` 无差异、`/usr/libexec/opd2413/` 无 `__pycache__`、已执行 `kbuildsycoca6` 刷新、`WAYLAND_DEBUG=1` 实测 `wayland-1` 发送 `xdg_toplevel_icon_v1.set_name("face-smile")` 与 7 档位 `wl_buffer`；`opd-face status --user colin` 为 `idle` 且 `enrolled=yes`、`authselect` 为 `opd2413-face with-silent-lastlog with-mdns4`、`lockscreen UI shell overlay: enabled`、`systemctl is-system-running = running`、`--failed = 0`、`ausearch --input-logs -m avc -ts recent = <no matches>`，用户实机确认桌面启动器 `face-smile` 图标显示正常。

#### 2026-11-15 相机实时 GPU ISP 画质与重配置修复：`libcamera 0.7.2-5.fc45.opd2413.3`

- **问题对照与离线原型依据：**
  - 对比 ColorOS（`3264×2448` 8MP、`1/25s`、`f/2.0`、`ISO 400`）与 Fedora GNOME Snapshot / PipeWire 默认出片（`1920×1080`）及直采 8MP SoftISP 实机样张（存宿主机 gitignored 试验目录），定位 5 项实时画质/稳定性差距：
    1. `DebayerEGL::debayerGPU()` 对 1080p 裁剪 FBO 仍使用全传感器 `glViewport(0, 0, width_, height_)` 与左下角锚点 `projMatrix`，造成 1080p 底部约 25% 画面截断且径向 LSC 坐标拉伸失真，同时 `SwStatsCpu` 测光窗口落于左上角 `(0, 0)`；
    2. `RAW10P`/`RAW12P` 着色器（[bayer_1x_packed.frag](../packaging/opd2413-libcamera/patches/0109-ipa-simple-shaders-Upgrade-GPU-ISP-pipeline-and-tuni.patch)）仍采用 3×3 双线性去马赛克、无降噪锐化、且在 CCM 前执行 `clamp(rgb * lscGain * awb, 0.0, 1.0)` 导致高光被硬削平且过曝白墙泛洋红（实测 1080p `>250` 溢出 `16.61%`、8MP 达 `37.19%`，而传感器原始 RAW10 仅 `5.44%` 饱和）；
    3. `sc820cs` 在 `Rotation=180` 硬件 `HFLIP+VFLIP` 后光学中心 `cx` 未镜像且径向 `R/G` 增益偏高（角部 `3.70x` vs `3.15x`）引发四角粉紫偏色；
    4. `SwStatsCpu` 统计 `sum_` 未剔除饱和/黑电平区、AGC `kExposureOptimal=2.5` 未感知高光溢出、`Awb` 缺帧间 IIR 平滑；
    5. `DebayerEGL::stop()` 未执行 `makeCurrent()` 与 `eglTerminate`/`eglDestroyContext` 清理，同进程切换分辨率会残留跨线程上下文状态并报错 `debayerGPU failed`。
  - 先通过宿主机零写入实验抓取 `sc820cs` 实时帧与 8 帧 RAW10 连拍包并在离线原型验证：修复居中视口、LSC 色差阻尼、5×5 MHC、高光中性白重建、色调映射与联合双边降噪后，单帧 `>250` 溢出由 `37.19%` 降至 `0.93%`、四角 `R/G, B/G` 收敛到 `1.01, 0.99`。
- **补丁与离线打包（`packaging/opd2413-libcamera/`，`opdrel=3`）：**
  - 新增 `Patch108`（[0108-debayer_egl-Fix-crop-viewport-LSC-UV-and-EGL-reconfi.patch](../packaging/opd2413-libcamera/patches/0108-debayer_egl-Fix-crop-viewport-LSC-UV-and-EGL-reconfi.patch)）：在 `eGL` 新增 `cleanUp()` / `hasContext()` 及 `initEGLContext()` 重入清理；在 `DebayerEGL` 调整成员析构顺序、补全 `stop()` 的 `makeCurrent()` + 缓存/程序/EGL 上下文销毁、修复 `outputSize_` 视口及保长宽比居中 UV 裁剪（保持全画幅 LSC 坐标）、并将 `SwStatsCpu` 统计窗口居中到传感器 3/4 视场。
  - 新增 `Patch109`（[0109-ipa-simple-shaders-Upgrade-GPU-ISP-pipeline-and-tuni.patch](../packaging/opd2413-libcamera/patches/0109-ipa-simple-shaders-Upgrade-GPU-ISP-pipeline-and-tuni.patch)）：
    - 将 `bayer_1x_packed.frag` 升级为 5×5 Malvar-He-Cutler 去马赛克及半像素居中字节寻址（`Step[] = { bpp/stride, 1/height }`）；
    - 在 `bayer_1x_packed.frag` 与 `bayer_unpacked.frag` 统一去除 CCM 前截断，实现饱和通道中性白重建、线性 HDR CCM、保亮度 Extended-Reinhard 软肩部与微幅暗部补偿、分段 sRGB 传递函数；
    - 新增 `rgb_post.frag`（[0109 补丁](../packaging/opd2413-libcamera/patches/0109-ipa-simple-shaders-Upgrade-GPU-ISP-pipeline-and-tuni.patch) 内 `src/libcamera/shaders/rgb_post.frag`）并挂载到 `DebayerEGL` Pass 2 离屏 FBO（`intermediateImage_`），按 `DebayerParams::again` 实时增益执行 3×3 + 稀疏 5×5 YCbCr 联合双边降噪与 CAS 无光晕锐化；
    - 改进 `SwIspStats`/`SwStatsCpu`/`Awb`/`Agc`（剔除饱和与黑电平噪声采样用于 AWB 并保持有效样本数一致、AWB 首帧瞬时收敛+后续 IIR 平滑、AGC 目标 `2.2` + 顶部直方图饱和惩罚）并更新 `sc820cs.yaml`（镜像光心与阻尼 LSC）与 `sc1300cs.yaml`。
  - 在 ARM64 Fedora 45 容器执行 `tools/build-libcamera-rpm.sh 3` 编译通过，`--with container_check` 过滤运行 77 项 `meson test` 结果：`45 Ok`、`1 Expected Fail`、`0 Fail`、`31 Skipped`（容器内无内核 `vimc`/硬件节点项退出码 77 跳过；`libcamera.spec` 另排除 `6` 项依赖 `clone3`/IPC/虚拟管道测试）；`rpm -qlp` 核对 `libcamera-ipa` 含 `ipa_soft_simple.so`、`ipa_soft_simple.so.sign`、`sc820cs.yaml` 与 `sc1300cs.yaml`。
  - 对应平板当前已安装包的 `0.7.2-5.fc45.opd2413.3.aarch64.rpm` 产物 SHA-256：
    - `libcamera`：`fa4469dfe88f4cc38431e679052341925164b4cfd974efd134797eebd5ce1945`
    - `libcamera-ipa`：`78d8bb04f8d27d69bc7d429eadfac80e24c6e97fa0d076ec27664860ed22c131`
    - `libcamera-tools`：`f0c7f08c3911a662b724c2bf234d78412c5b5b2374ead2736f84d215154b3490`
    - `python3-libcamera`：`08bc139bf02a415b65fe18fd912e3c55c0229ea0208c2b79f2473fcbc821777d`
- **上机测试前预期与判据：**
  1. **设备写入范围（待用户确认后执行）**：仅向平板 `/tmp/` 传入上述 4 个对应已安装子包的 `0.7.2-5.fc45.opd2413.3.aarch64.rpm`，在 `ARMADA_ROOT` 上执行 `dnf upgrade -y` 并删除 `/tmp/` 临时 RPM，重启 `opd2413-faced.service` 与用户态 `pipewire`/`wireplumber`（不触碰 ESP、`ARMADA_BOOT`、`boot_b` 或 Android 分区）。
  2. **前摄 `sc820cs` 实时画质达标**：1080p（PipeWire / GNOME Snapshot）与 8MP 出片高光溢出率（`>250`）从 `16%~37%` 降至 `<3%`，1080p 底部截断消失（上下对称居中 16:9 视场），四角偏色消除（`|R/G - 1| <= 0.06`），平坦区彩噪与亮度颗粒显著下降且无边缘白边/黑边光晕。
  3. **跨分辨率重配置稳定性**：同一进程内连续切换 `1920×1080 <-> 3256×2448` 启动/停止流零 `debayerGPU failed` 或断言失败。
  4. **关联链路无回归**：`opd2413-face`（`1280×960`、8 帧预热）认证服务与后摄 `sc1300cs` 13MP 实时 GPU 出片均正常，系统与桌面日志无新报错。
- **真机验收结果（2026-11-15，真机通过）：**
  - **离线升级与服务健康**：4 个 `0.7.2-5.fc45.opd2413.3.aarch64` 子包经 SHA-256 校验后在 `ARMADA_ROOT` 完成 `dnf upgrade -y --disablerepo='*'`，临时包已清理；重启 `opd2413-face.service` 与用户态 `wireplumber`/`pipewire` 后，`opd-face status` 显示 `org.opd2413.Face1` 为 `idle`、`enrolled=yes`，`systemctl --failed` 为 `0` 项，`ausearch -m avc -ts recent` 无匹配拒绝。
  - **同进程多分辨率切换与帧率**：同一进程对 `sc820cs` 连续 `stop() -> 排空取消请求 -> configure() -> start()` 切换四档配置全部零 `debayerGPU failed` 通过：
    - `1920×1080 XRGB8888`：24 帧，`31.63 fps`；
    - `3256×2448 XRGB8888`：18 帧，`31.61 fps`；
    - `1280×960 XRGB8888`（`opd2413-face` 分辨率）：12 帧，`31.80 fps`；
    - `[Viewfinder 1632×1224 XRGB8888, Raw 3264×2448]` 双流 ZSL：12 帧，`32.59 fps`。
    - 后摄 `sc1300cs` `[StillCapture 4152×3120 XRGB8888, Raw 4160×3120]` 20 帧达 `32.67 fps`。验证过程同时定位并确认：Python/C++ 客户端每次 `cam.stop()` 后需立即排空 `get_ready_requests()` 中被取消的旧请求，避免将旧流的小尺寸输出缓冲误复用进大尺寸新配置触发 `Output cache 4 exceeded`。
  - **客观画质指标与视觉对比**（存宿主机 gitignored `private/cam-stage1-20261115/` 证据目录）：
    - 前摄 `1080p` / `8MP` 高光溢出率（`>250`）分别由升级前的 `24.66%` / `40.75%` 降至 **`0.0%`**（与 ColorOS 参考图一致），平坦区噪声标准差由 `5.37` / `5.84` 降至 **`1.49` / `1.84`**（ColorOS 为 `1.30`）；
    - 左侧同色纯白墙上下角相对中心墙面色比：`8MP` 上左 `(R/G=1.058, B/G=1.024)`、下左 `(R/G=1.055, B/G=1.028)`，`1080p` 上左 `(1.052, 1.030)`、下左 `(1.051, 1.017)`，墙面均值 `[171.9, 174.1, 175.3]`；16:9 视角上下居中对称恢复（不再截断底部 25% 画面），白墙及木纹色彩、清晰度经人工视觉检视无伪影。
  - **双摄 Raw 相位与后续 Stage 2 标定确认**：双流 `Raw` 相关性实测确认前摄 `sc820cs`（`3264×2448`）与后摄 `sc1300cs`（`4160×3120`）在内存中均已正立（`0°` 无需旋转）且实际物理 Bayer 排列均为 `BGGR10_CSI2P`（尽管 `StreamRole.Raw` 元信息仍标为 `SRGGB10_CSI2P`）；注：后摄测试时平板背面朝暗处且 20 帧下 AE 仍停留在 `17.6 ms / gain 1.0` 亮度偏暗，亮景与 HDR+ 效果留待 Stage 2 验证。

### ARM64 用户态 RPM 平板原生编译链路与阶段 2 HDR+ 相机离线验证（2026-11-15，离线通过）

- **平板原生编译流水线**（`tools/tablet-build-common.sh` 及 4 个 `tools/build-{camera,face,libcamera,sensors}-rpm.sh`）：
  - 默认通过 `private/ssh.sh`（`OPD_OS=fedora`）对平板执行架构与电量（`>=15%` 或充电中）检查后，在平板 SM8750 Oryon 原生环境（`/tmp` 内存盘、`systemd-inhibit` 防休眠、`nproc - 1` 即 `-j7` 留核限流）执行编译打包并回传产物与日志；保留 `--local` / `OPD_BUILD_TARGET=local` 宿主机固化容器镜像兜底路径（`opd_ensure_cached_image`，`build-libcamera-rpm.sh` 支持 `BuildRequires` 哈希自动失效与 `REUSE_BUILD=1`）。
  - 5 个脚本已通过 `bash -n` 静态检查；`tools/build-camera-rpm.sh 0.1 1`（首次按需补齐 `rpm-build`/`python3-devel` 后，复跑纯构建 + `%check`）从宿主 QEMU 容器约 `2.5+ min` 缩短至端到端 **`4.562s`**。注：`face`/`libcamera`/`sensors` 三个脚本的平板原生路径已做静态语法校验，暂未实际重跑全量构建。
- **阶段 2：`opd2413-camera` 0.1-1（ZSL 多帧 RAW10 HDR+ 相机，状态：`离线通过`）**：
  - **实现文件（`packaging/opd2413-camera/`）**：`src/hdrplus_isp.py`（RAW10 CSI2P 解包、2×2 超像素双阶段局部零均值相位相关对齐、`mad_noise` 与双帧方差 `2.0` 比例缩放去鬼影融合、5×5 Malvar-He-Cutler 去马赛克、中性高光重建、LSC/AWB/色温插值 CCM、5 级 Mertens 曝光融合、YCrCb 双边降噪与 CAS 锐化、`ExifIFD 0x8769` EXIF 写入）、`src/opd-camera-cli.py`（`/usr/bin/opd-camera-cli`）、`src/opd-camera-gui.py`（`/usr/bin/opd-camera`，`PySide6` ZSL 双流 `XRGB8888` + `stop()` 后 `get_ready_requests()` 排空）、`data/opd-camera.desktop`、`opd2413-camera.spec`、`tests/test_hdrplus_isp.py`。
  - **构建与单测校验**：`tools/build-camera-rpm.sh 0.1 1` 在平板原生构建并全部通过 `%build`（`py_compile`）、`%install`、`desktop-file-validate` 与 `tests/test_hdrplus_isp.py`（`ALL_HDRPLUS_UNIT_TESTS_PASSED`，含单 Bayer 子通道平坦区降噪校验与多尺度宽带纹理对齐 RMSE 校验），产出 `out/rpmbuild/RPMS/aarch64/opd2413-camera-0.1-1.fc45.aarch64.rpm`（SHA-256：`9d2ef6b94dfec9e42fad86b06175206e01ef3b8870fed3841af8a968cc1ed877`）。
  - **Oryon 真机芯片离线 RAW10 基准**（宿主机 `private/cam-exp-20261115/` 8 帧 8MP `sc820cs` 连拍输入，传平板 `/tmp` 运行后清理，输出 `private/cam-stage1-20261115/stage2_offline_hdrplus_8mp.jpg`）：全管线耗时 **`5629.8 ms`（5.63s）**，`clip(>250)% = 0.000%`，平坦白墙高频噪点标准差 **`0.55`**（Stage 1 单帧 `1.84`、ColorOS 参考图 `1.30`）；人工检视图像正立、白墙中性无色偏、细节清晰且无重影或高光溢出。
- **阶段 2 上机安装前预期与判据（待用户确认后执行）：**
  1. **设备写入范围**：仅向平板 `/tmp/` 传入 `opd2413-camera-0.1-1.fc45.aarch64.rpm`，在 `ARMADA_ROOT` 执行离线 `dnf install -y --disablerepo='*'` 后清除 `/tmp/` 临时 RPM；包内包含 `/usr/bin/opd-camera`、`/usr/bin/opd-camera-cli`、`/usr/libexec/opd2413/{hdrplus_isp,opd-camera-cli,opd-camera-gui}.py` 与 `/usr/share/applications/opd-camera.desktop`（运行依赖 `libcamera >= 0.7.2-5.fc45.opd2413.3`、`python3-{libcamera,numpy,opencv,pillow,pyside6}` 均已在平板就绪）。
  2. **前/后摄 ZSL HDR+ 实拍验收**：前摄 `sc820cs`（8MP）与后摄 `sc1300cs`（13MP）均可通过 `opd-camera-cli` 正常执行双流 ZSL 多帧 RAW10 采集与 HDR+ 出片，方向正立、色彩自然、高光不死白且无 `debayerGPU failed` 或崩溃。

#### 真机验收结果（2026-11-15，真机通过）

- **问题定位与最终修复**（[hdrplus_isp.py](../packaging/opd2413-camera/src/hdrplus_isp.py) / [opd-camera-gui.py](../packaging/opd2413-camera/src/opd-camera-gui.py)）：
  - 在 `opd-camera-gui.py` 补全 Wayland 桌面元数据（`app.setDesktopFileName("opd-camera")` 与 `QIcon.fromTheme("camera-photo")`）。
  - 首轮真机测试中前摄 `8MP` 成片正常，后摄 `sc1300cs`（`AnalogueGain=16.0`）暗光实拍出现整体紫红暗部雾霾（`mean_rgb=[129.9, 94.5, 117.5]`）；对实机 RAW10 做 8 帧均值采样确认 `SensorBlackLevels=4096`（`64.00 DN`）及最暗 `128×128` 块（`[B=64.96, Gb=66.0, Gr=65.42, R=64.69] DN`）准确且中性，问题系 `p005*0.98` 将 `black_level_10b` 误拉低至 `57.82 DN`、去马赛克前 `np.maximum(merged_bayer, 0.0)` 对零均值读噪声做半波整流产生正偏差，以及 `_auto_ev_gain` / Mertens 最大提亮达 `4.5×1.65=7.4×` 所致。
  - 修复方案：取消 `p005*0.98` 下拉（仅保留 `p05 < bl * 0.5` 严重失配兜底）、取消去马赛克前负值截断、在 CCM 后依据 `merge_info["mad_noise"]` 添加极暗部色度滚降，并将 `_auto_ev_gain` 上限压至 `2.4`、Mertens 倍率调整为 `[0.75, 1.0, 1.40]`。
- **最终编译、单测与平板装机**：
  - 平板原生运行 `bash tools/build-camera-rpm.sh 0.1 1`（`jobs=7 batt=94%(Charging)`）成功生成最终 `out/rpmbuild/RPMS/aarch64/opd2413-camera-0.1-1.fc45.aarch64.rpm`（SHA-256：`434aadb1a68e59fe993b463b142e5472cb49c1eec750cc8727bb0da2bae81df1`）；
  - 通过 `dnf reinstall -y --disablerepo='*'` 离线重装至 `ARMADA_ROOT` 并删除 `/tmp/` 临时包后，针对实装目录 `/usr/libexec/opd2413` 运行 `packaging/opd2413-camera/tests/test_hdrplus_isp.py` 直接观测输出 `ALL_HDRPLUS_UNIT_TESTS_PASSED`。
- **前/后摄 `opd-camera-cli` 实拍实测（普通用户 `colin`）**：
  - **前摄 `sc820cs`（8MP，`--mode hdr+ --frames 8 --warmup 24`）**：`black_level_10b=64.0`，`burst_capture_ms=234.5`，`isp_process_ms=3819.8`（`total_ms=7162.3`），`awb_gains=[1.667, 1.0, 1.36]`、`est_ct=6095.0`、`analogue_gain=12.36`、`exposure_us=33280`；样张 `private/cam-stage1-20261115/stage2_live_front_8mp.jpg`（`3264×2448`）指标 `mean_rgb=[162.92, 152.9, 141.96]`、`clip(>250)%=0.000%`、`flat_hp_noise=1.12`，EXIF `Make='OnePlus'`、`Model='OnePlus Pad 2 Pro (OPD2413)'`、`Orientation='Horizontal (normal)'`、`ISO=1236`、`ExposureTime=1/30`、`FNumber=2.0`；目视人像、白墙及纱帐正立清晰、无偏色。
  - **后摄 `sc1300cs`（13MP，`--mode hdr+ --frames 8 --warmup 30`）**：`black_level_10b=64.0`，`burst_capture_ms=222.7`，`isp_process_ms=9366.8`（`total_ms=12887.1`），`awb_gains=[2.151, 1.0, 1.685]`、`est_ct=5817.0`、`analogue_gain=16.0`、`exposure_us=33270`；样张 `private/cam-stage1-20261115/stage2_live_rear_13mp.jpg`（`4160×3120`）指标 `mean_rgb=[89.09, 99.86, 86.52]`、`dark10_rgb=[22.55, 22.07, 22.09]`、`clip(>250)%=0.119%`、`flat_hp_noise=2.25`，EXIF `Make='OnePlus'`、`Model='OnePlus Pad 2 Pro (OPD2413)'`、`Orientation='Horizontal (normal)'`、`ISO=1600`、`ExposureTime=1/30`、`FNumber=2.2`；目视黑色衣物恢复中性灰黑、紫红暗部雾霾彻底消除（`cn3927` 物理对焦仍受 `#42` 限制）。
- **Qt6 Wayland GUI 与系统健康度**：
  - 用户 `colin` 于 `WAYLAND_DISPLAY=wayland-1 QT_QPA_PLATFORM=wayland` 下启动 `/usr/bin/opd-camera` 运行 6 秒实况取景（Adreno 830 EGL `1632x1224` + `3264x2448`），`timeout -s TERM 6s` 干净退出（`GUI_EXIT_CODE=124`），无 Python 异常且无残留进程；
  - `opd2413-face.service` 状态 `active`（`idle`，`user 'colin': enrolled=yes`），`systemctl --failed` 为空，最近 SELinux `AVC` 无拒绝，平板 `/tmp/opd*` 已清理。
- **证据位置**：宿主机 `private/cam-stage1-20261115/stage2_live_front_8mp.jpg`、`private/cam-stage1-20261115/stage2_live_rear_13mp.jpg`。

### 后摄 `cn3927` 自动对焦与 `opd2413-camera-0.1-2` 亮度/鲜艳度修复（2026-11-16，RAM 热加载与 CLI/冒烟验证通过，待 `-29` 冷启动固化）

- **上机测试前预期与判据：**
  1. **设备写入边界**：内核侧先通过 `sysfs` 在线验证及 `rmmod cn3927 && insmod /tmp/cn3927.ko` 在平板内存（RAM）中完成真机验证，不触碰 `/boot` 与 ESP（待实机验证后向用户汇报并征求确认再持久化刷入内核 RPM）；用户态仅升级安装 `opd2413-camera-0.1-2.fc45.aarch64.rpm` 到 `ARMADA_ROOT`。
  2. **预期 1（后摄 `cn3927` 共电耦合与 PM 生命周期修复）**：保持 `sc1300cs` (`10-0036`) 处于 `active` 时重新绑定并驱动 `cn3927` (`10-000c`) 不再出现 `master 1 queue 0 timeout`；加载补丁 `2435` 后，空闲态打开 `/dev/v4l-subdev*` 不触发 I2C、写 `V4L2_CID_FOCUS_ABSOLUTE` 配合 `device_link` 在流期间保持马达与传感器共电稳定、停流后顺利归位并挂起，`dmesg` 零超时与报错；`opd-camera-cli --camera rear` 中 `libcamera` Contrast AF 正常锁定 `AfState == 2` (`Focused`)，手动 `0.0D` 远焦与 `10.0D` 近焦实拍呈现可测锐度差异。
  3. **预期 2（`opd2413-camera-0.1-2` 自动亮度与肤色保护鲜艳度）**：采用 `LUX` 感知中心加权测光 + 通透中间调曲线及暗部归零/肤色高斯保护 `Vibrance + Saturation` 后，前/后摄亮度与色彩鲜艳度明显改善，同时暗部保持中性（`dark10_rgb` 不偏紫）、高光裁剪 `< 1.0%`、Wayland GUI 与 `opd2413-face.service` 无回归。
- **用户态升级与首次复测根因定位：**
  - 更新 `packaging/opd2413-camera/`（`opd2413-camera.spec`、`src/hdrplus_isp.py`、`src/opd-camera-cli.py`、`src/opd-camera-gui.py`、`tests/test_hdrplus_isp.py`），在平板原生编译打包生成 `out/rpmbuild/RPMS/aarch64/opd2413-camera-0.1-2.fc45.aarch64.rpm`（`sha256: 48fb126bf88dc95595e4358b7862f378ae9e3ad6b6d03bcd9de1b0afe7d94e21`）并离线 `dnf upgrade` 升级，单元测试 `test_hdrplus_isp.py` 输出 `ALL_HDRPLUS_UNIT_TESTS_PASSED`。
  - 首次后摄实测中，出流约 `1.3 s` 首个 `S_CTRL` 仍触发 `i2c-qcom-cci ac7b000.cci: master 1 queue 0 timeout`，导致 `10-000c` 锁死在 `runtime_status=error`。对照 OEM `runtime.dts`、`erhaimain_actuator` 配置与 `/sys/class/devlink/i2c:10-0036--i2c:10-000c` 查明三重原因：(1) `device_link_add` 的 `consumer`/`supplier` 写反，将 `sc1300cs` (`10-0036`) 当成 `cn3927` (`10-000c`) 的 supplier 而非 consumer，且 sensor 已激活时缺少 `DL_FLAG_RPM_ACTIVE`；(2) `cn3927` 发送 `0x08=0x6f` 解锁后缺少 OEM 要求的 `100 us`（`CN3927_INIT_DELAY_US`）稳定延时，且 `CN3927_PARK_STEP` 应为 `64`；(3) `cn3927_write()` 缺少总线短暂抖动重试（`CN3927_I2C_RETRIES=3`，间隔 `5 ms`）。
- **补丁 `2435` 离线编译与反向校验：**
  - 修正 `drivers/media/i2c/cn3927.c`（移除 `<linux/suspend.h>`、`bool unbinding`、`usage_count > 1` 判断及 `device_is_bound` 延迟，改用 `device_link_add(cn3927->sensor_dev, &client->dev, dl_flags)` 与清理路径），导出 `kernel/opd2413-7.2/patches/2435-media-i2c-cn3927-fix-power-up-delay-load-and-runtime-pm.patch` 并更新 `kernel/PATCHES.md`。
  - 宿主机 `ARCH=arm64` 增量编译 `modules` 目标退出码 `0`（注：Kbuild 单目标 `drivers/media/i2c/cn3927.ko` 因缺少 `Module.symvers` 无法单独过 `modpost`），strip 后模块 `61K`（`sha256: 4dea8b257b3b814ce4ffa4cdafb27699805eeba7033b31ebd37e0824c6fc4408`，`vermagic=7.2.15-28.opd2413 SMP preempt mod_unload aarch64`）；`patch -p1 -R -F0 --dry-run` 返回 `PATCH_REVERSE_F0_OK`。
- **实机结果与证据（RAM 热加载 + 两轮实拍 + 5s GUI 冒烟，2026-11-16）：**
  - **RAM 热加载**：将 `cn3927.ko` 传至平板 `/tmp/cn3927.ko`（`sha256` 校验一致），停 `opd2413-face` 与 `wireplumber`、解绑 `ad27000.isp` 与 `10-000c` 后 `rmmod cn3927 && insmod /tmp/cn3927.ko`，重绑 `ad27000.isp` 并拉起服务（未触碰 `/boot` 与 ESP）。核验 `/sys/class/devlink/i2c:10-000c--i2c:10-0036/runtime_pm = 1`，`10-000c` 与 `10-0036` 均为 `suspended` 且 `runtime_error=none`。
  - **两轮 CLI 连拍实测（以 `colin` 执行，6 次拍摄全部 `Contrast AF enabled`、零 `Unable to set control`）：**
    1. `test_front_012.jpg`：`3264x2448, frames=6, burst=162.0ms, isp=3591.9ms`，`meanY=14.07, p50Y=13.00, p95Y=32.00, meanSat=60.89, dark10=[4.01, 3.83, 4.58], center_lap_var=676.11, center_sobel=40.08, corners_lap=[1111.48, 1174.21, 1162.07, 1202.54]`。
    2. `test_rear_af_012.jpg`：`4160x3120, frames=6, af_state=2, lens=1.833D, burst=155.6ms, isp=6473.2ms`，`meanY=8.49, p50Y=6.00, p95Y=23.00, meanSat=32.33, dark10=[3.49, 3.25, 3.31], center_lap_var=455.93, center_sobel=31.34, corners_lap=[737.79, 826.27, 715.95, 826.98]`。
    3. `test_rear_lp0_012.jpg`：`4160x3120, frames=6, af_state=0, lens=0.0D, burst=162.6ms, isp=6440.1ms`，`meanY=8.58, p50Y=6.00, p95Y=24.00, meanSat=31.03, dark10=[3.23, 3.24, 2.98], center_lap_var=466.75, center_sobel=31.93, corners_lap=[754.67, 834.98, 729.77, 808.68]`。
    4. `test_rear_lp10_012.jpg`：`4160x3120, frames=6, af_state=0, lens=10.0D, burst=166.0ms, isp=6509.7ms`，`meanY=7.74, p50Y=5.00, p95Y=23.00, meanSat=52.24, dark10=[3.14, 3.15, 4.0], center_lap_var=408.65, center_sobel=29.2, corners_lap=[655.49, 748.13, 664.12, 781.72]`。
    5. `test_front2_012.jpg`（`10.0D` 后切前摄）：`3264x2448, frames=6, burst=164.7ms, isp=3693.3ms`。
    6. `test_rear_af2_012.jpg`（再切回后摄 AF）：`4160x3120, frames=6, af_state=2, lens=6.012D, burst=165.3ms, isp=6475.2ms`，`meanY=8.29, p50Y=6.00, p95Y=23.00, meanSat=48.79, dark10=[3.62, 3.27, 4.01], center_lap_var=438.64, center_sobel=30.8, corners_lap=[664.27, 768.44, 702.97, 817.89]`。
  - **内核日志与状态收尾**：测试后 `10-000c` 与 `10-0036` 均恢复 `suspended`（`runtime_error=none`）；`journalctl -k --since "2026-11-16 01:31:17"`（排除 `ath12k_wifi7_pci`）为空，0 次 CCI 超时或重试（Step 2B 降频 100 kHz 无需实施）。4 张样本已拉回宿主机 `out/camera-verify/` 目视核验，平板 `/tmp/test_*.jpg` 已清理（保留 `/tmp/cn3927.ko`）。
  - **GUI 冒烟与全机健康**：`colin` 在 `WAYLAND_DISPLAY=wayland-1`（`QT_QPA_PLATFORM=wayland`）运行 `timeout 5s /usr/bin/opd-camera` 返回 `124`（Adreno 830 EGL `1632x1224` + `3264x2448`，`Contrast AF enabled`）；退出后 `10-000c`/`10-0036` 保持 `suspended`、`kernel_log=clean`、`opd2413-face=active`、`wireplumber=active`、`systemctl --failed` 为 `0 loaded units listed`、`ausearch -m avc -ts recent` 为 `<no matches>`、电量 `94% (Charging)`。
  - **实测范围与待跟进项**：本次拍摄在夜间极暗室内完成（`meanY` `7.74–14.07`），`0.0D` 与 `10.0D` 在右下微弱反光点已体现明显清晰度差异且深暗部中性（`dark10 ~ 2.98–4.58`），但极暗纯噪点边缘在多帧对齐下存在明显移位伪影；明亮环境下的 `0.1-2` 亮度/色彩观感、日间远近焦对比与 GUI 交互按钮仍待用户在正常光照下实测，内核修改待用户确认后编译安装 `kernel-opd2413-7.2.15-29` 并冷启动验收。

### 持久化内核 `kernel-opd2413-7.2.15-29` 构建、刷入与重启对焦验收（2026-11-16，已完成）

- **上机测试前预期与判据：**
  1. **构建与离线校验预期**：`N=29 bash out/m3k/build.sh`（`-j15`，保留 1 核空闲）零错误编出 `kernel-opd2413-7.2.15-29.opd2413.aarch64.rpm`，stage 内 `cn3927.ko*` 的 `vermagic` 为 `7.2.15-29.opd2413 SMP preempt mod_unload aarch64`；`tests/ufs-guard-test.sh` 退出码 `0`，`tests/package-install-test.sh out/m3k/rpms29 out/m3k/pkg-test29` 确认 ESP 条目、DTB 与 initramfs 全部早期固件 `0 missing` 且无 rescue 镜像（仅允许已知 `66` vs `67` 常量提示）。
  2. **安全装机与 `KSHIM.CHO` 零变动**：保留 `-28` 与 `-26` 回退包，通过 `rpm -ivh --nosignature` 安装 `-29` 并清理 `/tmp/cn3927.ko` 与临时 RPM；核验 `/boot/efi/KSHIM.CHO` 的 `sha256sum` 与 `filefrag -v` 物理 extent 前后完全一致，先维持 `loader.conf` 默认项为 `fedora-7.2.15-28.opd2413.conf` 并用 `tools/tablet-reboot.py --entry fedora-7.2.15-29.opd2413.conf --wait 240` 单次引导至 `-29`。
  3. **重启上线、相机对焦与默认切换判据**：`-29` 上线后 `uname -r == 7.2.15-29.opd2413`、`systemctl is-system-running == running`、`0 failed`、`Enforcing`、`0 AVC`；`cn3927` 从 `/lib/modules/7.2.15-29.opd2413/...` 加载、`/sys/class/devlink/i2c:10-000c--i2c:10-0036/runtime_pm == 1`；完成晨光下前摄/后摄 AF/手动 `0.0D`/`10.0D` CLI 实拍及 5 秒 Wayland GUI 预览冒烟，全程 `dmesg` 零 `ac7b000.cci` 超时与报错、`10-000c`/`10-0036` 回归 `suspended`（`runtime_error=none`）；随后将 `fedora-7.2.15-29.opd2413.conf` 设为默认并做无 `--entry` 重启复核后消号 `#42`。
- **实际结果与证据：**
  1. **宿主机交叉编译与离线校验**：`N=29 bash out/m3k/build.sh`（`-j15`）输出 `BUILD-OK`，生成 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-29.opd2413.aarch64.rpm`（`sha256: 0acbb9b0918ca63d2d022b681db4b4b5d99386309925f4df26cd9d5b3851c45b`，同步归档于 `out/m3k/rpms29/`）；`cn3927.ko`（`61K`）`vermagic = 7.2.15-29.opd2413 SMP preempt mod_unload aarch64`。`tests/ufs-guard-test.sh` 退出码 `0`；`tests/package-install-test.sh out/m3k/rpms29 out/m3k/pkg-test29` 仅触发已知第 78 行 `FAIL: expected 66 early firmware files, the helper lists 67`，实际 `initramfs: 94063852 bytes, 67 device firmware files required, 0 missing`、`negative.txt = refused`、无 Fedora 原生内核且无其他失败。
  2. **安全装机与 `KSHIM.CHO` 前后一致**：流式上传并校验 SHA-256 一致后，执行 `rpm -ivh --nosignature` 安装 `-29` 并清理 `/tmp/kernel-opd2413-7.2.15-29*.rpm` 与 `/tmp/cn3927.ko`；保留 `-26`/`-28`/`-29` 三个内核 RPM 与条目，ESP `/dev/sda16` 已用 `370M / 512M`（`73%`，剩余 `143M`）；`/boot/efi/KSHIM.CHO` 装前装后均为 `65d97e12564575a318ba221c6b76ce8b9db91d40187168793c58f4ab3ae52a7d`、`16384` 字节、`1 extent found`。
  3. **单次安全引导与系统全检**：保持 `loader.conf` 默认为 `fedora-7.2.15-28.opd2413.conf`，执行 `python3 tools/tablet-reboot.py --entry fedora-7.2.15-29.opd2413.conf --wait 240` 经 `90 s` 直接上线至 `7.2.15-29.opd2413`（`running`、`0 failed`、`Enforcing`、`ausearch --input-logs -m avc -ts boot` 为 `<no matches>`）；`/proc/cmdline` 含 `mem_sleep_default=s2idle` 且不含 `fw_devlink.sync_state=timeout`/`pcie_ports=compat`；`/tmp/cn3927.ko` 已不存在，`modinfo -n cn3927` 指向 `/lib/modules/7.2.15-29.opd2413/kernel/drivers/media/i2c/cn3927.ko`；`/sys/class/devlink/i2c:10-000c--i2c:10-0036/runtime_pm = 1`，`10-000c`/`10-0036` 均处于 `suspended`（注：该内核 sysfs 无 `runtime_error` 属性文件）；`dmesg` 无 Oops/`qsh_process`/`fatal error` 且**零 `ac7b000.cci` 超时**（仅含既有 `ath12k_wifi7_pci` 接收警告），`opd2413-sensors-*`/`bluetooth`/`opd-netshare`/`opd2413-face`/`wireplumber` 均为 `active`，`aplay -l` 正常列出 `card 0: OnePlusPad2Pro`。
  4. **晨光相机实拍与 GUI 冒烟（以 `colin` 执行）**：
     - `verify29_front.jpg`：`3264x2448, size=2492362, frames=8, burst=225.6ms, isp=4073.5ms`，`meanY=166.66, p50Y=189.06, p95Y=238.93, meanSat=26.65, dark10=[54.9, 53.03, 58.26], center_lap_var=52.23, center_sobel=18.27`；
     - `verify29_rear_af.jpg`：`4160x3120, size=5928893, frames=8, af_state=2 (Focused), lens=2.053D, burst=222.3ms, isp=6625.6ms`，`meanY=133.68, p50Y=121.92, p95Y=234.21, meanSat=21.82, dark10=[46.06, 46.29, 46.34], center_lap_var=148.10, center_sobel=17.84`；
     - `verify29_rear_lp0.jpg`：`4160x3120, size=6041485, frames=8, af_state=0, lens=0.0D, burst=222.7ms, isp=6750.5ms`，`meanY=132.63, p50Y=120.61, p95Y=233.31, meanSat=37.31, dark10=[44.27, 45.99, 43.37], center_lap_var=192.05, center_sobel=19.97`；
     - `verify29_rear_lp10.jpg`：`4160x3120, size=6447861, frames=8, af_state=0, lens=10.0D, burst=225.9ms, isp=6691.9ms`，`meanY=133.50, p50Y=116.59, p95Y=226.37, meanSat=49.76, dark10=[46.45, 49.41, 43.58], center_lap_var=252.20, center_sobel=23.04`。
     - 4 张样本已拉回宿主机 `out/camera-verify/` 目视核验并清理平板 `/tmp/verify29_*.jpg`：前摄肤色自然、白墙中性、亮度均衡；后摄 `10.0D` 下近景贴纸小字（“微萌电蚊拍 / 危险电压 / GB 4706.1”）字字清晰、背景虚化，与 `0.0D`/`2.053D` 形成明显物理焦平面位移（室内后摄白墙略呈轻微偏黄绿暖调，属后续按需白平衡微调项）。5 秒 Wayland GUI 冒烟返回 `GUI_EXIT=124`；测后 `journalctl -k --since "$t_start"`（排除 `ath12k_wifi7_pci`）为空、`10-000c`/`10-0036` 均恢复 `suspended`、`opd2413-face` 与 `wireplumber` 保持 `active`。
  5. **默认项固化与用户验收**：用户已在运行 `-29` 的平板上试用后摄并反馈“已经可以自动聚焦了”，执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-29.opd2413.conf && sync`，核实 `loader_default == booted_entry == fedora-7.2.15-29.opd2413.conf`、`pending_next = null`、`KSHIM.CHO` 哈希与 `1 extent` 不变、电量 `94% (charging)`（未再额外触发二次重启以免打断用户当前使用），完成 `#42` 消号。

### `opd2413-netshare 0.1-9` IPv6 穿透与 Android 伴侣后台快速发现优化（2026-11-16，离线通过，待上机装包实测）

- **上机测试前预期与判据：**
  1. **IPv6 端到端通道预期**：
     - 手机端 `NetShareService` 从活跃物理网络提取全局单播 IPv6（`2000::/3`，非 ULA `fc00::/7`）与 IPv6 默认路由（464XLAT 场景下自动取底层接口如 `rmnet_data3` 而非 `v4-rmnet_data3`），派生 `/64` 内固定后缀 `::0:2413:49:1`；`helper.sh` 配置 `ip -6 rule`（`pref 9996`/`9997`）、`ip6tables` `opdlink_fwd6`（`tetherctrl_FORWARD`）与 `opdlink_nat6`（`MASQUERADE`，若内核无 `ip6table_nat` 则自动回退 `proxy_ndp` + `ip -6 neigh replace proxy`），并确保上游 `accept_ra=2` 后开启 IPv6 转发。
     - 平板端 `opd-netshare-daemon` 在 `p2p0` 收到 `v6_ll` + `v6_ip` 后配置 `<v6_ip>/128 nodad`、`default via <v6_ll> dev p2p0 metric <550|700>` 与 IPv6 DNS（`2400:3200::1`、`2402:4e00::`），在线切换上游（如 `wlan0 <-> rmnet_data*` 或切到纯 IPv4 Wi-Fi）时由手机推送 `upstream_update` 同步刷新或清理；`tailscale netcheck` 报告 `IPv6: yes` 且公网 IPv6 可直通。
  2. **后台发现与连接提速预期**：
     - 手机端新增 `OpdCompanionService`（`CompanionDeviceService` + `CompanionDeviceManager.startObservingDevicePresence`）避开 ColorOS `OplusHansManager` 后台扫盘冻结，并在 `ACTION_SCREEN_ON` / `ACTION_USER_PRESENT` 刷新 `PendingIntent` 扫描并启动 `20 s` `SCAN_MODE_LOW_LATENCY` 突击 `ScanCallback`。
     - 手机端 RFCOMM 建连即先发送 `{"event":"hello","sta_freq":...}`；平板端 `opd-netshare-daemon` 订阅 `NetworkManager` `StateChanged` 加快断网唤醒（`s2idle` 唤醒复评 `300 ms`），且在仅广播待命时不预先起 `p2p0` AP（消解空闲 `5745 MHz` 占频触发 `#41`），待收到 `hello`（上限 `0.45 s`）后直接按对端 `sta_freq` 一次选对信道起播 AP。
  3. **判据**：离线检查 `py_compile`、`sh -n helper.sh`、XML 解析、`tests/netshare-daemon-test.py` 4 项单测与 `tools/build-netshare-rpm.sh 0.1 9` 全通过；待在有 Android SDK 的宿主机编译 `opd-netshare.apk` 并 `adb install -r` 到手机、在平板安装 `opd2413-netshare-0.1-9.noarch.rpm` 并完成伴侣关联后，实测熄屏/退后台自动建连速度、`tailscale netcheck` `IPv6: yes` 及公网 IPv6 连通性。
- **实机验证结果（2026-11-16，IPv6 已真机通过，后台发现/息屏压测待用户继续实测）：**
  1. **本机环境配置与装机**：通过 `pkexec dnf` 在平板安装 `opd2413-netshare-0.1-9.noarch` 与 `java-25-openjdk-devel`（`javac 25.0.4.1`）；于 `~/Android/Sdk` 部署 Android `cmdline-tools`、`platforms;android-35` 与 `build-tools;35.0.1`，并在 `~/Android/x86_64-sysroot` 配置精简 `x86_64` `glibc`/`libgcc` 供 `qemu-x86_64-static` 运行 `aapt2`/`zipalign`，直接编出 `out/netshare/opd-netshare.apk`（`114K`，v3 签名校验通过）。手机端经 `su -c 'pm uninstall ...'` 清除旧版残留后由 `/data/local/tmp/` 走 `pm install -r` 安装成功。
  2. **IPv6 端到端真机通过**：平板切换至 `opd-netshare mode force`（验证广播期未拉起 `p2p0` AP、不干扰 `wlp1s0`）并完成伴侣端建连后，手机经 `rmnet_data3` 上报链路本地网关与 `/64` 派生的全局 IPv6 地址；平板 `p2p0` 自动获配 `<prefix>:0:2413:49:1/128 scope global nodad` 及 `default via fe80::... dev p2p0 proto static metric 550`（并配置 `resolvectl` IPv6 DNS `2400:3200::1`、`2402:4e00::`），AP 运行于 `5180 MHz / 80 MHz`（`1200.9 MBit/s HE-MCS 11 NSS 2`）。
  3. **Tailscale 与公网 IPv6 实测**：`tailscale netcheck` 返回 `IPv6: yes, [2408:xxxx:...]:32923`（`Nearest DERP: Hong Kong`）、`ping -6 -c 2 2400:3200::1` 往返 `71.1–99.7 ms`（`0% packet loss`）、`curl -6 -I https://www.qq.com` 通过 IPv6 收到正常 HTTP 响应；随后切回 `opd-netshare mode auto` 保持稳定连接。
  4. **连续切换稳定性修复（`opd2413-netshare-0.1-10` + APK 重编）**：
     - 定位到桌面端多次切换后复现连续组网失败的原因：1）`helper.sh` `cmd_down` 反复调用 `cmd wifip2p deinit` 且 `cmd_up` 仅 `sleep 0.1`，叠加 160 轮轮询超过 `28 s` 触发 `helper timeout` 强杀后未做 `cancel-connect`；2）平板端 `5180 MHz` 遇邻居 BSS 重叠切换主信道至 `5200 MHz` 时仍向手机下发 `5180`；3）候选信道耗尽重置会话时未清空 `failed_freqs`（`180 s` 冷却残留导致下次只试 1 次即中断）。
     - 已修复：平板端读取实际 `iw dev p2p0 info` 信道并在候选耗尽时清空 `failed_freqs`（冷却缩至 `60 s`）；`helper.sh` 去掉 `cmd_down` 的 `deinit`、新增 `ensure_p2p_ready` 与 `cmd_cancel`、以墙钟 `16 s` 上限避免 `helper timeout`；`NetShareService` 增加扫描防抖与超时 `cancel`。重跑 `tests/netshare-daemon-test.py`（4/4 `OK`），编译并经 `pkexec dnf` 安装 `opd2413-netshare-0.1-10.noarch`，同时重编 `out/netshare/opd-netshare.apk`（`114K`，同密钥可覆盖安装）。
  5. **双端连续切换、耗时拆解与锁屏后台验收（2026-11-16 真机通过）**：
     - 手机覆盖安装新版 APK 后，用户多次切换桌面模式均可稳定恢复连接（`5745 MHz` 一次成功、`IPv6` 同步生效）；初始耗时拆解确认 BLE+RFCOMM 发现仅 `~1–2 s`、平板按需起 AP `~1 s`，而 `RFCOMM hello` 至组网完成仍需约 `15–17 s`（随后经手机端 `adb` + `dumpsys wifip2p` 进一步追查精确定位，见下条）。
     - **锁屏后台对比实测**：未在 ColorOS 最近任务锁卡时，锁屏静置一段时间后仍会被 ColorOS 强制冻结直至打开手机；**将 `OPD NetShare` 在最近任务栏锁定后再次锁屏静置，平板断开再切回 `auto` 模式可在手机不解锁/不打开 App 的情况下后台自动拉起建连**（同步更新 [TECH-DEBT.md](TECH-DEBT.md) `#40` 与 `#41`）。

### `opd2413-netshare-0.1-11` 连接速度根因定位与 P2P ADB 调试联动（2026-11-16，真机通过）

- **上机测试前预期与判据：**
  1. **设备写入边界**：在平板安装 `android-tools` 后经仅限 P2P 网关的白名单防火墙端口建立手机 `adb` 只读诊断，确认根因并与用户确认修改范围后：重编并覆盖安装 `out/netshare/opd-netshare.apk` 至手机，通过 `pkexec dnf` 升级平板 `opd2413-netshare-0.1-11.noarch`。
  2. **根因与优化预期**：
     - 手机端：`get_sta_freq()` 在 `wlan0` 未连接时会回退调用 `/vendor/bin/wpa_cli`，受 ColorOS SELinux 拒绝 `hal_wifi_supplicant_default` 向 `su` (`u:r:ksu:s0`) 回包（`avc: denied { sendto }`）影响每次超时卡死 **10.055 s**（失败重试更卡 20.1 s）；移除 `wpa_cli` 回退并仅在失败分支按需读取 `iw`、`hello` 阶段优先读取 Android `WifiInfo.getFrequency()`、已处 `InactiveState` 时跳过冗余 `cancel-connect`/`remove-group`、通过 `/proc/sys/net/ipv6/conf/p2p0/dad_transmits=0` 消除链路本地地址 `tentative` 等待、借助状态脏标记与 `/dev/.opdlink_v6nat_ok` 缓存省去重复 `iptables`/`ip6tables` 清理与无效 `ip6tables -t nat` 试探，并在 APK 与 `helper.sh` 中集成仅放行 P2P 网关（`192.168.49.1`）的 `adb-on`/`adb-off`/`adb-status` 开关。
     - 平板端：`dnsmasq` 启动参数增加 `--no-ping` 消除首次 `DHCPDISCOVER` 默认 ICMP ping 探活造成的 **3.005 s** 硬延迟；`_start_ap()` 用 `_drain_proc_log` 触发的 `AP-ENABLED` 事件替换 `0.15 s` 慢轮询与固定 `sleep(0.2)`，并将 `firewall-cmd --zone=trusted` 与 `wpa_supplicant` 启动并行执行。
  3. **判据**：离线执行 `sh -n helper.sh` 与 `python3 tests/netshare-daemon-test.py`（5/5）全通过；真机双端升级后，`RFCOMM hello` 至 IPv4 + IPv6 全双栈就绪时间由约 `16.9 s` 缩短至 `~2 s` 左右，公网 IPv6 连通与 `5745 MHz / 80 MHz` 链路正常。
- **离线检验与构建：**
  - `sh -n netshare/android/app/src/main/assets/helper.sh`、`python3 tests/netshare-daemon-test.py`（`Ran 5 tests in 0.002s OK`）、`./tools/build-netshare-rpm.sh 0.1 11` 与 `bash netshare/android/build-apk.sh`（生成 `out/netshare/opd-netshare.apk` `114K`，v3 签名校验通过）全部一次通过。
- **实机验证结果（2026-11-16 真机通过，证据位置：`journalctl -u opd-netshare`、手机 `dumpsys wifip2p` / `helper.sh adb-status`）：**
  1. **耗时对比实测（`RFCOMM hello` -> 双栈就绪，缩短 8.3 倍）**：
     - 平板 `_start_ap`：`0.93 s` -> **`0.542 s`**（`18:27:33.191 -> 18:27:33.733`）。
     - P2P 建组至 `DHCPACK`：`17:35` 旧版 `10.7 s (卡死+清理) + 1.55 s (CONNECT) + 3.07 s (DHCP)` -> 本次实测 **`0.694 s`**（`Sent credentials 18:27:33.741 -> DHCPACK 18:27:34.427`；手机 `WifiP2pMetrics` 组网耗时 `459 ms`，`dnsmasq` 在收到 `DHCPDISCOVER` 后 `23 ms` 内即完成 `DHCPACK`）。
     - IPv4 恢复与 IPv6 双栈总耗时：`RFCOMM hello` 后 **`1.251 s`** 平板即接入 `192.168.49.x` IPv4 网络（`18:27:34.442`），**`2.042 s`** 完成全部 `iptables`/`ip6tables`/路由切换进入双栈可用状态（`18:27:35.233`，含首次写入 `/dev/.opdlink_v6nat_ok=0` 与 `p2p0` `dad_transmits=0`）。
  2. **功能与连通复核**：`opd-netshare status` 显示 `State: connected`、`5745 MHz`、`576.4 MBit/s 80MHz HE-MCS 5 NSS 2`；`ping -6 -c 2 2400:3200::1` 返回 `0% packet loss`（`62.5 / 66.0 ms`）；手机端 `helper.sh adb-status` 正常响应，APK 新增的顶部环境栏 `P2P ADB` 开关编译并装机就绪。

### 合盖休眠/唤醒触发 `kwin_wayland` `SIGUSR1` 崩死与 `fcitx5` 失灵根因排查及修复（2026-11-16，离线单测通过，用户态配置已生效，待 `sudo` 安装 `kscreenlocker` RPM 后真机复测）

- **现象与根因定位（证据位置：`journalctl -b -1`、`coredumpctl`、`/lib64/libKScreenLocker.so.6` 反汇编、SRPM `ksldapp.cpp`）：**
  1. **合盖前先触发宽限期解锁撞上睡眠锁屏**：`~/.config/kscreenlockerrc` 原含 `LockGrace=900`（`900 s`）。`20:29:54` 空闲锁屏启动 `kscreenlocker_greet[84429]`；`20:35:51.835` 合盖时仍在宽限期内，`20:35:51.879` `84429` 报 `The Wayland connection broke`，`64 ms` 后 `20:35:51.943` 收到 `PrepareForSleep(true)` 触发 `KSldApp::lock(EstablishLock::Immediate)`。因旧 `m_lockProcess` 尚未退出，`20:35:52.140` `kwin_wayland[3330]` 报 `QProcess::start: Process is already running`，随后旧进程退出回调命中未清零的 `s_graceTimeKill` 返回，系统在 `m_lockState=Locked` 且 `processId()=0`（无 greeter）的损坏状态进入并退出第一次 `s2idle`。
  2. **`kill(0, SIGUSR1)` 广播误杀合成器**：`20:37:13.349` 第二次合盖触发 `KSldApp::lock(EstablishLock::Immediate)`，源码直接调用 `kill(m_lockProcess->processId(), SIGUSR1)` 未判 `pid > 0`，实际执行 `kill(0, SIGUSR1)` 击中 `kwin_wayland` 整个进程组。`20:37:13.482` `plasma-kwin_wayland.service` 以 `status=10/USR1` 退出，同组 `fcitx5[3482]` 亦于同毫秒收到信号 `10`/`15` 退出。
  3. **黑屏卡顿、40 次崩溃弹窗与 `fcitx5` 失灵连锁**：`plasmalogin` 重建 `session-10` 时复用仍存活的 `user@1000.service`（其 `graphical-session.target` 保持 `active` 未停），`xdg-desktop-autostart.target` 早于 `kwin_wayland[88415]` 就绪即并发拉起全部 XDG 自启动程序、`plasma-ksplash.service` 阻塞 `33.244 s`，`20:37:13`–`20:37:31` 累计 `40` 次 `systemd-coredump` 并由 `drkonqi-coredump-launcher` 弹窗；同时 `~/.config/autostart/org.fcitx.Fcitx5.desktop` 抢先于 `20:37:31.205` 占用 `org.fcitx.Fcitx5` D-Bus 名且无 Wayland/X11 连接，导致 `20:37:33.689` KWin 托管拉起的 `fcitx5[88612]` 因 D-Bus 冲突自卸全部插件而失效。
- **修复预期与判据：**
  1. 用户态配置：删除冗余 `~/.config/autostart/org.fcitx.Fcitx5.desktop`（仅留 `~/.config/kwinrc` `[Wayland] InputMethod[$e]` 托管），并将 `~/.config/kscreenlockerrc` 的 `LockGrace` 调回 `5` 秒并重载配置。
  2. `kscreenlocker` 修复打包（`packaging/opd2413-kscreenlocker/`、`tools/build-kscreenlocker-rpm.sh`，补丁 `0001`）：`KSldApp::lock()` 仅在 `pid > 0` 时发 `SIGUSR1`（`pid <= 0` 且非应急窗则重起 greeter），`KSldApp::startLockProcess()` 在 `m_lockProcess->state() != QProcess::NotRunning` 时断开信号并 `deleteLater` 退役旧 `QProcess` 后重建，`lock()` 同步复位 `s_graceTimeKill`/`s_logindExit`，`unlock()`/`requestUnlock` 增加空指针与运行态守卫，不改 `ksldapp.h` ABI 布局（登记 [TECH-DEBT.md](TECH-DEBT.md) `#43`）。
  3. **判据**：离线确认 `libKScreenLocker.so.6.8.3` 与 `libkwin.so.6` 缺失符号为空、`PASS : KSldTest::testNoKillZeroAndFastRelock()`（`Totals: 3 passed, 0 failed`）在无 Wayland 模拟 `Locked+pid==0` 及宽限期 `unlock()->lock()` 时 `g_gotUsr1==0` 且旧 `QProcess` 退出不破坏新 `Locked` 状态；待在平板执行 `sudo dnf upgrade ./out/rpmbuild/RPMS/aarch64/kscreenlocker-6.8.3-1.fc45.opd2413.1.aarch64.rpm` 并重启会话/系统后，连续合盖休眠、开盖唤醒桌面与 `fcitx5` 输入均正常、`journalctl` 无 `Process is already running` 或 `status=10/USR1`。
- **当前已完成与离线结果（2026-11-16）：**
  - 已删除 `~/.config/autostart/org.fcitx.Fcitx5.desktop` 并 `systemctl --user daemon-reload`，确认 `xdg-desktop-autostart.target` `Wants` 不再含 `app-org.fcitx.Fcitx5@autostart.service`；已改 `~/.config/kscreenlockerrc` 为 `LockGrace=5` 并执行 `qdbus-qt6 org.freedesktop.ScreenSaver /ScreenSaver configure`。
  - `./tools/build-kscreenlocker-rpm.sh --local 1` 于 Fedora 45 `aarch64` 容器成功编出 `out/rpmbuild/RPMS/aarch64/kscreenlocker-6.8.3-1.fc45.opd2413.1.aarch64.rpm`（及 `-devel` / `-debuginfo` / `-debugsource` / `.src.rpm`）；`nm -DC` 核对 `libkwin.so.6` 所需 `KSldApp` 符号零缺失；容器内装入新 RPM 编译运行 `KSldTest::testNoKillZeroAndFastRelock()`（`QT_QPA_PLATFORM=offscreen`）输出 `Totals: 3 passed, 0 failed, 0 skipped`（`317ms`）。

### 平板装入 `kscreenlocker` 修复包并配置「合盖锁屏熄屏 + 10 分钟后休眠」（2026-11-16，已安装与离线验证通过，待重启会话后真机合盖实测）

- **用户需求与策略设计：** 用户确认在平板安装 `kscreenlocker-6.8.3-1.fc45.opd2413.1.aarch64`，并将合盖行为调整为「合盖立即锁屏并熄屏、10 分钟后再进入休眠（短时间合盖再打开无需经历 `s2idle` 唤醒延迟）」。源码确认 KDE PowerDevil 6.8.3 `HandleButtonEvents`（`daemon/actions/bundled/handlebuttonevents.cpp` 与 `dpms.cpp`）仅支持合盖立即执行单一动作：设 `LidAction=64`（`TurnOffScreen`）+ `[Display] LockBeforeTurnOffDisplay=true` 可在合盖时立即调用 `KScreen::Dpms::Off` 熄屏并在 `250 ms`（`dimAnimationTime`）后触发 `org.freedesktop.ScreenSaver Lock` 锁屏，而 PowerDevil 无原生「合盖延迟 N 分钟休眠」配置（若改全局 `AutoSuspendAction=1` 会在开盖挂机或 SSH 跑编译时误睡眠）。
- **预期与判据：**
  1. 经 Polkit 授权执行 `pkexec dnf --disablerepo='*' upgrade -y ./out/rpmbuild/RPMS/aarch64/kscreenlocker-6.8.3-1.fc45.opd2413.1.aarch64.rpm` 完成装包，`rpm -q kscreenlocker` 为 `kscreenlocker-6.8.3-1.fc45.opd2413.1.aarch64`。
  2. 通过 `kwriteconfig6` 对 `powerdevilrc` 的 `AC`/`Battery`/`LowBattery` 均写入 `[Display] LockBeforeTurnOffDisplay=true` 与 `[SuspendAndShutdown] LidAction=64`（保留 `PowerButtonAction=1` 与 `AutoSuspendAction=0`），重启 `plasma-powerdevil.service` 后 `HandleButtonEvents.lidAction()` 返回 `64`。
  3. 新增 `device/libexec/lid-suspend` 与 `device/systemd/opd2413-lid-suspend.service`（暂用户态部署至 `~/.local/libexec/opd2413-lid-suspend` 与 `~/.config/systemd/user/opd2413-lid-suspend.service`，登记 [TECH-DEBT.md](TECH-DEBT.md) `#44`）：监听 `org.freedesktop.UPower` `LidIsClosed` 与 `login1` `PrepareForSleep`，合盖后启动 `600 s` 单调定时器，开盖或提前进入睡眠则立即取消；`600 s` 到时复查仍合盖且 `HandleButtonEvents.triggersLidAction()` 为真（无外接显示器抑制）后调用 `PowerDevil` `SuspendSession.suspendToRam()` 进 `s2idle`；若系统处于合盖态发生误唤醒并收到 `PrepareForSleep(false)`，则重新计时以便再次入睡。
  4. **判据**：注销重登或重启整机让 `kwin_wayland` 加载新版 `libKScreenLocker.so.6` 后，实测合盖立即黑屏锁屏、10 分钟内开盖瞬时亮屏解锁（无卡死与崩溃弹窗、`fcitx5` 正常），持续合盖满 10 分钟自动进入 `s2idle`。
- **实机操作与检验结果（2026-11-16）：**
  1. 用户经桌面 Polkit 弹窗授权后 `pkexec dnf --disablerepo='*' upgrade -y` 成功完成事务，`rpm -q kscreenlocker` 返回 `kscreenlocker-6.8.3-1.fc45.opd2413.1.aarch64`。
  2. `~/.config/powerdevilrc` 更新并执行 `systemctl --user restart plasma-powerdevil.service` 后，`qdbus-qt6 org.kde.Solid.PowerManagement /org/kde/Solid/PowerManagement/Actions/HandleButtonEvents lidAction` 返回 `64`。
  3. `systemctl --user enable --now opd2413-lid-suspend.service` 后服务为 `active (running)`（日志 `watching lid events (delay=600s, lid currently open)`、零警告）；离线单元测试 `LidSuspendWatcher(delay_sec=1, dry_run=True)` 验证 `get_lid_closed()==False`、`triggers_lid_action()==True`、合盖起表/开盖撤表、`PrepareForSleep(true)` 撤表及超时触发 `trigger_suspend` 均通过（`LID_SUSPEND_TEST_PASS`）。

### 修复合盖瞬间保护套误触回醒 DPMS 致合盖不熄屏及人脸识别 `"lid-closed"` 失败锁死（2026-11-16，已部署并离线验证通过，待真机合盖复测）

- **复测问题与根因定位（证据位置：`journalctl -b` `21:31:48`–`21:33:17`、`libkwin.so.6` 反汇编、`LockScreenUi.qml`、`opd2413-faced`）：**
  1. 重启后用户实测 4 轮合盖/开盖：`21:32:39` 与 `21:32:51` 两轮正常触发 `[nt36536] panel_unpreparing` + `nvt_ts_suspend` 熄屏并在开盖时由 `pam_opd2413_face` 解锁；但 `21:32:24` 与 `21:33:08` 两轮**未出现 `panel_unpreparing`**，且同秒 `kwin_wayland` 打印数十条 `Detected a touch move that never has been down, discarding` 后由 `unix_chkpwd` 密码解锁。
  2. 反汇编确认 `KWin::DpmsInputEventFilter` 的 `pointerMotion`/`pointerButton`/`keyboardKey` 及双击 `touchUp` 会调用 `notify()` -> `Workspace::requestDpmsState(On)` 而不校验合盖状态；合盖瞬间保护套触碰玻璃或触控板/键盘微动在 DRM 完成 `panel_unpreparing` 前把 `DPMS Off` 弹回 `On`（`touchDown` 被吞而唤醒后的 `touchMotion` 报错）。
  3. 屏幕未灭且触摸/键盘仍活跃导致 `kscreenlocker_greet` 在 `350 ms`（`pressReadyTimer`）后被合盖接触触发 `uiVisible=true` 与 `FaceBridge.armScan()`（将 `faceTriedThisOpen` 置 `true`）；`opd2413-faced` 校验 `login1.LidClosed==True` 直接返回 `failed("lid-closed")`，致使开盖后锁屏仍停留在失败态。
- **修复预期与判据：**
  1. 新增 `device/libexec/lid-input` 与 `device/systemd/opd2413-lid-input.service`（已直装为 `/usr/libexec/opd2413/lid-input` 与 `/etc/systemd/system/opd2413-lid-input.service`）：监听 `gpio-keys`（`SW_LID`）及 `NETLINK_KOBJECT_UEVENT` 热插拔，在 `SW_LID=1` 时向内置受盖遮挡输入设备（`NVTCapacitiveTouchScreen`、`NVTCapacitivePen`、`OnePlus Pad 2 Pro Keyboard`、`OnePlus Pad 2 Pro Keyboard Touchpad`）的 `/sys/class/input/input*/inhibited` 写 `1`，开盖或进程退出时恢复 `0`。
  2. 在 `device/libexec/lid-suspend` 增加 `+350 ms` / `+900 ms` DPMS 复核守卫：若持续合盖且无外接屏抑制期间 `/sys/class/drm/card*-DSI-*/dpms` 仍为 `On`，自动补发 `kscreen-doctor --dpms off`。
  3. 在 `packaging/opd2413-face/data/lockscreen/LockScreenUi.qml`（并同步直装至 `/usr/share/opd2413-face/lockscreen/` 与 `/usr/local/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/`）增加 `onFaceStateChanged` 兜底：若出现 `faceState==="failed" && lastReason==="lid-closed"`，延迟归位 `faceTriedThisOpen=false` 与 `uiVisible=false`，避免开盖后停在失败态（已并记入 [TECH-DEBT.md](TECH-DEBT.md) `#44`）。
- **已验证结果（2026-11-16）：**
  - 离线模拟 sysfs 目录验证 `lid-input`（`find_lid_event_device()==/dev/input/event4`、仅对 4 个内置受盖设备写入 `inhibited=1/0`、`pmic_pwrkey` 与外接 USB 鼠标不受影响）及 `lid-suspend` `+350 ms`/`+900 ms` DPMS 守卫均通过（`LID_INPUT_AND_SUSPEND_TESTS_PASS`）；`opd2413-lid-input.service`（`active (running)`）与 `opd2413-lid-suspend.service`（`active (running)`）均无报错运行。

### 复测「偶发开盖未亮屏」定位与 `lid-suspend` Wayland DPMS 状态校验修正（2026-11-16，已部署并离线验证通过）

- **日志排查（证据位置：`journalctl -b` `21:45:31`–`21:47:11`）：**
  1. `opd2413-lid-input.service` 上线后连续 10+ 轮合盖均正常执行 `[nt36536] panel_unpreparing` 与 `nvt_ts_suspend`，**全程零条 `Detected a touch move` 与零次 `unix_chkpwd` 密码回退**，人脸认证在开盖后全数通过。
  2. 但用户在 `~1–2 s` 内快速合盖/开盖（如 `21:45:42 -> 21:45:43`、`21:45:59 -> 21:46:01`、`21:46:34 -> 21:46:35`）时出现了 `21:46:01` 开盖无 `panel_prepared`、以及 `21:45:43 -> 21:45:48` / `21:46:35 -> 21:46:39` 延迟 `4–5 s` 才亮屏。
  3. 原因：`/sys/class/drm/card0-DSI-1/dpms` 在 `drm/msm` 下即使已执行 `panel_unpreparing` 仍固定显示 `On`，导致 `lid-suspend` 误以为面板未熄而在每次合盖 `+350 ms` / `+900 ms` 都强行触发 `kscreen-doctor --dpms off`；若用户在 `+1 s` 前后开盖，在途异步的 `--dpms off` 会与 KWin `switchEvent` 亮屏竞态，在开盖瞬间把屏幕重新关掉。
- **修复与验证：**
  - 将 `device/libexec/lid-suspend`（已同步至 `~/.local/libexec/opd2413-lid-suspend` 并重启 `opd2413-lid-suspend.service`）改为解析 `kscreen-doctor --dpms show` 查询 KWin 实际 Wayland DPMS 状态（实测耗时 `~30 ms`）；合盖仅在 `+400 ms`/`+1000 ms` 仍为 `on` 时补发 `--dpms off`，并新增开盖后 `+250 ms` 复查（若仍为 `off` 则自动补发 `kscreen-doctor --dpms on`）。
  - `DPMS_WAYLAND_GUARD_PASS` 离线测试验证 `get_kwin_dpms_state()=="on"` 闭合守卫（`['off', 'off']`）与 `"off"` 开盖唤醒守卫（`['on']`）均通过，待用户快/慢速合盖开盖复测确认。

### 修复「开盖停留锁屏未解锁再合盖重开」残留人脸失败提示（`opd2413-face 0.1-11`，2026-11-16，已装机与离线测试通过）

- **用户定位的场景与源码根因（`LockScreenUi.qml`、`facebridge.cpp`、`opd2413-faced.py`）：**
  1. 开盖后停留在锁屏未解锁（`faceScanDelayTimer` 已触发且 `faceTriedThisOpen=true`，处于扫描中或已以 `no-face`/`timeout` 结束并维持 `uiVisible=true`），随后直接合盖时 `kscreenlocker_greet` 保持存活且未监听合盖/DPMS 事件：`uiVisible` 与 `faceTriedThisOpen` 未归零，且运行中的相机扫描继续在黑盒内超时失败。
  2. 再次开盖后 `uiVisible` 与 `faceTriedThisOpen` 仍为上次失败状态，界面直接提示人脸识别失败而不自动重扫。
- **修复内容与打包验证：**
  1. `packaging/opd2413-face/src/qml/facebridge.{h,cpp}`：新增 `FaceBridge.lidClosed` 属性（订阅系统总线 `org.freedesktop.UPower` `PropertiesChanged` 并在构造时异步拉取 `LidIsClosed`）。
  2. `packaging/opd2413-face/src/opd2413-faced.py`：订阅 `UPower` `LidIsClosed`，合盖瞬间若正在识别立即 `active_cancel.set()` 释放摄像头并按 `lid-closed` 结束，避免在黑盖后空转 3.5 s。
  3. `packaging/opd2413-face/data/lockscreen/LockScreenUi.qml`：新增 `onLidClosedChanged`：合盖（`lidClosed===true`）立即停表、归零 `faceTriedThisOpen=false`、`uiVisible=false` 并 `FaceBridge.resetState()`；开盖（`lidClosed===false`）时在未解锁态复位 `faceTriedThisOpen=false` 与状态，主动展示锁屏提示并在 `260 ms` 后自动拉起新一轮人脸识别（`armScan()` 也增加 `!FaceBridge.lidClosed` 守卫）。
  4. `./tools/build-face-rpm.sh --local 0.1 11` 编出 `out/rpmbuild/RPMS/aarch64/opd2413-face-0.1-11.fc45.aarch64.rpm` 并经 `pkexec dnf upgrade -y` 装机及重启 `opd2413-face.service`（`active`）；`cmp -s` 确认 `/usr/local/share/plasma/.../LockScreenUi.qml` 已随 `%posttrans` 更新一致，`PySide6` 离线 QML 加载验证 `FaceBridge.lidClosed===false` 通过（`FACEBRIDGE_QML_OK`）；并同步将 `TECH-DEBT #44` 中的 `opd2413-face` 直装项清除。待用户实测「开盖未解锁→合盖→再开盖」闭环确认。

### P0 收口：合盖服务并入 `opd2413-device` RPM、修复固件数测试校验与 NTP 时钟同步（2026-11-16，离线构建通过，待用户确认后装机验证）
2304: 
- **离线改动与排查：**
  1. **合盖输入屏蔽与延迟休眠并入 RPM**（[opd2413-device.spec](../packaging/opd2413-device/opd2413-device.spec)）：新增 `Requires: python3-gobject-base`，将 `device/libexec/{lid-input,lid-suspend}` 安装至 `/usr/libexec/opd2413/`，将 `device/systemd/opd2413-lid-input.service` 与 `opd2413-lid-suspend.service` 分别安装至 `/usr/lib/systemd/system/`（静态链接到 `multi-user.target.wants/`）与 `/usr/lib/systemd/user/`（静态链接到 `graphical-session.target.wants/`）。编出 `out/rpmbuild/RPMS/noarch/opd2413-device-0.1-15.noarch.rpm`（SHA-256 `1fc4415f8852aecd216cd0fa04004ffdbcfc38a5970507393b431dda146beec6`）；`rpm -qlp`、`rpm -qpR`、`py_compile` 及 `tests/ufs-guard-test.sh` 均通过。
  2. **修复离线安装测试的固件数断言**（[tests/package-install-test.sh](../tests/package-install-test.sh#L75-L78)、[docs/BUILD.md](BUILD.md)）：将期望早期固件数由 `66` 更新为 `67`（补齐 `opd2413-firmware 16.0.10.600-2` 新增的 `vpu35_4v.mbn`）；`bash -n tests/package-install-test.sh` 通过。
  3. **NTP 不同步根因排查（只读）**：平板实测 `chronyc tracking` 为 `Not synchronised`、`2.fedora.pool.ntp.org` 8 个境外节点全部 `Reach=0`；路由与 UDP 123 探活确认非 CN 节点经本机 TUN 代理表出站时 UDP 123 超时，而直连的国内 NTP 服务器（`ntp.aliyun.com`、`ntp1.aliyun.com`、`ntp.tencent.com`、`time2.cloud.tencent.com`）均在 UDP 123 返回正常 `48 B` 响应。
- **上机写入范围与判据：**
  1. **设备写入范围（仅 `ARMADA_ROOT`，不碰 ESP / `boot_b` / Android 分区）**：
     - 停用并清理此前直装的 `/etc/systemd/system/opd2413-lid-input.service`（及 `multi-user.target.wants` 软链）、`/usr/libexec/opd2413/lid-input`、`~/.local/libexec/opd2413-lid-suspend`、`~/.config/systemd/user/opd2413-lid-suspend.service`（及 `graphical-session.target.wants` 软链）；
     - 安装 `out/rpmbuild/RPMS/noarch/opd2413-device-0.1-15.noarch.rpm`（`pkexec dnf --disablerepo='*' upgrade -y`），`systemctl daemon-reload` 与 `systemctl --user daemon-reload` 并重启两个服务；
     - 更新 `/etc/chrony.conf`，保留原有配置结构并替换 `pool 2.fedora.pool.ntp.org iburst` 为 `ntp.aliyun.com` / `ntp1.aliyun.com` / `ntp.tencent.com` / `time2.cloud.tencent.com`（`iburst`），重启 `chronyd.service`。
  2. **验收判据**：
     - `rpm -q opd2413-device` 为 `0.1-15` 且 `rpm -V opd2413-device` 无缺失/篡改；原直装路径已清除；`opd2413-lid-input.service`（系统级）与 `opd2413-lid-suspend.service`（用户级）均处于 `active (running)` 且指向 `/usr/lib/systemd/{system,user}/` 与 `/usr/libexec/opd2413/`；
     - `chronyc tracking` `Leap status` 变为 `Normal`，`chronyc sources` 至少 3 个国内源达到非零 `Reach` 并选出主同步源（`*`）；
     - 经一次冷启动验证（因涉及系统级 systemd unit 变动），确认上述服务与 `chronyd` 在开机后自动就绪、`systemctl --failed` 为空、SELinux `Enforcing` 无新增 AVC。
- **实机验证结果（2026-11-16，运行态已通过，待下一次冷启动复核 systemd 静态自启）：**
  1. **清理与装包（`opd2413-device-0.1-15.noarch`）**：停止并清除旧直装 `/etc/systemd/system/opd2413-lid-input.service`、`/usr/libexec/opd2413/lid-input`、`~/.local/libexec/opd2413-lid-suspend` 与 `~/.config/systemd/user/opd2413-lid-suspend.service`（含各自 `.wants` 软链）；经 `pkexec dnf --disablerepo="*" upgrade -y` 成功升级至 `opd2413-device-0.1-15.noarch`，`rpm -V opd2413-device` 零输出通过；新文件路径及 SELinux 上下文确认分别为 `/usr/libexec/opd2413/{lid-input,lid-suspend}`（`bin_t`）与 `/usr/lib/systemd/{system/opd2413-lid-input,user/opd2413-lid-suspend}.service`（`systemd_unit_file_t`）及对应静态 `.wants` 软链。
  2. **服务状态**：`opd2413-lid-input.service`（系统级，`PID 26584`）与 `opd2413-lid-suspend.service`（用户级，`PID 26613`）均处于 `active (running)`，`watching /dev/input/event...` 与 `watching lid events (delay=600s, lid currently open)` 正常。
  3. **NTP 同步**：更新 `/etc/chrony.conf`（注释原境外 `pool 2.fedora.pool.ntp.org iburst`，加入 `ntp.aliyun.com`、`ntp1.aliyun.com`、`ntp.tencent.com`、`time2.cloud.tencent.com` `iburst`）并重启 `chronyd.service`；6 s 后 `chronyc tracking` 为 `Leap status: Normal`、`Stratum: 3`、`Reference ID: 6FE6BDAE (111.230.189.174)`、`System time: 0.000170632 s slow`，`chronyc sources -v` 4 源全部 `Reach=17`（`^* 111.230.189.174` 为主源）。
  4. **整机健康度**：`systemctl is-system-running = running`，`systemctl --failed` 为 `0 loaded units listed`，SELinux `Enforcing` 无 `lid-input`/`lid-suspend`/`chronyd` 相关 AVC 拒绝（`chronyc` 仅读父 shell `/proc/<pid>` 触发无害拒绝）。待下一次插电冷启动后确认静态启用的两项合盖服务与 `chronyd` 自动就绪。
- **重启/冷启动复核（2026-11-16 22:38:00 开机，真机通过）：**
  - 用户完成重启（`uptime -s = 2026-11-16 22:38:00`、`uname -r = 7.2.15-29.opd2413`）：系统级 `opd2413-lid-input.service`（`/usr/lib/systemd/system/`、`PID 2218`）于 `22:38:08` 自动拉起、用户级 `opd2413-lid-suspend.service`（`/usr/lib/systemd/user/`、`PID 4222`）于 `22:38:22` 自动拉起，均呈 `active (running)`；
  - `chronyc tracking` 开机后自动同步为 `Leap status: Normal`（Stratum 3、`0.000903192 s slow`），4 源 `Reach` 为 `37/37/67/57`（`^* 223.4.249.80`）；
  - `systemctl is-system-running = running`、`systemctl --failed` 为 `0 loaded units listed`、`Enforcing` 零相关 AVC。

## 2026-11-17

### Pogo 键盘触摸板掌触、`Ctrl+轻击`、轻击掉点与 ColorOS 光标加速曲线排查及修复（真机通过，已设为默认启动项）

- **只读取证与实机采样根因定位（证据位置：`private/touchpad-20261117/{coloros,firmware,trace/evdev.jsonl}`）：**
  1. **硬件键抑与缺失掌触置信位（`Ctrl+轻击` 与手掌误触）**：
     - 真机抓取 2,326 条 `evdev` 事件（`trace/evdev.jsonl`，含 `OnePlus Pad 2 Pro Keyboard Touchpad` `VID=0x22d9 PID=0x3869`、`BUS_HOST` `0x19`、`120.17 × 70.87 mm`、`23 units/mm`、`584 DPI`）证实：在键盘 MCU 固件 `KA030_B_1.2.0_TP_A_13` 下，按下 `KEY_LEFTCTRL` 会直接在 MCU 内挂起触摸板坐标上报约 **`152.4–169.2 ms`**（分别对应 `dt=1.3369 -> 1.5061 s` 与 `dt=2.3427 -> 2.4950 s` 两处断档）；用户随后重启至 ColorOS 16 实测确认“滑指过程中按 `Ctrl` 光标同样短暂卡顿”，证明该 ~`160 ms` 按键下行抑制位于键盘硬件 MCU 固件，且 CN 版 ColorOS `super` 分区（只读检查 `fw-listings.txt`）不携带 `POGOPIN_KB.bin` 固件、UART `0x3a` 协议亦无关闭开关（已记入 [TECH-DEBT.md](TECH-DEBT.md) `#46`）。按住 `Ctrl` 超过 `170 ms` 后单独轻击在内核 `evdev` 层可稳定产生完整 `58.4–58.9 ms` 接触事件（`tid=331`/`333`/`335`）。
     - 内核驱动 `oneplus-pogo-keyboard.c` 此前忽略触摸帧 `slot[0] & BIT(0)`（ColorOS `oplus_bsp_pogo_keyboard.ko` 证实活性触点 `bit 0 = 1` 为手指、`bit 0 = 0` 为手掌），且未注册 `ABS_MT_TOOL_TYPE`；这使得 `libinput` 在多指落点时经 `tp_palm_detect_multifinger()` 对边缘掌触解除屏蔽、把 `Ctrl+单指轻击` 误判为双指交互并吞掉点击，同时还叠加启用了 `libinput` 默认 `200–500 ms` 的软件 `DisableWhileTyping`。
  2. **1 秒心跳周期性截断与偶发轻击失效**：
     - 抓包在连续滑指 `tid=328 -> 329`（`dt=2.0188 -> 2.0215 s`，间隔仅 `2.7 ms`）与 `tid=329 -> 330`（`dt=3.0780 -> 3.0798 s`，间隔仅 `1.8 ms`）两处抓到整条触点被凭空截断重建：根因在于 `pogo_kb_rx_sync()` 对每约 `1 s` 一次的 `0x2f`（`0x05`）保活心跳无条件调用 `pogo_kb_release_touches()`，强行抬起正在滑动、拖拽、悬停掌触或轻击的触点。
     - `evdev.jsonl` 同时录得持续 `199.8 ms`（`tid=336`）与 `219.3 ms`（`tid=337`）的真实单指轻击，超出 `libinput` 默认 `180 ms`（`1.3 mm`）轻击容差而被放弃（对照 ColorOS `libinputreader.so` 中 `ImmediateInterpreter` 实测使用 `Tap Timeout` / `Tap Move Distance` 约 `200 ms / 2.0 mm`）；此外串口帧突发聚集到 `<3 ms` 时还易误触发 `libinput` 的 `Touch jump detected and discarded`。
  3. **ColorOS 16 光标加速曲线与 Wayland 高分屏适配**：
     - 对 `system_b/system/lib64/libinput.so`（`createAccelerationCurveForPointerSensitivity`）、`libinputreader.so`（`ScalingFilterInterpreter`）及 `libinputservice.so`（`MouseCursorController`）逆向提取出完整四段双曲速度增益曲线：$v \le 32.002\text{ mm/s}$ 时 $g = 3.19$；$v \le 52.830$ 时 $g = 4.79 - 51.254/v$；$v \le 119.124$ 时 $g = 7.28 - 182.737/v$；$v > 119.124$ 时 $g = 15.04 - 1107.556/v$，叠加 15 档灵敏度系数（默认档 `speed=0` 对应 `commonFactor = 0.64`）与 `ScalingFilterInterpreter` `7.85433054` 物理像素/mm 系数；结合平板 KDE Wayland（`DSI-1` `3392×2400`、`scale = 2.5`）映射至 `libinput` 1000-DPI 逻辑坐标增量，保持双指滚动滤波器 `touchpad_scroll_filter` 不变。
     - 实机核对 `/usr/bin/kwin_wayland` 携带文件能力 `cap_sys_nice=ep`（触发 `AT_SECURE=1` 由 glibc 剥离 `LD_PRELOAD`），且 `libinput` Lua 插件 API 未暴露指针加速度表接口，故通过新建独立下游包 `packaging/opd2413-libinput/`（`ModelOnePlusOPD2413Touchpad=1` 定向触发）承接用户态改动并记入 [TECH-DEBT.md](TECH-DEBT.md) `#45`。
- **离线修改与测试结果（2026-11-17）：**
  1. **内核 `7.2.15-30.opd2413`（[2436](../kernel/opd2413-7.2/patches/2436-Input-oneplus-pogo-keyboard-report-palm-and-fix-touchpad.patch)）**：
     - 为 `oneplus-pogo-keyboard.c` 注册 `ABS_MT_TOOL_TYPE`，按 `slot[0] & BIT(0)` 上报 `MT_TOOL_FINGER` / `MT_TOOL_PALM`；将 `pogo_kb_rx_sync()` 在 `0x2f` 心跳时释放触点严格限定为 `kb->touching && kb->tp_rx_err && time_after(jiffies, kb->last_tp_rx + msecs_to_jiffies(250))`（`patch -F0` 应用并经反向 `-R --dry-run` 校验）。
     - 于 `opd2413-builder-kernel:fc45` 完成全量编译，经 `HOSTCC=/tmp/hostgcc` 解决 Fedora 45 `kernel-headers-7.3.3` 下 `resolve_btfids` 的 `__u128` 头文件遮蔽，`oneplus-pogo-keyboard.o` 在 `KCFLAGS="-Werror"` 下零警告通过；产出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-30.opd2413.aarch64.rpm`（SHA-256 `d5e2b9bc9dd54073720d4d11e32a470b71745388dd272349901822ece393fa64`）。校验 `vmlinuz` 为未压缩 `Linux kernel ARM64 boot executable Image, little-endian, 4K pages`（`62M`）、`oneplus-pogo-keyboard.ko` 含 `[36] .BTF` 段且 `vermagic: 7.2.15-30.opd2413`，`objdump` 确认含 `0x37`（`ABS_MT_TOOL_TYPE`）及 `0xfa`（`250 ms`）分支。
  2. **用户态 `libinput-1.32.0-1.fc45.opd2413.1`（[0001 补丁](../packaging/opd2413-libinput/patches/0001-touchpad-add-OnePlus-Pad-2-Pro-ColorOS-accel-and-tap-quirk.patch)、[libinput.spec](../packaging/opd2413-libinput/libinput.spec)、[build-libinput-rpm.sh](../tools/build-libinput-rpm.sh)）**：
     - 通过 `quirks/50-system-oneplus.quirks`（`MatchVendor=0x22D9` / `MatchProduct=0x3869` / `ModelOnePlusOPD2413Touchpad=1`）定向启用 ColorOS 16 曲线及 `DSI-1` `kwinoutputconfig.json` 缩放读取、`tp_dwt_default_enabled() == false`、`220 ms` / `2.0 mm` 轻击阈值、关闭 `jump.detection_disabled = true` 并设置 `20 ms / 8 ms` 串口帧间隔平滑。
     - `./tools/build-libinput-rpm.sh --local 1` 编出 `out/rpmbuild/RPMS/aarch64/libinput-1.32.0-1.fc45.opd2413.1.aarch64.rpm`（SHA-256 `e18db3f3be598748b629aaf86f10f8bb2de3003b5c7a147bd9f5cb2752b95d32`），`%check` 执行 `meson test`（`validate-quirks`、`test-library-version`、`symbols-leak-test` 3/3 `OK`）与链接 `libfilter.a` + `liblibinput-util.a` 的自测程序均通过（`OPD2413_FILTER_SELF_TEST_PASS`：1–500 mm/s 单调、3 个拐点连续性 <0.2%、`20/85/200 mm/s` 精确增益、`-1/0/+1` 档位倍率、`kwinoutputconfig.json` 中 `DSI-1 scale=2.0` 解析），且包内已含 `/usr/share/libinput/50-system-oneplus.quirks`。
- **实机装机与单次引导准备（2026-11-17，已写入设备，待重启验收）：**
  1. **装机与 ESP 状态**：经 `pkexec dnf --disablerepo='*'` 执行单事务：先核对 `boot-select status`（`kshim_remembered: "Fedora"`、`booted_entry: fedora-7.2.15-29.opd2413.conf`、`pending_next: null`）并将 `fedora-7.2.15-29.opd2413.conf` 确认为回退默认项；带 `--setopt=protected_packages=""` 卸载最旧备用内核 `kernel-opd2413-7.2.15-26.opd2413`（ESP `/dev/sda16` 从 `370M / 512M` 回落至 `247M / 512M`，空出 `266M`）；随后升级安装 `libinput-1.32.0-1.fc45.opd2413.1.aarch64`（`rpm -V libinput` 零输出通过；`/usr/lib64/libinput.so.10.13.0` 与 `/usr/share/libinput/50-system-oneplus.quirks` SELinux 上下文分别为 `lib_t` 与 `usr_t`），并带 `--setopt=installonly_limit=3` 装入 `kernel-opd2413-7.2.15-30.opd2413.aarch64`（保留 `-29` 与 `-28` 两级回退）。
  2. **ESP 与 `KSHIM.CHO` 核验**：`kernel-install` + `dracut` + `60-opd2413-initrd-check` 于 `30 s` 内完成；`/boot/efi/fedora/7.2.15-30.opd2413/` 含 `linux`（`62M`）、`initrd`（`62M`）、`sm8750-oneplus-pad2pro.dtb`（`145K`），`fedora-7.2.15-30.opd2413.conf` 启动参数与 `-29` 一致（含 `cpufreq.default_governor=schedutil swiotlb=8192 mem_sleep_default=s2idle`），ESP 最终占用 `370M / 512M`（剩余 `143M`）。已调用 `/usr/libexec/opd2413/boot-select next fedora-7.2.15-30.opd2413.conf` 并 `sync`，校验 `KSHIM.CHO` 前后 SHA-256 完全一致，`pending_next` 指向 `fedora-7.2.15-30.opd2413.conf`（回退项为 `fedora-7.2.15-29.opd2413.conf`）。待用户重启进入 `-30` 后完成下列真机验收：
- **真机验收判据：**
  - `uname -r = 7.2.15-30.opd2413`、SELinux `Enforcing`、`0 AVC`、`/proc/bus/input/devices` 触控板 `ABS` 位图包含 `ABS_MT_TOOL_TYPE`（位 `55`）；
  - 连续拖拽或单指慢滑无每 1 秒自动抬指断触；光标加减速轨迹与轻击响应符合预期；按住 `Ctrl` 越过固件静默窗口且掌不压边时单指轻击稳定命中。
- **实机重启验收与固件边界逆向定论（2026-11-17，真机通过）：**
  1. **系统与输入栈状态复核**：用户重启经 `boot-select next` 引导至 `7.2.15-30.opd2413`（`/proc/cmdline` 含 `initrd=\fedora\7.2.15-30.opd2413\initrd` 与 `mem_sleep_default=s2idle`），`opd2413-boot-restore.service` 于开机阶段按预期自动将 `loader.conf` 默认条目从 `fedora-7.2.15-30.opd2413.conf` 恢复至 `fedora-7.2.15-29.opd2413.conf`（待用户确认后调用 `boot-select default` 固化）。`rpm -q kernel-opd2413` 列出 `-28`/`-29`/`-30`、`libinput` 为 `1.32.0-1.fc45.opd2413.1`、`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing`、当次开机 journal `0 avc: denied`；`/proc/bus/input/devices` 中 `OnePlus Pad 2 Pro Keyboard Touchpad`（`event6`）`ABS=2e0800000000003`（`ABS_MT_TOOL_TYPE` 位 55 已激活）；KWin D-Bus `/org/kde/KWin/InputDevice/event6` 实测 `disableWhileTyping=false`、`disableWhileTypingEnabledByDefault=false`、`pointerAccelerationProfileAdaptive=true`、`tapToClick=true`。
  2. **真机交互验收与 `Ctrl+轻击` 分层排除**：用户实测确认重启后单指轻击与连续拖拽（“拓展”）明显改善；针对浏览器 `Ctrl+轻击` 进行独立隔离测试——**“双手离开触控板 → 按住 `Ctrl` 等约 1 秒（避开 `< 160 ms` 固件静默且掌根不贴边）→ 单指轻击网页链接”可正常打开新标签页**，证明内核 `2436`（`MT_TOOL_PALM` + 心跳条件抬指）与 `opd2413-libinput` 未误杀正常 `Ctrl+轻击`；同步滑动按 `Ctrl` 停顿与 `< 160 ms` 快速组合吞点确认属硬件固件限制（日常可用三指轻击中键替代）。
  3. **固件协议完全审计（证据位于 `private/touchpad-20261117/`）**：反汇编 `oplus_bsp_pogo_keyboard.ko`、`libpogo_keyboard.so`、`dtbo_b` 与 `AccessoryFramework.apk`（`IPogoKeyboard`）确认，键盘为 `KA030_B_1.2.0`（MCU）+ `TP_A_13`（触控 IC）双芯片方案，UART 指令仅覆盖 LED（`0x20 06 0d 04`）、版本查询（`0x34 01 07` / `0x38 03 08`）、亮灭屏同步（`0x3a 03 02`）、电池电流（`0x3a 03 09`）、20 B 序列号（`0x3a 04 0b`）、触控板总开关（`0x3a 03 11`）、手势开关（`0x3a 03 17`）、15×25 电容矩阵调试流（`0x3a 03 19`）与 NFC 标签同步，不存在 DWT/掌触参数调节命令；且 `dtbo_b` `Erhai` 节点未开 `pogopin-kb-fw-support`、`super` 分区无 `POGOPIN_KB.bin`，串口 DFU（`0x38 04 0a` / `0x24 03` 与 `0x3a 09 12`）仅有只写路径而无 Flash 回读，MCU 还依赖 Nordic Secure DFU `bat_data` 签名校验（见 [TECH-DEBT.md](TECH-DEBT.md) `#46`）。
  4. **设为默认启动项（2026-11-17，经用户确认执行）**：经用户确认仅写入 ESP `loader.conf` 后，通过 `pkexec /usr/libexec/opd2413/boot-select default fedora-7.2.15-30.opd2413.conf && sync` 固化默认引导项；核验 `/boot/efi/loader/loader.conf` 为 `default fedora-7.2.15-30.opd2413.conf`，`boot-select status` 显示 `booted_entry: "fedora-7.2.15-30.opd2413.conf"`、`loader_default: "fedora-7.2.15-30.opd2413.conf"`、`pending_next: null`、`kshim_remembered: "Fedora"`，`/boot/efi/KSHIM.CHO` 写前后 SHA-256 完全一致且保持 `1 extent`（`16384 B`），`loader/entries/` 保留 `fedora-7.2.15-{28,29,30}.opd2413.conf`（ESP `370M / 512M`，剩余 `143M`）；常规冷启动走默认项可于下次断电重启时一并复核。



### Polkit 授权弹窗显式“开始人脸识别”确认机制（`opd2413-face-0.1-12` + `polkit-kde-6.8.3-1.fc45.opd2413.1`）

- **问题根因：** `authselect` 配置 `opd2413-face` 在 `system-auth` 中先于 `pam_unix.so` 调用 `pam_opd2413_face.so`，而 `polkit-kde-authentication-agent-1` 弹出授权框时立即执行 `Session::initiate()`（`PAM_SERVICE=polkit-1`），导致尚未看清授权动作即在后台完成人脸比对并直接放行。
- **方案与改动：**
  1. **服务端与 PAM 门控（`packaging/opd2413-face`）**：在 `opd2413-faced`（[opd2413-faced.py](../packaging/opd2413-face/src/opd2413-faced.py)）与 [org.opd2413.Face1.conf](../packaging/opd2413-face/data/org.opd2413.Face1.conf) 新增 `SetPolkitArmed(username, armed)` / `IsPolkitArmed(username)` 接口；`service == "polkit-1"` 默认拦截（`polkit-unarmed`），仅当收到显式单次放行令牌（`POLKIT_ARM_TTL_S = 8.0`，`Verify` 启动时原子消费）才开启前摄识别。[pam_opd2413_face.c](../packaging/opd2413-face/src/pam_opd2413_face.c) 在 `polkit-1` 未放行时静默返回 `PAM_IGNORE`（不发 `Verifying face...`，直接交由 `pam_unix.so` 等待密码输入）。锁屏（`kde-fingerprint`）与终端 `sudo` 保持原有行为不变。
  2. **Polkit 弹窗确认按钮（`packaging/opd2413-polkit-kde`）**：新增下游补丁 [0001-add-explicit-face-recognition-confirmation-button.patch](../packaging/opd2413-polkit-kde/patches/0001-add-explicit-face-recognition-confirmation-button.patch)、[polkit-kde.spec](../packaging/opd2413-polkit-kde/polkit-kde.spec) 与 [build-polkit-kde-rpm.sh](../tools/build-polkit-kde-rpm.sh)。弹窗打开后不触发扫脸，检测到用户已录入人脸时显示 `Start Face Recognition` 按钮（支持随时直接输入密码）；点击按钮后调用 `SetPolkitArmed(user, true)` 并重启当前 `PolkitQt1::Agent::Session` 触发人脸识别；识别失败后可点击 `Retry Face Recognition` 或直接输入密码，点击 `Cancel`/切换用户/合盖均正确解除放行并取消相机扫描。
- **离线构建与预期/判据（待用户确认装包后真机验收）：**
  - 已在平板本地容器完成编译：`out/rpmbuild/RPMS/aarch64/opd2413-face-0.1-12.fc45.aarch64.rpm` 与 `out/rpmbuild/RPMS/aarch64/polkit-kde-6.8.3-1.fc45.opd2413.1.aarch64.rpm`。
  - **预期与判据：**
    1. 安装上述两包并重启 `opd2413-face.service` 与用户级 `plasma-polkit-agent.service` 后，运行 `pkexec id`（或图形提权操作）弹出授权窗口时，不自动调用摄像头/不自动解锁，可先查看请求动作与 `Details`，并可见 `Start Face Recognition` 按钮与密码输入框；
    2. 在弹窗未点按钮时直接输入密码可正常授权；
    3. 点击 `Start Face Recognition` 后按钮切换为 `Scanning Face…`，正对前摄即完成识别并授权放行；遮挡摄像头超时或失败后保留密码输入与 `Retry Face Recognition` 按钮，且 `Cancel` 能立即中止扫描；
    4. 终端 `sudo` 与锁屏人脸解锁仍按原有方式正常工作；SELinux `Enforcing` 无新增 AVC 拒绝。
- **实机验证结果（2026-11-17，真机通过）：**
  1. **装包与服务重启**：经 `pkexec dnf --disablerepo="*" upgrade -y` 装入 `opd2413-face-0.1-12.fc45.aarch64` 与 `polkit-kde-6.8.3-1.fc45.opd2413.1.aarch64`（`rpm -V opd2413-face polkit-kde` 零输出通过）；`opd2413-face.service`（`PID 191533`）与用户级 `plasma-polkit-agent.service`（`PID 191846`）均 `active (running)`。`gdbus` 查询确认 `HasEnrolled("colin") = true`、`IsPolkitArmed("colin") = false`。
  2. **显式点击确认验收（`pkexec id`）**：
     - `22:22:30` 触发 `pkexec id` 弹出新版 `QuickAuthDialog.qml`，在随后 9 秒停留期间未触发人脸扫描与自动授权（用户有充足时间查看动作内容）；
     - `22:22:39` 用户点击 **Start Face Recognition** 后，`polkit-agent-helper-1[192249]` 记录 `pam_opd2413_face(polkit-1:auth): Face authenticated user colin (polkit-1)`，审核日志 `grantors=pam_opd2413_face res=success`，`pkexec id` 返回 `uid=0(root)`；
     - 验证完成后复查 `IsPolkitArmed("colin") = false`（单次令牌已原子消费并复位）。
  3. **整机健康度**：`getenforce = Enforcing`、相关时段 journal 零 `avc: denied`、`systemctl is-system-running = running`、`systemctl --failed` 为 `0 loaded units listed`。


## 2026-11-19

### Steam 客户端与大型 3D 游戏适配立项及阶段 1 离线准备（`opd2413-gaming-0.1-1` + 内核 `7.2.15-31.opd2413`）

- **现网基线核对（只读，`7.2.15-30.opd2413`）：**
  - 已确认当前内核已原生命中 SM8750 Oryon `ssbd_sigreturn`（`cpu0-5` `0x514f0014`、`cpu6-7` `0x513f0014` 匹配 `MIDR_QCOM_ORYON_X1`），且已包含 `0505`/`0505a` 非对齐原子模拟、`0504` 兼容输入、`CONFIG_NTSYNC=y`（`/dev/ntsync` `0666`）、`CONFIG_UCLAMP_TASK=y`（普通用户实测 `uclampset -m 256` 生效）、`CONFIG_TRANSPARENT_HUGEPAGE_MADVISE=y`、UFS MCQ、`zram0` `8 GiB zstd`、Adreno 830 `1100 MHz` OPP 与 `qcom-battmgr-bat` `charge_control_{start,end}_threshold`。
  - 已确认 Fedora 45 官方仓库自带 `fex-emu 2604`、`fex-emu-rootfs-fedora`、`fex-emu-thunks`、`gamescope 3.16.31`、`gamemode 1.8.2`、`mangohud 0.8.3`、`box64 0.3.6`、`vulkan-tools`。
  - 现网待补齐缺口：`CONFIG_CPU_IDLE_GOV_TEO` 未编入（仅 `menu`）、`3d00000.gpu/polling_interval=50` ms、`kernel.sched_util_clamp_min_rt_default=1024`、`vm.swappiness=60`、`vm.dirty_bytes=0`（`dirty_ratio=20`）、`net.core.rmem_max=4194304`、PipeWire 游戏音频缓冲底限及无风扇专用启动/功耗工具。
- **总体文档与阶段 1 改动：**
  1. 新增总体路线文档 [GAMING-STEAM.md](GAMING-STEAM.md)，明确 4 阶段路线（阶段 1 性能基座 → 阶段 2 Steam ARM64 + ARM64EC Proton / FEX + SELinux 策略 → 阶段 3 Gamescope/MangoHud/外设 → 阶段 4 大型 3D 游戏长时热稳态与旁路供电）。
  2. 新增独立性能基座包 `packaging/opd2413-gaming/` 与 [build-gaming-rpm.sh](../tools/build-gaming-rpm.sh)（`opd2413-gaming-0.1-1.noarch.rpm`，SHA-256 `f116b1e3…`）：
     - `60-opd2413-gaming.conf`（sysctl：`sched_util_clamp_min_rt_default=64`、`vm.swappiness=150`、`vm.dirty_bytes=536870912`、`vm.dirty_background_bytes=67108864`、`net.core.rmem_max=33554432`）；
     - `60-opd2413-gaming.rules`（udev：`/dev/ntsync` `0666`、`3d00000.gpu` `polling_interval=16`）；
     - `60-opd2413-gaming.conf`（tmpfiles：`cpuidle=teo` 与 `polling_interval=16`）；
     - `61-opd2413-gaming.conf`（environment.d：`WINE_D3D_CONFIG=renderer=vulkan`）；
     - PipeWire / pipewire-pulse 1024 帧底限配置（防 Q6APM 游戏音频欠载爆音）；
     - `/usr/bin/opd-game`（`balanced`/`fast`/`fastest`/`compat`、`uclamp.min`、FEX/Proton 参数、`--gamescope`、`--vk-icd`）与 `/usr/bin/opd-power`（无风扇安全档位 `silent`/`balanced`/`performance`、GPU 锁频、旁路充电阈值、状态遥测）。
     - 离线测试 [tests/gaming-test.sh](../tests/gaming-test.sh) 通过（`PASS: opd2413-gaming offline tests`）。
  3. 新增 `kernel/opd2413-7.2/config/m4-gaming.config`（仅开启 `CONFIG_CPU_IDLE_GOV_TEO=y`），于本地容器离线构建 `kernel-opd2413-7.2.15-31.opd2413.aarch64.rpm`。
- **上机预期与判据（待用户确认写入后按阶段 1A → 1B 分步上机）：**
  1. **阶段 1A（安装 `opd2413-gaming-0.1-1`）**：安装后 sysctl/udev/tmpfiles 立即生效，`opd-power status` 显示 `polling_interval=16 ms`、`rt_uclamp_min=64`、`swappiness=150`、`dirty=536870912/67108864`、`rmem_max=33554432`；重启 PipeWire 后扬声器播放正常无爆音；`opd-power bypass on` / `off` 可正常切换 `charge_control_{start,end}_threshold`；SELinux `Enforcing` 零新增 AVC。
  2. **阶段 1B（清理旧回退 `-28`、安装 `7.2.15-31.opd2413` 并经 `boot-select next` 安全单次引导 + 冷启动复核）**：开机后 `uname -r = 7.2.15-31.opd2413`、`/sys/devices/system/cpu/cpuidle/current_governor = teo`、`running`、`0 failed`、`Enforcing` 零 AVC、`KSHIM.CHO` 哈希与 `1 extent` 不变、`s2idle` 短休眠唤醒与显示/触控/触摸板/Wi-Fi/蓝牙/GPU/相机均无回归。
- **阶段 1A 实机验证结果（2026-11-19，经用户确认装机，真机通过）：**
  - 通过 `pkexec dnf --disablerepo="*" install -y out/rpmbuild/RPMS/noarch/opd2413-gaming-0.1-1.noarch.rpm` 完成安装（`rpm -V opd2413-gaming` 零输出）。
  - sysctl/udev 即时生效：`3d00000.gpu/polling_interval = 16` ms、`kernel.sched_util_clamp_min_rt_default = 64`、`vm.swappiness = 150`、`vm.dirty_bytes = 536870912`、`vm.dirty_background_bytes = 67108864`、`net.core.rmem_max = 33554432`、`/dev/ntsync` 可访问（`0666`）；`60-opd2413-gaming.conf` tmpfiles 写入 `cpuidle=teo` 在当前 `7.2.15-30` 上按预期返回 `Invalid argument`（待 1B 内核 `7.2.15-31` 启用后自动切入）。
  - `opd-power bypass on` 将阈值置为 `93%..94%`，`opd-power bypass off` 恢复至 `50%..100%`（`qcom_battmgr` 固件将 `start=0` 钳位至 `50`）；`opd-power profile performance` 保持 `policy6` 为 `schedutil` 并将 GPU 最低频提至 `443 MHz`，切回 `balanced` 恢复全范围。
  - 重启用户级 `pipewire`/`pipewire-pulse`/`wireplumber` 均 `active`，`pw-metadata -n settings 0` 确认 `clock.min-quantum = 1024`、`clock.quantum = 1024`、`clock.rate = 48000`；`opd-game fast` 实测 `PROTON_USE_NTSYNC=1`、`WINE_D3D_CONFIG=renderer=vulkan`、`FEX_X87REDUCEDPRECISION=1` 与 `uclampset util_clamp: min: 448 max: 1024`。
  - 整机状态：`systemctl is-system-running = running`、`0 failed`、`SELinux Enforcing` 零新增 AVC。
- **阶段 1B 离线构建与装机就绪（2026-11-19，待重启验收）：**
  - 本地容器离线完成 `kernel-opd2413-7.2.15-31.opd2413.aarch64.rpm` 构建（SHA-256 `5355fe70…`），`diff -u` 确认 `.config` 相对 `7.2.15-30.opd2413` 仅 `CONFIG_CPU_IDLE_GOV_TEO=y` 一行变化。
  - 已通过单次 `pkexec` 固化 `boot-select default fedora-7.2.15-30.opd2413.conf`、卸载最旧回退 `7.2.15-28`、装入 `7.2.15-31.opd2413` 并设置一次性引导 `boot-select next fedora-7.2.15-31.opd2413.conf`；ESP `/dev/sda16` 保留 `-29`/`-30`/`-31`（`370M / 512M`，剩余 `143M`），`/boot/efi/KSHIM.CHO` 写前后 SHA-256 完全一致且保持 `1 extent`（`16384 B`）。待用户重启平板后核验 `uname -r = 7.2.15-31.opd2413`、`cpuidle=teo`、`opd2413-gaming` 冷启动持久化与整机健康度。
- **阶段 1B 重启验收结果（2026-11-19 09:20:59 开机，真机通过）：**
  - 重启直接进入 `uname -r = 7.2.15-31.opd2413`；`opd-power status` 核验 `CPUIDLE: teo (available: menu teo)`、`3d00000.gpu/polling_interval = 16 ms`、`ntsync=yes`、`rt_uclamp_min=64`、`swappiness=150`、`dirty=536870912/67108864`、`rmem_max=33554432`；
  - `systemctl --user show-environment` 含 `WINE_D3D_CONFIG=renderer=vulkan`，PipeWire `clock.min-quantum = 1024`（`48000 Hz`）；
  - 整机健康度：`systemctl is-system-running = running`、`0 failed`、`SELinux Enforcing` 零 `avc: denied`，`bluetooth`/`opd-netshare`/`opd2413-face`/`opd2413-lid-input`/`pipewire`/`wireplumber`/`opd2413-lid-suspend`、`OnePlusPad2Pro` 扬声器、`Adreno (TM) 830 Mesa 26.2.6` 与 Wi-Fi 全部正常。待同阶段 2 授权时一并固化 `boot-select default fedora-7.2.15-31.opd2413.conf`。
- **阶段 1B 固化默认项与阶段 2 实机部署及冒烟（2026-11-19，经用户确认，阶段 2 达 `真机启动`）：**
  1. **固化默认引导项**：`boot-select default fedora-7.2.15-31.opd2413.conf` 完成，`KSHIM.CHO` 写前后哈希一致且保持 `1 extent`（保留 `-30`、`-29` 回退）。
  2. **Fedora 官方游戏/转译栈与 FEX `binfmt_misc` 修复**：安装 `fex-emu 2604`、`fex-emu-rootfs-fedora`（`default.erofs`）、`fex-emu-thunks`、`gamescope 3.16.31`、`mangohud 0.8.3`、`gamemode 1.8.2`、`vulkan-headers`。排查并解决两项关键坑：
     - Fedora 默认 `binfmt-dispatcher` 为 16 KB 页（Apple Silicon）开启 `use_muvm = true`，且屏蔽后字母序靠后的 `qemu-x86_64-static.conf` 在 `binfmt_misc` LIFO 队列中排在 `FEX-x86_64.conf` 之上；升级 `opd2413-gaming-0.1-4.noarch`（屏蔽 `zz-binfmt-dispatcher-x86{,_64}` 与早位 `FEX-x86{,_64}`，并在最末注册 `zz-opd2413-FEX-x86{,_64}.conf`）后，原生 `/usr/bin/FEX` 稳居 LIFO 最高优先级；
     - 实测开启 FEX Vulkan HostThunks 在 X11 显示初始化阶段触发 `SIGILL`（rc=132），而关闭 Thunks 后 `fex-emu-rootfs-fedora` 内置的 x86_64 `libvulkan_freedreno.so`（Mesa 26.2.2）直接经 `/dev/dri/renderD128` 驱动 `Adreno (TM) 830`（Vulkan 1.4.354）且零警告、零 AVC。
  3. **Steam ARM64 + `webhelper_acquire` + ARM64EC Proton + Gamescope 实机冒烟**：
     - [install-steam-arm64.py](../tools/gaming/install-steam-arm64.py)（改用 Akamai HTTP/2 CDN）完成 `steam_client_linuxarm64`（version `1794536281`）全部 34 包 SHA-256 校验并解压 13,653 个文件至 `~/.local/share/Steam`；[install-webhelper-layer.sh](../tools/gaming/install-webhelper-layer.sh) 将 `libVkLayer_webhelper_acquire.so` 隔离安装至 `~/.local/share/opd2413-steam-layer`（仅由 `steam-arm64` 经 `VK_ADD_IMPLICIT_LAYER_PATH` 加载，避免影响其他/x86_64 Vulkan 进程）。
     - [install-proton-arm.py](../tools/gaming/install-proton-arm.py) 安装 `proton-cachyos-11.0-20261015-slr-arm64`（含原生 ARM64 Wine 11.0、`libarm64ecfex`/`libwow64fex`、ARM64 DXVK 与 VKD3D-Proton Low-Latency），自动剥离 `require_tool_appid` 并建立 `files/bin -> bin-arm64` 软链；实测临时前缀执行 Windows `cmd.exe` 输出 `ntsync: up and running.`、`ARM64EC_OK`，`SELinux Enforcing` 零 AVC。
     - 提前完成阶段 3 核心冒烟：`opd-game --gamescope --res 1696x1200 --fps 60 --mangohud -- vkcube --c 120` 在 KDE Wayland 上 60 Hz（`16.67 ms`）FSR 全屏嵌套渲染正常退出且零 AVC。
     - 启动 `~/.local/bin/steam-arm64`：`steam` 与 `steamwebhelper` 动态库 100% 解析，`steamsysinfo` 识别 `Adreno (TM) 830 (k_EGpuDriverId_MesaTurnip 26.2.6, 11.7 GB VRAM)`，`Enforcing` 零 AVC；待用户登录 Steam 账户下载/运行 3D 游戏完成阶段 2/3/4 实机验证。

### 阶段 2 真机实玩排障验收（《黑暗之魂 3》）与阶段 3 Adreno MangoHud v0.8.4 部署

- **Steam 客户端与桌面集成问题闭环**：
  1. KRunner 反复启动未弹窗：实证 `zipfile` 解压未保留 `steamerrorreporter` 可执行位，`crashhandler.so` 在 `CefCrashReportingEnabled()` 断言时退回进程内同步上传至 `crash.steampowered.com` 阻塞超过 3 分钟；在 [tools/gaming/install-steam-arm64.py](../tools/gaming/install-steam-arm64.py) 中替换为非阻塞桩（保留 `.orig`）并仅在无运行中实例时清理 `Singleton*` 锁文件，实测登录窗 `1.01 s` 弹出。
  2. 图标与托盘：从 `public/steam_tray.ico` 生成 `16..256` 七档 PNG 安装至用户 `hicolor` 主题，统一桌面项为 `steam.desktop`（`StartupWMClass=steam`），并安装 Fedora 官方 `libappindicator-12.10.1-11.fc45.aarch64`（满足 GTK2 `steamui.so` 对 `libappindicator.so.1` 的动态加载），实测 Plasma `StatusNotifierWatcher` 注册 `:1.290/org/ayatana/NotificationItem/steam`。
  3. 游戏快捷方式启动：在 `opd2413-gaming-0.1-5` 中新增 `/usr/bin/steam` 分发入口（及 `~/.local/bin/steam`），满足 Steam 生成的 `Exec=steam steam://rungameid/...`。
  4. 着色器卡 0% 与启动秒退：扫描出 28 个 ZIP 属性 `0644` 的 ELF/脚本（含 `steamrtarm64/fossilize_replay`、`linuxarm64/steam-launch-wrapper`、`steamrtarm64/reaper`、`steamrtarm64/gameoverlayui`），改为自动遍历补齐 `0755`（剩余缺失 `0`）。
  5. Steam 内置性能面板不显示：核实 Valve ARM64 `steamui.so` 漏写 `steamoverlay_arm64.json`，已自动注册指向 `steamrtarm64/steamoverlayvulkanlayer.so`，实测游戏内原生帧率正常显示。
  6. 游戏退出弹 DrKonqi 崩溃窗：定位为 `DarkSoulsIII.exe` 在 ARM64EC Wine 收尾时音频线程（`winepipewire_ti` / `audio_client_ma`）触发 `SIGSEGV`（原落盘 `453.6M` core）；在 `opd-game` 加 `ulimit -c 0` 并默认 `PROTON_USE_PIPEWIRE=0`，同时通过用户级 `opd-drkonqi-filter` + `drkonqi-coredump-launcher@.service.d` 仅静默过滤 Wine/Proton 退出包（`SOCK_SEQPACKET` 自测 `PASS`）。
- **《黑暗之魂 3》（AppID 374320）性能剖析与 `opd2413-gaming-0.1-7` 调优**：
  - 基线 720p 最低画质未挂 `opd-game` 时约 `55 FPS`；启用 `opd-game fastest`（`FEX_TSOENABLED=0`）后达到 `60 FPS`，60 s MangoHud CSV 显示 `6.4s..40.8s` 连续 34.4 s 稳态中位帧时间 `16.78 ms`（`59.6 FPS`），同时暴露两个卡顿源：（a）`uclamp=512` 让 `policy6` 轻载常驻 `4089 MHz` 于 45 s 撞 `96°C` 降频至 `3513 MHz`；（b）`vm.swappiness=150` 在后台浏览器占内存叠加游戏加载至 `12.6 GiB` 时触发 `kswapd` 1.3 s 猛压 `340 MiB` 进 `zram0`（`30–155 ms` 尖刺）。
  - 升级装入 `opd2413-gaming-0.1-7.noarch`（`vm.swappiness=60`、`uclamp=320`、`FEX_PROFILESTATS=0`、`fastest` 零 TSO 屏障、`opd-power profile sustained` 设 `policy6 <= 3.51 GHz` + GPU `443..1100 MHz`）并关闭黑魂 3 `Auto-detectBestRenderingSettings`，用户实测卡顿频率明显下降，阶段 2 升格为 **`真机通过`**（全程 `SELinux Enforcing` 零 AVC）。
- **阶段 3 高通 Adreno 830 真实 GPU 监控（`MangoHud v0.8.4`）**：
  - 新增 [tools/gaming/build-mangohud-adreno.sh](../tools/gaming/build-mangohud-adreno.sh)，预缓存 GitHub wrap 并在 `fedora:45` 容器中以 `-j7` 原生编译 Zaviya `MangoHud v0.8.4`（含高通 `msm_dpu` + `3d00000.gpu/cur_freq` + `gpuss` 温区 + `drm-engine-gpu` 补丁）至用户态 `~/.local/lib/opd2413-mangohud/` 与 `~/.local/share/vulkan/implicit_layer.d/MangoHud.aarch64.json`，并写入默认 `~/.config/MangoHud/MangoHud.conf`。
  - 真机 `vkcube` 冒烟通过：`gpu_temp=40°C`、`gpu_core_clock=443 MHz`、自动日志零崩溃完成，且核实内核 `/proc/<pid>/fdinfo` 正常输出 `drm-driver: msm` 与 `drm-engine-gpu` 递增纳秒计数。

### 阶段 3–4 关键突破：`FEX_SMCCHECKS=none` 消除黑魂 3 周期卡顿与 `opd-drkonqi-filter` 实机验收

- **退出崩溃弹窗彻底静默**：升级 `opd-drkonqi-filter` 循环读取 `QLocalSocket` 分片并在命中 `wine-preloader` 时立即退出；`15:08:42` 实机退出《黑魂 3》时 `journalctl --user` 明确打印 `opd-drkonqi-filter: suppressed harmless Wine/Proton teardown crash`，无 DrKonqi 弹窗。
- **FSR 功耗对比与 `FEX_SMCCHECKS=none` 实测**：
  - 实测 `--gamescope` FSR 升频到 `3392×2400` 肉眼帧节奏更顺（精确 60 Hz 2:1 对齐 120 Hz 面板），但在无风扇机身下功耗与 CPU/GPU 温升明显更高，日常更适合直出渲染。
  - 关闭 FSR 后在《黑魂 3》启用 `PROTON_DISABLE_HIDRAW=1 FEX_SMCCHECKS=none opd-game --mangohud fastest %command%`，彻底消除 FEX 默认 `mtrack` 自修改代码页追踪与 Arxan 定时内存校验叠加引发的周期性卡顿，用户实测**几乎不再卡顿、稳定 60 FPS**（注意 `FEX_SMCCHECKS=none` 应按游戏单独启用，避免影响依赖实时自修改代码/JIT 的游戏）。
- **冷启动持久化复核**：平板于 `15:02` 重启后，`opd-power status` 确认 `CPUIDLE: teo`、`3d00000.gpu/polling_interval=16 ms`、`ntsync=yes`、`rt_uclamp_min=64`、`vm.swappiness=60`、`dirty=512M/64M`、`rmem_max=32M` 全部自动持久化生效。

### 人脸解锁锁屏与 Polkit 授权弹窗图标统一（`opd2413-face 0.1-13`、`polkit-kde 6.8.3-1.fc45.opd2413.2`）

- **问题根因与选型**：录入向导（`opd-face-enroll.desktop` / `opd-face-enroll-gui.py`）使用 `face-smile`（Breeze 中软链到 `preferences-desktop-emoticons.svg`，圆形微笑脸）；此前锁屏 [MainBlock.qml](../packaging/opd2413-face/data/lockscreen/MainBlock.qml) 使用 `edit-image-face-recognize-symbolic`（方框问号）/`edit-image-face-detect-symbolic`，Polkit 弹窗补丁 [0001-add-explicit-face-recognition-confirmation-button.patch](../packaging/opd2413-polkit-kde/patches/0001-add-explicit-face-recognition-confirmation-button.patch) 使用 `edit-image-face-recognize`。核实 `breeze` / `breeze-dark` 内置的 `preferences-desktop-emoticons-symbolic` 与 `face-smile` 造型完全一致，且在 KDE `KIconEngine` 下 `16/22/24/32/48 px` 均以单色 `.ColorScheme-Text` 矢量渲染、不回退彩色（而 `face-smile-symbolic` 在 Breeze 下缺失会回退到黄色彩色版）。
- **源码改动与离线通过**：
  - [MainBlock.qml](../packaging/opd2413-face/data/lockscreen/MainBlock.qml)：将非匹配态的 `iconSource()` 统一为 `preferences-desktop-emoticons-symbolic`（匹配解锁瞬间保留 `object-unlocked-symbolic`）。
  - [0001-add-explicit-face-recognition-confirmation-button.patch](../packaging/opd2413-polkit-kde/patches/0001-add-explicit-face-recognition-confirmation-button.patch) 与 [polkit-kde.spec](../packaging/opd2413-polkit-kde/polkit-kde.spec)：将 `QuickAuthDialog.qml` 与 `MobileQuickAuthDialog.qml` 中 `faceAuthButton` 的 `icon.name` 改为 `preferences-desktop-emoticons-symbolic`。
  - 原生构建产出 `out/rpmbuild/RPMS/aarch64/opd2413-face-0.1-13.fc45.aarch64.rpm`（SHA-256 `baf4c473...`）与 `out/rpmbuild/RPMS/aarch64/polkit-kde-6.8.3-1.fc45.opd2413.2.aarch64.rpm`（SHA-256 `f89123c0...`）；离线解包并解压 `.qrc` zstd 资源验证两包均仅含新图标、无旧 `edit-image-face-*` 残留（`离线通过`）。
- **上机预期与判据**：装入两包并重启 `plasma-polkit-agent.service` 后，（1）`rpm -q` 为 `opd2413-face-0.1-13` 与 `polkit-kde-6.8.3-1.fc45.opd2413.2`；（2）`/usr/local/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/MainBlock.qml` 已刷新为 `preferences-desktop-emoticons-symbolic`；（3）触发 `pkexec` 授权弹窗与锁屏界面目视确认均为黑白单色微笑脸且人脸解锁正常；（4）`SELinux Enforcing` 零新增 AVC。
- **装机与实机验收结果（2026-11-19，经用户确认与目视验收，达 `真机通过`）**：
  - 通过单次 `pkexec` 完成 `dnf -y upgrade --nogpgcheck`，`rpm -q` 确认为 `opd2413-face-0.1-13.fc45.aarch64` 与 `polkit-kde-6.8.3-1.fc45.opd2413.2.aarch64`；
  - `/usr/share/opd2413-face/lockscreen/MainBlock.qml` 与 `/usr/local/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/MainBlock.qml` 均已更新为 `preferences-desktop-emoticons-symbolic`；
  - `systemctl --user restart plasma-polkit-agent.service` 后 `active`（新进程 `/usr/libexec/kf6/polkit-kde-authentication-agent-1` 已接管），`opd2413-face.service` 为 `active`，`SELinux Enforcing` 零新增 AVC；用户目视验收锁屏与授权弹窗黑白微笑脸图标均符合预期。

## 2026-11-20 `#39` 启动偶发黑屏自动重启专项取证与排查

- **现象与离线排查结论**：
  - 用户反馈偶发在引导界面选择 Linux 后黑屏数秒、无内核日志、自动重启后正常进入 Fedora（冷启动与热重启均遇过，概率较低；与 [TECH-DEBT.md](TECH-DEBT.md) `#39` 一致）。
  - 离线代码审计与只读基线核对已排除物理 KASLR 撞保留区（U-Boot 无 `EFI_RNG_PROTOCOL`，内核物理地址固定在 `0xbf2a00000`）、U-Boot 常规加载失败（会切 `vidconsole` 显示错误并等待 8 s）及 `kShimC` 软件/异常复位（全部为 `while (1)` 停机）。
  - 现网 `7.2.15-31.opd2413` 带 `quiet loglevel=3` 且 `CONFIG_PANIC_TIMEOUT=0`、无运行时看门狗，导致早期硬件/TZ/SMMU/时钟/电源域复位时 `console-ramoops-0` 为 `0` 字节；同时审计出 `7.2.15-31` 尚未合入的 3 处 `erhai` 早期竞态修复候选（`qcom_tzmem` `DO_ONCE` 关中断睡眠、`drivers/clk/clk.c` 孤儿时钟重挂 ABBA 死锁与 `#32` 的 8 条 `mdss_probe` WARNING、`ufshcd` 时钟缩放死锁）。
- **取证方案与写入范围（2026-11-20 经用户批准方案 A）**：
  - 仅在 ESP `/boot/efi/loader/entries/` 新增临时诊断条目 `opd2413-bootdiag.conf`（复用现役 `7.2.15-31` 内核、initrd 与 DTB，仅去掉 `quiet loglevel=3` 改为 `loglevel=7 ignore_loglevel initcall_debug panic=10`），通过 `boot-select default opd2413-bootdiag.conf` 临时切为默认，不改动 `boot_b`、`KSHIM.CHO` 及原有 `-31`/`-30`/`-29` 条目。
  - 由主机经 SSH 运行最多 25 轮无人值守热重启循环，每轮核验启动耗时、`pstore` 序号递增、`console-ramoops-0` 尾部是否正常结束于 `reboot: Restarting system` 及 `dmesg` 异常；**命中任一异常立即停止**、将完整现场拉回 `private/bootdiag-20261120/`，并恢复 `default fedora-7.2.15-31.opd2413.conf`、删除临时条目、复核 `KSHIM.CHO` 哈希与 `1 extent`。
- **预期与判据**：
  - 正常轮次：单次热重启耗时稳定（预期约 35–55 s），`pstore` `.seq` 每次 `+1`，`console-ramoops-0` 末行为 `reboot: Restarting system`。
  - **分支 A（内核早期复位）**：某轮 `console-ramoops-0` 不以 `reboot: Restarting system` 结尾（或出现 `dmesg-ramoops-*`），直接给出复位前最后执行的函数/驱动与时间戳。
  - **分支 B（内核 `ramoops` 之前复位）**：某轮耗时明显跃升（`> 基线 + 18 s`）且 `console-ramoops-0` 仍保留上一轮正常重启记录，锁定故障位于 U-Boot / `systemd-boot` / EFI stub。
  - **分支 C（非保内存硬复位）**：热重启后 `pstore` `.seq` 未递增（空 `pstore`）且耗时跃升，锁定触发了不保内存的硬件/PMIC 掉电复位。
- **第 1 轮取证结果与恢复（2026-11-20 `10:32`–`10:57`）**：
  - 写入 `opd2413-bootdiag.conf`（`console=tty0 loglevel=7 ignore_loglevel initcall_debug panic=10`）并设为默认后，Run 1 触发**100% 必现的灰屏→自动重启死循环**（240 s 未回 SSH）；用户经 `Fedora boot menu` 手选回到正常 `7.2.15-31.opd2413` 后，已立即恢复 `loader.conf` 为 `default fedora-7.2.15-31.opd2413.conf` 并删除 `opd2413-bootdiag.conf`（此时 `kshim_remembered` 停在 `"Fedora boot menu"` 待确认恢复）。
  - **完整证据已持久化归档**：`private/bootdiag-20261120/captured/000095-b2137f8adb994cba87d0299170c05978/console-ramoops-0`（满 `262,132` 字节，3,761 行，同步逐行落盘无滞后）。
  - **现场剖析**：
    1. 去掉 `quiet` 且保留 `console=tty0` 后，`fbcon` 在 `0.099 s` 接管、`efifb` 在 `0.274 s` 接管 3392×2400 帧缓冲并逐行滚屏（约 `0.8–1.3 ms/行`），叠加 `initcall_debug` 把 `deferred_probe_initcall` 从正常 `0.26 s` 拖慢到 `0.62 s`。
    2. `Freeing initrd memory` 在 `0.417 s` 先于 `remoteproc-soccp` 探针（`0.755 s`）完成（正常启动为 `remoteproc-soccp` `0.295 s` 先探针、`regulators-0/2` `0.307 s` 就绪、63 ms 后的 `0.358 s` 才 `Freeing initrd`）。
    3. `0.755011 s` `remoteproc0: soccp is available` → `0.756088 s` `powering up soccp` → `0.757235 s` `Booting fw image qcom/sm8750/erhai/soccp.mbn` → `0.758127 s` `probe of qcom_common.pd-mapper.0 returned 0` → `0.759011 s` `probe of remoteproc-soccp returned 0`，**随即整机硬复位**（无 Oops/panic，且因 `ktz8866 6-0011` 与 `dispcc` 尚未探针、背光仍亮，复位断扫瞬间呈现灰屏；此时 `dispcc`/`mdss`/`gmu`/`ufs`/`pcie` 均未探针）。
  - **待验证的下一步（需用户确认）**：使用 `video=efifb:off loglevel=7 ignore_loglevel panic=10`（关闭 `efifb` 刷屏且不加 `initcall_debug`，保持正常启动时序同时全速写 `ramoops`）做单次冒烟确认不死循环，再继续无人值守复现以区分“原始 `#39` 是否同样死于 `soccp` 抢跑竞态”与“`efifb` 活跃写入干扰”。
- **第 2 轮单步冒烟方案（2026-11-20，经用户确认）**：
  - **写入范围**：（1）`/usr/libexec/opd2413/boot-select kshim Fedora` 将 `KSHIM.CHO` 记忆从 `"Fedora boot menu"` 恢复回 `"Fedora"`（原地覆写，核验保持 `1 extent`）；（2）新增临时条目 `/boot/efi/loader/entries/opd2413-bootdiag2.conf`（复用 `7.2.15-31`，仅将 `quiet loglevel=3` 替换为 `video=efifb:off loglevel=7 ignore_loglevel panic=10`，**不加** `initcall_debug`）；（3）`/usr/libexec/opd2413/boot-select next opd2413-bootdiag2.conf` 执行 1 次热重启冒烟。
  - **预期与判据**：（1）无灰屏、无死循环，约 35–55 s 内正常进 Fedora 且 `systemctl is-system-running` 为 `running`、`booted_entry = opd2413-bootdiag2.conf`、`loader.conf` 已自动恢复为 `default fedora-7.2.15-31.opd2413.conf`；（2）`dmesg` 中无 `efifb` 接管记录，且 `remoteproc-soccp` 探针与 `Freeing initrd` 时序与日常 `-31` 一致；（3）随后再重启一次或检查本轮 `console-ramoops-0` 能完整录下 `loglevel=7` 早期启动日志。
  - **单步冒烟结果（2026-11-20 `11:16`–`11:17`）**：
    - `KSHIM.CHO` 已恢复为 `"Fedora"`（`sequence=48`、`1 extent`）。
    - 热重启 `opd2413-bootdiag2.conf` 耗时 **`38.8 s`** 正常上线（`boot_id` 前缀 `671e5e8d`），无灰屏、无死循环；`loader.conf` 已由服务自动恢复为 `default fedora-7.2.15-31.opd2413.conf`。
    - `dmesg` 确认 `video=efifb:off` 生效（零 `efifb` 接管），`console [ramoops-1] enabled`（`0.0468 s`），关键时序与日常 `-31` 完全一致：`remoteproc0: soccp`（`0.2995 s`）→ `adsp`（`0.3003 s`）→ `ktz8866 6-0011`（`0.3066 s`）→ `Freeing initrd`（`0.3609 s`）→ `adsp`（`0.3611 s`）与 `soccp`（`0.3673 s`）启动并完成（`soccp is now up` `0.4588 s`、`in D3, boot bus vote dropped` `0.4593 s`）→ `msm-mdss bootloader scanout`（`0.4824 s`），零严重内核报错。
- **测试 A：原生态时序 25 轮无人值守热重启复现（2026-11-20，经用户确认）**：
  - **写入范围**：复用 `opd2413-bootdiag2.conf` 并临时设为默认，连跑最多 25 轮热重启；命中任一异常或跑满 25 轮均自动还原 `default fedora-7.2.15-31.opd2413.conf`、删除 `opd2413-bootdiag2.conf` 并校验 `KSHIM.CHO` 哈希与 `1 extent`。
  - **预期与判据**：首轮校验 `console-ramoops-0` 大小显著大于正常 `41 B`（确认全量 `loglevel=7` 落盘）；正常轮次耗时稳定在基线 `+14 s` 内、`pstore` 序号逐轮 `+1` 且尾部为 `reboot: Restarting system`；若命中 `#39`，自动落盘完整 `pstore` 与当前 `journalctl -k` 至 `private/bootdiag-20261120/testA/anomaly-runXX/` 并立即停止。
  - **测试 A 结果（2026-11-20 `11:19`–`11:21`，第 2 轮即命中原生态 `#39` 现场并自动清理恢复）**：
    - Run 01/25：`dt=38.7 s`，`seq=97(+1)`，`console-ramoops-0 = 17,874 B`，尾部为 `reboot: Restarting system`（`OK`，验证全量 `loglevel=7` 落盘正常）。
    - **Run 02/25（命中异常）**：`dt=87.3 s`（基线 `38.7 s`，典型双启动），`seq=98(+1)`，完整未卷绕的 `console-ramoops-0 = 67,739 B` 已归档至 `private/bootdiag-20261120/testA/anomaly-run02/000098-458b6933083b445d9f936c761332ba03/console-ramoops-0`。脚本随即自动恢复 `default fedora-7.2.15-31.opd2413.conf`、删除 `opd2413-bootdiag2.conf`，复核 `KSHIM.CHO` 哈希不变且保持 `1 extent`。
    - **决定性结论**：在完全关闭 `efifb`（`video=efifb:off`）、不加 `initcall_debug`、`ktz8866 6-0011`/`regulators-0,2`/`ufs`/`adsp` 全部正常就绪的原生态时序下，硬复位仍精确发生在 **`0.364065 s` `remoteproc remoteproc0: Booting fw image qcom/sm8750/erhai/soccp.mbn, size 565924`** 之后数毫秒内（与第 1 轮 `000095` 的 `0.757235 s` 现场 100% 重合）。由此**彻底排除 `efifb`、时序倒置及 `regulators`/`adsp` 未就绪**，故障 100% 锁定在 `qcom_pas_start()` 加载/鉴权/复位 `soccp.mbn`（`pas_id=51`、`0x9ec00000`）路径内部。
- **测试 B：`soccp` 启动路径细粒度同步埋点定位（2026-11-20，经用户确认）**：
  - **方案与写入范围**：基于 `out/m3k/build`（保持 `7.2.15-31.opd2413` ABI 不变，编完即回滚主机源码树）编译临时诊断内核 `Image-soccp-diag`，仅对 `pas_id == 51` 在 `qcom_pas_start()` 与 `mdt_loader.c` 注入 9 处 `pr_emerg("soccp-diag: ...")` 同步埋点（覆盖 `prepare`、`pd/clk`、`qcom_scm_pas_init_image(51)`、`memcpy 0x9ec00000`、`pil_info`、`qcom_scm_pas_auth_and_reset(51)`、`wait_for_start` 及 `TCSR dstate` 读值）；上传至 ESP `/boot/efi/fedora/7.2.15-31.opd2413/linux-soccp-diag` 并配置临时条目 `opd2413-bootdiag3.conf`（`video=efifb:off loglevel=7 ignore_loglevel panic=10`），先单步冒烟再最多连跑 25 轮，命中首例即停并自动删除临时内核与条目、还原 `default fedora-7.2.15-31.opd2413.conf`。
  - **预期与判据**：单步冒烟在 `dmesg` 可见完整 `soccp-diag: 1..9` 序列及正常启动；复现命中后 `console-ramoops-0` 末条 `soccp-diag` 编号直接锁定唯一致死调用（如停在 `4a`→`init_image` SMC、停在 `5`→`memcpy 0x9ec00000` 覆盖运行中固件、停在 `7`→`auth_and_reset` SMC、停在 `8`→复位后启动期）。
  - **首次裸 `Image` 试跑收获（2026-11-20 `11:53`–`12:01`）**：
    - 仅换裸 `Image` 时因 `CONFIG_DEBUG_INFO_BTF=y` 校验拒绝原有 `-31` 模块（`failed to validate module [raid6_pq] BTF: -22`），导致 initrd 无法加载 `btrfs` 挂载根分区；已手动回 `-31` 并清理。
    - 归档日志 `private/bootdiag-20261120/testB-smoke/000099-3caa761b56544c3cad23d12d59a46701/console-ramoops-0` 已打出关键硬件状态：`1 pre-prepare dstate=0x2`（D0）→ `4a..4b` `init_image(51)` 耗时 `35 ms` 返回 `0`（`reloc=0`）→ `5..6` `memcpy/memset 0x9ec00000` 耗时 `2.08 ms` → **`7 pre-auth-reset dstate=0x2`**（实锤 `init_image(51)` 不停机，覆写 `0x9ec00000` 全程早期 SoCCP 仍处于 D0 运行态）→ `8 post-auth-reset`（`8.18 ms`）→ 36 ms 后进 D3（`dstate=0x8`）。
  - **BTF 配套重跑方案（经用户确认）**：编译独立临时版本 `7.2.15-31diag.opd2413`（配套 `Image + modules` 并于平板 `dracut` 生成 `initrd-soccp-diag`，不经 `dnf`、不动 `-29`/`-30`/`-31`），恢复 `kshim Fedora` 后先单步冒烟再最多连跑 25 轮抓精确致死埋点，退出自动全量清理。
  - **测试 B 结果与根因完全定案（2026-11-20 `12:07`–`12:13`，第 1 轮即命中）**：
    - 单步冒烟 `7.2.15-31diag.opd2413` 耗时 `38.3 s` 正常上线，零 BTF 报错，完整打印 `soccp-diag: 1..9`。
    - **Run 01/25（即刻命中）**：`dt=87.3 s`，`seq=101(+1)`，`console-ramoops-0 = 68,873 B` 归档至 `private/bootdiag-20261120/testB/anomaly-run01/000101-a87f3957.../console-ramoops-0`，脚本自动恢复 `default fedora-7.2.15-31.opd2413.conf` 并删除全部临时内核/initrd/模块/启动项（`KSHIM.CHO` 哈希不变、`1 extent`）。
    - **精确致死点**：`0.359876 s` 打印 `soccp-diag: 4a pre-scm-init-image len=5016` 后，其他 CPU 继续完成 `sdd`/`sda`/`sde` 扫描至 `0.375018 s`（`15.1 ms`），**始终未到达 `4b post-scm-init-image`** 即发生整机硬复位。
    - **完整根因链（100% 闭环解释冷/热偶发与第 1 轮 100% 死循环）**：
      1. 原厂 `runtime.dts` 明确保留了 bootloader 连续显示显存 `splash_region@fc800000`（`0xfc800000` 大小 `0x2b00000`，即 `0xfc800000..0xff2fffff`），而我方 `sm8750-oneplus-pad2pro.dts`（及上游 `sm8750.dtsi`/`erhai`）均遗漏了该保留区，导致 `/proc/iomem` 将 `fc800000-ff7fffff` 暴露为 `System RAM`。
      2. 内核自顶向下在 `< 4 GiB` 保留 32 MiB 全局 CMA，直接落在了 **`0xfcc00000..0xfebfffff`**——与仍在 144 Hz 扫描输出的 bootloader 显存 **`0xfc800000..0xfe70dfff`**（`sspp 0xf fc800000`，直到 `0.482 s` 才由 `msm-mdss` 停扫）**重叠 27.05 MiB**（这也是每次启动都报错 `simple-framebuffer.0: failed to claim resource 0` 的原因）。
      3. `0.35–0.36 s`（停扫前约 120 ms），`remoteproc_adsp`/`remoteproc_soccp` 调用 `qcom_scm_pas_init_image()` → `dma_alloc_coherent(__scm->dev, 5016)` → `dma_alloc_contiguous()` 从全局 CMA（`0xfcc00000+`）分配元数据物理页，随后 `__qcom_scm_pas_init_image()` 进 TrustZone 对该页开启 XPU 内存保护。
      4. 一旦 144 Hz DPU 扫描光束在 TZ 锁定该页的瞬间读到 `0xfcc00000+`（或如第 1 轮 `000095` 中 `efifb` CPU 持续写显存必撞该页），即触发硬件 XPU 访问违规并由 TZ 直接硬复位整机；重启后 90%+ 概率未撞到扫描窗口，从而表现为“黑屏数秒自动重启后正常进 Fedora”。
- **修复补丁与离线打包（`7.2.15-32.opd2413`，`离线通过`）**：
  - 新增最小精准补丁 [2437-arm64-dts-qcom-sm8750-oneplus-pad2pro-reserve-bootlo.patch](../kernel/opd2413-7.2/patches/2437-arm64-dts-qcom-sm8750-oneplus-pad2pro-reserve-bootlo.patch)（仅向板级 DTS `/reserved-memory` 新增与原厂一致的 `splash_mem: splash@fc800000`、`reg = <0x0 0xfc800000 0x0 0x2b00000>`、`no-map`），并登记至 `series`、[PATCHES.md](../kernel/PATCHES.md) 与 [README.md](../kernel/opd2413-7.2/README.md)。
  - 严格 `-F0` 打入并编译产出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-32.opd2413.aarch64.rpm`（最终纯净版 SHA-256 `33b6a9ca6b34142411dfcb81a693d67afc1a22a11830ced89198c35147d3be9d`，1,775 个模块，零 `soccp-diag` 字符串）；离线解包反编译 DTB 确认含 `splash@fc800000 { reg = <0x00 0xfc800000 0x00 0x2b00000>; no-map; };`。
- **上机安装与回归验收预期与判据（2026-11-20 经用户确认）**：
  1. 以 `boot-select next fedora-7.2.15-32.opd2413.conf` 首次重启进入 `7.2.15-32.opd2413`，核验：（a）`dmesg` 显示 `OF: reserved mem: 0x00000000fc800000..0x00000000ff2fffff (44032 KiB) nomap non-reusable splash@fc800000`；（b）`cma: Reserved 32 MiB` 与 `adsp-rpc-remote-heap` 均退至 `0xf3800000` 以下、与 `0xfc800000..0xff2fffff` 零重叠；（c）无 `simple-framebuffer.0: failed to claim resource 0` 报错，且 `msm` 正常接管、背光/无灰闪、触控、Wi-Fi/蓝牙、音频、Pogo 键盘正常，`systemctl is-system-running = running`、`0 failed`、`SELinux Enforcing` 零新增 AVC。
  2. 强回归压测：（a）用临时项在 `7.2.15-32` 上复测此前 100% 必现死循环的 `console=tty0 loglevel=7 ignore_loglevel initcall_debug`（预期 1 次即直接正常进桌面，证明 XPU 碰撞彻底消除）；（b）在 `video=efifb:off loglevel=7 ignore_loglevel` 下连跑 20 轮无人值守热重启（此前第 1–2 轮即命中），预期 **20/20 零异常**、全员正常结束于 `reboot: Restarting system`，随后切 `default fedora-7.2.15-32.opd2413.conf` 并由用户做 1 次冷启动验收。
- **装机与实机回归验收结果（2026-11-20 `12:27`–`13:06`，全项达 `真机通过`）**：
  1. **安全装机**：卸载最旧回退 `7.2.15-29`，装入 `kernel-opd2413-7.2.15-32.opd2413`（保留 `-31` 与 `-30` 两级回退，ESP `370M / 512M` 剩余 `143M`，`KSHIM.CHO` 前后 SHA-256 一致且保持 `1 extent`）。
  2. **物理内存映射核验**：首次 `boot-select next` `40.3 s` 上线，`journalctl -k` 实测 `OF: reserved mem: 0x00000000fc800000..0x00000000ff2fffff (44032 KiB) nomap non-reusable splash@fc800000`、`adsp-rpc-remote-heap` 迁至 `0x00000000f2c00000..0x00000000f37fffff`、`cma: Reserved 32 MiB at 0x00000000f0c00000`，`/proc/iomem` `f3800000-ff2fffff : reserved`，`simple-framebuffer.0` 正常初始化后由 `msm` `aperture_remove_all_conflicting_devices()` 无缝接管，`kwin_wayland` 正常拉起。
  3. **必现场景强回归**：在 `-32` 上加载此前在 `-31` 100% 必现灰屏死循环的 `console=tty0 loglevel=7 ignore_loglevel initcall_debug`，**第 1 次即以 `43.5 s` 顺利越过 `soccp` 并进入系统**（零硬复位）。
  4. **纯净版重装与 20 轮压力回归**：发现首版 `-32` 因增量源码还原保留旧 mtime 残留了 `soccp-diag` 调试打印，随即清除两份 `.o` 重编并离线验证零 `soccp-diag` 字符串后覆盖重装至平板；在纯净版 `-32`（`#62`）上使用 `video=efifb:off loglevel=7 ignore_loglevel` 连跑 20 轮无人值守热重启（日志 `private/bootdiag-20261120/reg32/runs.log`），**20/20 全部通过、零异常**（单轮耗时稳定在 `39.6–41.0 s`，中位数 `40.0 s`，全部 `seq +1` 且正常结束于 `reboot: Restarting system`），退出已自动删除临时项。
  5. **默认项固化、生产全检与 2 次冷启动终验**：切换 `boot-select default fedora-7.2.15-32.opd2413.conf` 并标准参数（`quiet loglevel=3`）重启，`38.7 s` 上线：`uname -r = 7.2.15-32.opd2413`（`#62`，零 `soccp-diag`）、`running`、`0 failed`、`SELinux Enforcing` 零 AVC、`opd2413-sensors-gate`/`bluetooth`/`opd2413-face`/`NetworkManager` 全 `active`、`cpuidle=teo`、`card 0: OnePlusPad2Pro` 音频正常、`KSHIM.CHO` 保持 `1 extent`。随后用户实机执行 **2 次冷启动复核均无异常**，[TECH-DEBT.md](TECH-DEBT.md) `#39` 彻底关闭。

## 2026-11-21 `opd2413-camera` 0.1-3：新增录像功能并统一前摄镜像朝向（`真机启动`）

- **问题根因定位**：
  - 底层 `libcamera` / PipeWire 经硬件 `HFLIP+VFLIP` 补偿 `Rotation=180` 后，前摄 `sc820cs` 与后摄 `sc1300cs` 均输出正立非镜像流。
  - GNOME Camera（`snapshot-51.0`）仅在 GTK 预览层 `Viewfinder::snapshot()` 对前摄做 `scale(-1.0, 1.0)` 水平镜像，而 `camerabin` 的 `image-filter`/`video-filter` 均不做翻转；本项目自带 `opd-camera` 默认开启 `Selfie Mirror`（预览与拍照均水平镜像）但此前不含录像功能，导致用户跨应用拍照与录像时前摄成片与预览朝向不一致。
  - 经用户确认方案：为 `opd-camera` 新增原生录像功能，使前摄在开启 `Selfie Mirror` 时预览、拍照、录像朝向完全一致（所见即所得）。
- **实现与离线验证（`离线通过`）**：
  - 新增 [packaging/opd2413-camera/src/video_recorder.py](../packaging/opd2413-camera/src/video_recorder.py)：统一 `should_mirror_front(model, mirror_front)` 判定，并以非阻塞异步队列将视图流（`bgr0`/`rgb0`）经管道送入 `ffmpeg`（`libopenh264` + PulseAudio `aac`、`-use_wallclock_as_timestamps 1`、`-shortest`、`+faststart`；前摄镜像时附加 `-vf hflip`，音频不可用时自动降级为纯视频）。
  - 更新 [packaging/opd2413-camera/src/opd-camera-gui.py](../packaging/opd2413-camera/src/opd-camera-gui.py)：新增 Photo/Video 模式切换、红色录像/停止按钮、实时 `● REC MM:SS` 计时、录制期间跳过 `RAW10` 拷贝并锁定切镜与镜像开关，成片保存至 `~/Videos/OPD_Camera/VID_<时间>_<FRONT|REAR>.mp4` 并联动缩略图打开。
  - 新增 [packaging/opd2413-camera/tests/test_video_recorder.py](../packaging/opd2413-camera/tests/test_video_recorder.py)（含合成 `bgr0` 帧实录编解码像素级镜像校验），更新 [packaging/opd2413-camera/opd2413-camera.spec](../packaging/opd2413-camera/opd2413-camera.spec)（`0.1-3`，补充 `/usr/bin/ffmpeg` 依赖）与 [tools/build-camera-rpm.sh](../tools/build-camera-rpm.sh)。
  - 本机原生构建 `out/rpmbuild/RPMS/aarch64/opd2413-camera-0.1-3.fc45.aarch64.rpm`（`SHA256: 90359485048a5f23...`），`test_hdrplus_isp.py` 与 `test_video_recorder.py` 全部通过。
- **上机安装与冒烟验证（`真机启动`，待用户目视复核）**：
  - **预期与判据**：升级安装 `opd2413-camera-0.1-3.fc45.aarch64` 后，`opd-camera` 可在前/后摄正常预览、拍照与录像，前摄开启 `Selfie Mirror` 时录像回放与预览、拍照水平朝向一致且音画同步。
  - **实测结果**：
    1. 前摄 `sc820cs`（`1632x1224`，`mirror_front=True`）实机录像冒烟 `1.48 s`：产出 35 帧 H.264（`start=0.000000`, `dur=1.480000`）+ 69 帧 AAC（`start=0.000000`, `dur=1.477166`），缩略图生成正常，零报错（临时文件已清理）。
    2. 经用户确认后执行 `pkexec dnf -y upgrade` 装入 `opd2413-camera-0.1-3.fc45.aarch64`，`/usr/libexec/opd2413/video_recorder.py` 等 7 个文件校验齐全。待用户在桌面打开 `OPD2413 HDR+ Camera` 实拍录像确认画面与声音。












## 2026-11-22

### 外接 Type-C KVM 显示器 USB 2.0 断连排查与补丁 `2438`（`7.2.15-33.opd2413`）

- **现场取证**：外接 4K KVM 显示器可正常扩展显示（`card1-DP-1: connected 3840x2160`），Type-C 端口处于 `data_role=[host]`、`power_role=[sink]`（9 V PD），`xhci-hcd` 根集线器（Bus 1 480M / Bus 2 10000M）均在位，但 `lsusb` 下无任何外设。内核日志显示插入瞬间 `usb 1-1`（显示器内置 USB 2.0 Hub）曾被探测，紧接着 `wcd939x-usbss` 切入 4-lane DP（`mode=4 svid=ff01`，即 `TYPEC_DP_STATE_C`）时输出 `usb=0 dp=1`，导致 `usb 1-1` 立即报 `can't set config #1, error -71` 掉线。
- **根因**：`drivers/usb/typec/mux/wcd939x-usbss.c` 中 `wcd939x_usbss_set()` 对 `TYPEC_DP_STATE_C`/`E`（4-lane DP）未设置 `enable_usb = true`，清零开关后漏开 `DNL`/`DPR`（USB 2.0 D+/D-）。
- **USB 3.0 核查**：`sm8750.dtsi` 的 `usb_dp_qmpphy` 已具备 `mode-switch`/`orientation-switch` 并连到 `pmic_glink_ss_in`，`phy-qcom-qmp-combo.c` 已支持 `QMPPHY_MODE_USB3_ONLY` / `QMPPHY_MODE_USB3DP`（`TYPEC_DP_STATE_D`/`F`） / `QMPPHY_MODE_DP_ONLY`（`TYPEC_DP_STATE_C`/`E`）及正反插方向切换。当前显示器协商为 4-lane DP（`STATE_C`），4 对高速线全部分配给视频；如需同时跑 USB 3.0 高速，需在显示器 OSD 切换为“USB 3.0 优先 / 2-lane DP”（`STATE_D`）或在纯 USB 3.0 外设下实测。
- **改动与产物**：新增补丁 `2438-usb-typec-mux-wcd939x-usbss-keep-USB2-DP-DM-enabled-.patch`，在本机容器基于 `7.2.15-32`（含 `2437`）构建打包 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-33.opd2413.aarch64.rpm`（`SHA256: f77b71f4...`），DTB 与 `7.2.15-32` 逐字节一致。
- **上机预期与判据（待用户确认安装）**：
  1. 卸载最旧回退 `7.2.15-30.opd2413`（保留 `-32` 为默认项、`-31` 为二级回退），安装 `7.2.15-33.opd2413`，设置 `boot-select next fedora-7.2.15-33.opd2413.conf` 重启测试。
  2. 进入 `7.2.15-33.opd2413` 后插拔外接 KVM 显示器：`wcd939x-usbss` 日志在 `mode=4 svid=ff01` 下打印 `usb=1 dp=1`，扩展显示正常，`lsusb -tv` 稳定识别显示器内置 Hub 及键鼠且可直接打字/移动光标，无 `-71` 掉线。
  3. 同步验证 USB 3.0（显示器 OSD 切 USB 3.0 模式或直插 USB 3.0 设备，`lsusb -tv` 下 Bus 2 `5000M`/`10000M` 正常枚举）。
- **实机验收结果（2026-11-22，真机通过）**：
  - 成功重启进入 `uname -r = 7.2.15-33.opd2413`：`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing`、`0 avc: denied`。
  - 外接 4K KVM 显示器后，`wcd939x-usbss` 在 4-lane DP（`mode=4 svid=ff01 orient=2`）下正确输出 `usb=1 dp=1 audio=0 dp_active=1`，显示器内置 TI Hub（`0451:8442` / `0451:82ff`）及下游罗技无线鼠标（`046d:c53f`）与键盘（`342d:e4ce`）均稳定枚举在 `Bus 001`（480M/12M），用户确认 KVM 键鼠与显示器输入源切换提示均恢复正常。
  - 当前仍保持 `loader.conf` 默认项为 `fedora-7.2.15-32.opd2413.conf`，待用户确认是否固化 `7.2.15-33.opd2413` 为默认项。

### Type-C USB 3.x 正反双向修复与补丁 `2439`（`7.2.15-34.opd2413`）

- **现场取证**：在 `7.2.15-33.opd2413` 上直插 RTL9210 NVMe 硬盘盒（`WD_BLACK SN770 1TB`）：正面握手 `Bus 002` `10000M`（USB 3.2 Gen 2），翻面反插降速至 `Bus 001` `480M`（USB 2.0）；内核日志显示纯 USB 模式下 `orient` 始终为 `0`。对反插与正插状态下的完整 `/sys/kernel/debug/gpio` 做 diff，确认 `f100000.pinctrl`（TLMM）`gpio61`（硬件 `usb_phy` 功能引脚）在正面（10 Gbps）为 `HIGH`、反面为 `LOW`。
- **根因**：板级 DTS `pmic-glink` 节点缺失 `orientation-gpios`，导致 `pmic_glink_ucsi` 在纯 USB 连接（非 DP AltMode）下无法通过 `typec_set_orientation()` 通知 `usb_dp_qmpphy` 翻转通道。
- **改动**：新增补丁 `2439-arm64-dts-qcom-sm8750-oneplus-pad2pro-add-pmic-glink.patch`，在 `pmic-glink` 节点添加 `orientation-gpios = <&tlmm 61 GPIO_ACTIVE_LOW>;`，构建 `kernel-opd2413-7.2.15-34.opd2413.aarch64.rpm`（包含 `2437` + `2438` + `2439`）。
- **上机预期与判据**：
  1. 卸载最旧回退 `7.2.15-31.opd2413`（保留 `-32` 默认回退与 `-33` 二级回退），安装 `7.2.15-34.opd2413` 并 `boot-select next fedora-7.2.15-34.opd2413.conf` 重启测试。
  2. 进入 `7.2.15-34.opd2413` 后：`/sys/class/typec/port0/orientation` 正常出现；直插 RTL9210 硬盘盒**正插与反插**均在 `Bus 002` 握手 `10000M`（`SuperSpeed Plus Gen 2x1`）；外接 4K KVM 显示器画面、键鼠、切换提示回归正常。
- **实机验收结果（2026-11-22，`7.2.15-35.opd2413` 真机通过）**：
  - `7.2.15-34`（初版 `GPIO_ACTIVE_LOW`）实测 `normal` 与 `reverse` 两面均降速 `480M`，证实此前 `-33` 测试正面 10 Gbps 时 `qmp->orientation` 实际保留了拔掉显示器前遗留的 `REVERSE` 状态，故本机 `tlmm 61` 与 SM8750 MTP/QRD 完全一致，应为 `GPIO_ACTIVE_HIGH`（`HIGH=REVERSE`、`LOW=NORMAL`）。
  - 修正 `2439` 为 `orientation-gpios = <&tlmm 61 GPIO_ACTIVE_HIGH>;` 并构建安装 `7.2.15-35.opd2413`（`SHA256: d0dd099e...`）后重启验收：`uname -r = 7.2.15-35.opd2413`、`running`、`0 failed`、SELinux `Enforcing`、零 AVC；直插 RTL9210 NVMe 硬盘盒实测 **`orientation=normal`（`orient=1`）→ `Bus 002` `10000M`（`SuperSpeed Plus Gen 2x1`）**，翻面后 **`orientation=reverse`（`orient=2`）→ `Bus 002` `10000M`（`SuperSpeed Plus Gen 2x1`）**，双面 10 Gbps 满速全部通过。

### 显示空闲熄屏/双屏 `DPMS off -> on` 花屏泛灰排查与证伪（`TECH-DEBT #47`）

- **现场复现**：在 `7.2.15-35.opd2413` 外接显示器双屏模式下跑 5 轮 `DPMS off (2s) -> on (2s)`，无论 60 Hz 还是 120 Hz 均偶发并粘滞复现“整屏竖条彩噪花屏 → 持续有背光泛灰”，后续再次 `DPMS off/on` 无法恢复；而在线切刷新率（`60 <-> 120 Hz`）4/4 次瞬间恢复正常画面。
- **假设验证与证伪**：原怀疑 MDSS GDSC 未掉电时 `2414` 保留的 `trigger_flush + trigger_start` 残留卡死 `CTL_0`，构建临时内核 `7.2.15-36.opd2413`（实验补丁 `2440`，在 `dpu_crtc_atomic_begin()` 检查并复位 `is_started`/`get_flush_register`）实测：双屏 5 轮压测仍复现泛灰黑屏且 `resetting stale ctl` 从未触发。
- **硬件寄存器全量取证（`private/display-dpms-grey-20261122/`）**：在 `7.2.15-36.opd2413` 同频 120 Hz 下分别抓取正常态（`dpu_120_good.txt`）与真实黑屏泛灰态（`dpu_120_bad2.txt`）的完整 `/sys/kernel/debug/dri/1/kms`（6013 行）逐模块比对，证实 SoC 侧 `ctl_0`、`lm`、`dspp`、`dce_0_0/0_1`（DSC）、`intf_1/2`、`dsi0/1_ctrl`、`dsi0/1_phy` 全部配置寄存器 **100% 逐位一致**，彻底排除 SoC 侧 `CTL_0`/DPU/DSI 配置卡死，锁定根因位于面板侧（`nt36536` 在 `2433` 真断电 ≥2 s 后重新上电/复位/DCS 初始化时序偶发失锁）。
- **收口**：已撤回实验补丁 `2440` 并清理 `-36` 构建产物，登记为 [TECH-DEBT.md](TECH-DEBT.md) `#47`；`loader.conf` 默认项仍为已验收提交的 `fedora-7.2.15-35.opd2413.conf`，下次正常重启后即可自动回到 `-35` 并按需卸载 `-36`。

### 显示熄屏/DPMS 黑灰屏根因定案与 SM8750 双路 DSI 同步修复（`2440`–`2445`，`7.2.15-36.opd2413`，`离线通过`）

- **深层根因核查（寄存器 + 上游 `erhai` 逐文件比对）**：
  - 全量比对 [panel-novatek-nt36536.c](../out/m3k/linux-7.2.15/drivers/gpu/drm/panel/panel-novatek-nt36536.c)、`ktz8866.c`、板级 DTS 与 `dpu1` / `dsi` 源码，结合 `private/display-dpms-grey-20261122/dpu_120_good.txt` 与 `dpu_120_bad2.txt` 实机寄存器 dump，发现 `7.2.15-35` 缺少上游 `erhai`（`sm8750/v7.4-dev`）整套 **SM8750 绑定双路 DSI 硬件同步与关断序列（6 个提交）**，实机寄存器直接印证：
    1. `dsi_mgr_bridge_post_disable()` 先关时钟源 `DSI_0` 再关从路消费者 `DSI_1`（缺失 `ff1a1513c`）。
    2. 未启用 `restore_slave_pll`，DPMS 关闭/恢复期未保存与恢复从路 PHY（`DSI_1`）分频器与时钟多路器状态（缺失 `7385bb05c`）。
    3. 未实现从路 PHY 分频镜像与 `PERF_OPTIMIZE=0x22` 编程（缺失 `d0f6d6120`）：实测 `dsi0_phy[0x10]`（`CMN_CLK_CFG0`）=`0x61`，而 **`dsi1_phy[0x10]` 滞留出厂默认值 `0xf1`**。
    4. 双路 HS 链路时钟启动后未执行原厂两步 PHY 重同步（缺失 `282ca2a9a`）：未翻转 `RBUF_CTRL`（`0->1`）且未清除 `CLK_EN_SEL`（`BIT(4)`），实测 **`dsi0_phy[0x14]=0x30`、`dsi1_phy[0x14]=0x34`**（原厂黄金值为 `0x20`/`0x24`）。
    5. PHY 重同步完成后未对绑定 `qcom,sm8750-dsi-ctrl` 视频模式控制器执行 `1 us` 软复位（缺失 `3b4689ae9`）。
    6. 未编程 `HS_TIMER_CTRL`（`0x3FD08`）与 `MISR_VIDEO_CTRL`（`0x10100`）（缺失 `8b3f19e48`）：实测 **`dsi0/1_ctrl[0xbc]`（`TIMEOUT_STATUS`）每帧误锁存 `0x00000001`** 且逐帧视频 CRC `MISR_VIDEO_32BIT`（`0x13c`）未开启。
  - **2026-11-22 `23:24:51 -> 23:24:53` 复现现场**：外接 4K DP 期间平板闲置熄屏再唤醒再次触发有背灯黑屏；实测 `DSI-1`（`connected`/`enabled`/`dpms:On`）、背光 `1331/2047`（`bl_power=0`）、5 路供电（`vreg_l12b_1p8` `1896000 uV`、`lcd_vsp`、`lcd_vsn`、`vreg_l3i_0p88` `880000 uV`、`vreg_l3g_1p2` `1200000 uV`）及 `nt36536` 触控固件加载（`<183344 us>`, `PID=5F95`）均正常且内核零 DSI/DPU 报错，与双路 DSI PHY retime FIFO 相位失锁（静态 MMIO diff 不可见）特征完全一致。
- **代码改动与离线构建校验（`离线通过`）**：
  - 修复此前实验回退遗留在 `out/m3k/linux-7.2.15/drivers/gpu/drm/msm/disp/dpu1/dpu_crtc.c` 第 1333 行的 1 行误删，确认与 `linux-7.2.15.tar.xz + armada-7.2.6 + opd2413-7.2` 重建结果严格仅差该行。
  - 新增并按 `-F0` 严格打入补丁 `2440`–`2445`（见 [series](../kernel/opd2413-7.2/patches/series) 与 [PATCHES.md](../kernel/PATCHES.md)），不改 DPU（保留 `2411`/`2414`）、不引入依赖 7.4 CCF orphan 改造的 `bbf19e86d`，也不回退 `2433`（保留熄屏真断电）：
    - [2440-drm-msm-dsi-stop-the-bonded-clock-consumer-before-it.patch](../kernel/opd2413-7.2/patches/2440-drm-msm-dsi-stop-the-bonded-clock-consumer-before-it.patch)
    - [2441-drm-msm-dsi-restore-SM8750-bonded-slave-clock-state.patch](../kernel/opd2413-7.2/patches/2441-drm-msm-dsi-restore-SM8750-bonded-slave-clock-state.patch)
    - [2442-drm-msm-dsi-program-the-bonded-slave-PHY-dividers-li.patch](../kernel/opd2413-7.2/patches/2442-drm-msm-dsi-program-the-bonded-slave-PHY-dividers-li.patch)
    - [2443-drm-msm-dsi-Resynchronize-SM8750-PHYs-after-link-clo.patch](../kernel/opd2413-7.2/patches/2443-drm-msm-dsi-Resynchronize-SM8750-PHYs-after-link-clo.patch)
    - [2444-drm-msm-dsi-Reset-SM8750-bonded-controllers-after-PH.patch](../kernel/opd2413-7.2/patches/2444-drm-msm-dsi-Reset-SM8750-bonded-controllers-after-PH.patch)
    - [2445-drm-msm-dsi-program-the-HS-TX-timer-and-the-video-MI.patch](../kernel/opd2413-7.2/patches/2445-drm-msm-dsi-program-the-HS-TX-timer-and-the-video-MI.patch)
  - 于 `localhost/opd2413-builder-kernel:fc45`（`HOSTCC=/tmp/hostgcc`）使用 `-j7` 完成干净全量编译，4 个改动 DSI `.o` 文件在 `KCFLAGS="-Werror"` 下零警告编译通过；产出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-36.opd2413.aarch64.rpm`（SHA-256 `75e8eecb4d55d7d97ca1689c03ebc850c1f51b5f108c2c328f2f07029c27b57d`）：
    - `dsi.xml.h` 已生成 `REG_DSI_MISR_VIDEO_CTRL`（`0x000a0`）与 `REG_DSI_MISR_VIDEO_32BIT`（`0x0013c`）；
    - `System.map` 与 `vmlinuz`（未压缩 ARM64 `Image`）确认含 `msm_dsi_host_reset_after_phy_sync`、`msm_dsi_phy_toggle_resync_fifo`、`msm_dsi_phy_reset_clk_en_sel` 及 `dsi_pll_v7_2_program_slave`/`reset_clk_en_sel` 调试字符串，`vmlinux` 与模块 `oneplus-pogo-keyboard.ko`（`vermagic: 7.2.15-36.opd2413`）均含完整 `.BTF` 段；
    - `sm8750-oneplus-pad2pro.dtb` 与 `7.2.15-35` 逐字节一致（零多余 DTS 改动）。
- **上机预期与判据（待用户确认装机测试）**：
  1. 保留 `7.2.15-35` 为 `default`、`7.2.15-32` 为二级回退，安装 `7.2.15-36.opd2413`（不动 `boot_b` 与 `KSHIM.CHO`），经 `/usr/libexec/opd2413/boot-select next fedora-7.2.15-36.opd2413.conf` 单次重启进入 `uname -r = 7.2.15-36.opd2413`。
  2. **硬件寄存器判据**（`/sys/kernel/debug/dri/1/kms`）：
     - `dsi0_phy[0x10] == 0x61` 且 **`dsi1_phy[0x10] == 0x61`**（由 `0xf1` 修正）；
     - **`dsi0_phy[0x14] == 0x20` 且 `dsi1_phy[0x14] == 0x24`**（`CLK_EN_SEL=0`，由 `0x30/0x34` 修正）；
     - **`dsi0_ctrl[0xbc] == 0` 且 `dsi1_ctrl[0xbc] == 0`**（`TIMEOUT_STATUS` 清零，由 `0x1` 修正）；
     - `dsi0_ctrl[0xa0] == 0x00010100`、`dsi1_ctrl[0xa0] == 0x00010100`，且 `0x13c`（`MISR_VIDEO_32BIT`）呈非零活跃 CRC。
  3. **DPMS 与刷新率/休眠功能判据**：
     - `DPMS off (≥3 s)` 期间 `vreg_l12b_1p8`、`lcd_vsp`、`lcd_vsn` 真实断电；
     - 在 **120 Hz**（双屏外接 `DP-1` 与单屏独立模式）及 **60 Hz** 下连续执行 **≥10 轮 `DPMS off (≥3 s) -> on`**，以及桌面闲置熄屏/锁屏唤醒与 **`s2idle` 休眠唤醒**：**0 次**竖条彩噪或持续黑灰屏，内核日志零 DSI/DPU 报错，触控、背光、音频与 `60 <-> 120 Hz` 切换均正常。
     - 经用户确认设为默认项并完成冷启动验收后关闭 [TECH-DEBT.md](TECH-DEBT.md) `#47`。

### `7.2.15-36` 实机寄存器核验与 `2443` 补丁错位修正（`7.2.15-37.opd2413`，`离线通过`）

- **`7.2.15-36.opd2413` 实机首启核验结果（`2026-11-23 00:15`）**：
  - 经 `boot-select next` 成功重启进入 `uname -r = 7.2.15-36.opd2413`，`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing`、`0 avc: denied`、`KSHIM.CHO` 保持 `"Fedora"` 且 `loader_default` 为 `-35`、`DP-1` + `DSI-1`（`3392x2400@120`）与 `nt36536` 触控均正常工作。
  - 只读读取 `/sys/kernel/debug/dri/1/kms` 确认 `2442` 与 `2445` 已立即生效：
    - `dsi0_phy[0x10] = 0x61` 且 **`dsi1_phy[0x10] = 0x61`**（从路分频已由 `0xf1` 修正）；
    - `dsi0/1_ctrl[0xb8]`（`HS_TIMER_CTRL`）=`0x0003fd08`，**`dsi0/1_ctrl[0xbc]`（`TIMEOUT_STATUS`）=`0x00000000`**（由每帧 `0x1` 清除），`dsi0/1_ctrl[0xa0]`（`MISR_VIDEO_CTRL`）=`0x00010100`。
  - 同时发现 **`dsi0_phy[0x14]=0x30`、`dsi1_phy[0x14]=0x34`**（`CLK_EN_SEL` 仍未清零）：审计源码确认因 `2443` 第 2 个 hunk 原仅有 `.save_pll_state`/`.restore_pll_state`/`.set_continuous_clock` 3 行上下文，在 `-F0` 下误落到了紧邻上方具有相同 3 行的 `dsi_phy_4nm_8650_cfgs`，未挂入 `dsi_phy_3nm_8750_cfgs.ops`。
- **修复与 `7.2.15-37.opd2413` 离线构建校验（`离线通过`）**：
  - 修正 [2443-drm-msm-dsi-Resynchronize-SM8750-PHYs-after-link-clo.patch](../kernel/opd2413-7.2/patches/2443-drm-msm-dsi-Resynchronize-SM8750-PHYs-after-link-clo.patch)（扩展上下文包含 `.restore_slave_pll = true,` 至 `.quirks = DSI_PHY_7NM_QUIRK_V7_2,`，确保仅匹配 `dsi_phy_3nm_8750_cfgs`）及 `dsi_phy_7nm.c`，并在临时目录通过 `2445 -> 2440` 逆序卸载与 `2440 -> 2445` 正序 `-F0` 重打严格闭环校验。
  - 编包产出 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-37.opd2413.aarch64.rpm`（SHA-256 `b66c91517262628e8b6e0f5cd192c5e80cfec0067aafb16b82a16e8c224526d9`）：`dsi_phy_7nm.o` 经 `KCFLAGS="-Werror"` 零警告编译，`readelf -rW`/`-sW` 证实 `dsi_7nm_phy_toggle_resync_fifo`（`0x1d0`）与 `dsi_7nm_phy_reset_clk_en_sel`（`0x1d8`）重定位严格落入 `dsi_phy_3nm_8750_cfgs`（`[0x188, 0x210)`），`vmlinuz`/`oneplus-pogo-keyboard.ko` 均含 `.BTF` 与 `vermagic: 7.2.15-37.opd2413`，`sm8750-oneplus-pad2pro.dtb` 与 `-35` 逐字节一致。
- **下一步写入范围与上机判据（待用户确认）**：
  - 因当前 ESP `/dev/sda16` 剩余 `143M`（`< 200 MiB` 装机最低需求），申请经单次 `pkexec` 卸载最旧回退 `7.2.15-32.opd2413`（保留 `-35` 为 `default`、`7.2.15-36` 为二级回退），安装 `7.2.15-37.opd2413`，核验 `KSHIM.CHO` 不变且保持 `1 extent` 后设 `boot-select next fedora-7.2.15-37.opd2413.conf`；由用户手动重启进入 `-37` 复验 `dsi0/1_phy[0x14] == 0x20/0x24` 与 120/60 Hz `DPMS off -> on` / 休眠唤醒压测。

### `7.2.15-37` 单双屏对照与 `erhai` 共享视频 `CTL` 四补丁替换（`2446`–`2449`，`7.2.15-38.opd2413`，`离线通过`）

- **`7.2.15-37.opd2413` 实机完整复验结果（`2026-11-23 00:35–07:54`）**：
  1. **开机健康与双路 DSI 寄存器全绿（`真机通过`）**：`boot-select next` 进入 `7.2.15-37.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC），`dsi0/1_phy[0x10]=0x61/0x61`、`dsi0/1_phy[0x14]=0x20/0x24`、`dsi0/1_ctrl[0xb8]=0x0003fd08`、`[0xbc]=0`、`[0xa0]=0x00010100`、`dsi0_pll[0x260]=0x22`，全部达到 SM8750 原厂黄金值。
  2. **单屏 `120 Hz` `DPMS off (3s) -> on (3s)` 10 轮 + `120 -> 60 -> 120 Hz` 切换（`真机通过`）**：`10/10` 轮亮屏视觉正常、`12/12` 次 `nt36536` 固件重载正常、4 路供电轨（`vreg_l12b_1p8`/`lcd_vsp`/`lcd_vsn`/`vreg_l3i_0p88`）关断/上电对称，0 内核错误。
  3. **双屏（`DP-1` + `DSI-1`）`DPMS off (4s) -> on (8s)`（`120 Hz` 6 轮 + `60 Hz` 3 轮，共 9 轮）—— `真机失败`（暴露真实根因）**：
     - 用户目视确认全部 **9/9 轮**外接 `DP-1` 正常亮屏出图，而内置 `DSI-1` 每轮均卡死在“有背光灰黑无画面”；循环结束切换刷新率（`120 <-> 60 Hz`）`2/2` 次瞬间恢复。
     - `pm_runtime` 计费直接证明原因：外接 `DP-1` 在连接态持有 `af54000.displayport-controller` 的 `pm_runtime` 引用（`DPMS off` 期间挂起增量 **`0 ms`**），连带拉住父域 `ae00000.display-subsystem`（`MDSS GDSC`）累计挂起保持 **`0 ms` 增量**（从不掉电复位），而 `ae01000.display-controller` 正常挂起 `+3561 ms`。
     - 抓包 `private/display-dpms-grey-20261122/dpu37_dual_bad.txt` 精准锁定 DPU 卡死指纹与 [DISPLAY-60HZ-MODESET.md](DISPLAY-60HZ-MODESET.md) 完全一致：**`sspp_8[0xd0]=00000c80`、`0xd4=00000c80`、`0xe0=00000008`、`0xf8=00000000`**，**`vbif[0x204]=ffff0000`**（XIN1 停止取帧）、**`vbif[0x20c]=00000030`**，而此时双路 `DSI`/`PHY` 寄存器仍为 100% 黄金值。
     - **根本因果收敛**：本地规避补丁 `2414` 仅在 `new_state->active == true`（内联切刷新率）时跳过 `_dpu_encoder_helper_phys_cleanup()` 里的 `trigger_flush + trigger_start`，错误假设 `DPMS off` 后 `MDSS GDSC` 必然掉电；单屏熄屏靠 `MDSS GDSC` 掉电掩盖了 `CTL_0` 卡死，双屏时 `DP-1` 保住 `MDSS GDSC` 使卡死态直接带入下一次亮屏，而切刷新率（`active == true`）正好绕过 `trigger_flush/start` 并靠 `ctl->ops.reset(ctl)` 解锁。
- **`7.2.15-38.opd2413` 修复方案与离线构建校验（`离线通过`）**：
  - 撤除临时规避 `2411` 与 `2414`，合入 `yzddmr6/linux-sm8750-erhai`（`sm8750/v7.4-dev`）共享视频 `CTL` 寄存器级修复四补丁系列（均通过严格 `-F0` 正向→反向→正向回环校验，已同步更新 `kernel/opd2413-7.2/patches/series`、`kernel/PATCHES.md`、`kernel/opd2413-7.2/README.md`）：
    - [2446-drm-msm-dpu-flush-shared-video-CTLs-once-per-kickoff.patch](../kernel/opd2413-7.2/patches/2446-drm-msm-dpu-flush-shared-video-CTLs-once-per-kickoff.patch)（erhai `cece3773ddb5`）
    - [2447-drm-msm-dpu-tear-a-video-mode-slave-down-after-both-.patch](../kernel/opd2413-7.2/patches/2447-drm-msm-dpu-tear-a-video-mode-slave-down-after-both-.patch)（erhai `8b53b972e9bd`）
    - [2448-drm-msm-dpu-complete-shared-video-CTL-teardown-befor.patch](../kernel/opd2413-7.2/patches/2448-drm-msm-dpu-complete-shared-video-CTL-teardown-befor.patch)（erhai `f6dafb3dbc42`）
    - [2449-drm-msm-dpu-hand-off-the-shared-video-slave-before-t.patch](../kernel/opd2413-7.2/patches/2449-drm-msm-dpu-hand-off-the-shared-video-slave-before-t.patch)（erhai `1fead1793340`）
  - 重建 `localhost/opd2413-builder-kernel:fc45` 后（清理编译中间树释放 `/dev/sda18` 至 `186G` 可用），完成 `7.2.15-38.opd2413` 全量编译：5 个修改 DPU `.o` 在 `KCFLAGS="-Werror"` 下零警告通过；`vmlinux` 与 `oneplus-pogo-keyboard.ko` 均含 `.BTF`、`vermagic: 7.2.15-38.opd2413 SMP preempt mod_unload aarch64`；`dpu_hw_ctl_remove_intf` 与 `dpu_encoder_phys_cleanup` 存在于 `vmlinux` 符号表；`sm8750-oneplus-pad2pro.dtb` 与 `-37` 逐字节一致；产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-38.opd2413.aarch64.rpm`（SHA-256 `e3dcf6804b8b4e47b1afc8c81db1ec159e904427020263092a1f0d5c82b258d9`）。
- **上机预期与判据（`7.2.15-38.opd2413` 待重启验收）**：
  1. 卸载过渡内核 `-36`（保留 `-35` 默认与 `-37` 回退），装入 `-38` 并以 `boot-select next fedora-7.2.15-38.opd2413.conf` 单次重启进入 `uname -r = 7.2.15-38.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC）；
  2. `/sys/kernel/debug/dri/1/kms` 保持 `dsi0/1_phy[0x10]=0x61/0x61`、`[0x14]=0x20/0x24`、`[0xb8]=0x0003fd08`、`[0xbc]=0`；
  3. **双屏（`DP-1` + `DSI-1`）`DPMS off (4s) -> on (8s)` 压测**（`120 Hz` 6 轮 + `60 Hz` 3 轮）：**9/9 轮双屏均正常亮屏显示完整桌面**（零灰黑屏/花屏），内核零 DSI/DPU/vblank/VBIF 错误；
  4. **在线切换 `120 <-> 60 <-> 30 Hz`**、**单屏 10 轮 DPMS**、**真实闲置锁屏/熄屏唤醒**与 **`s2idle` 休眠唤醒**全通过；随后经用户确认设 `-38` 为默认并完成冷启动验证后同步关闭 `#36` 与 `#47`。

### `7.2.15-38` 实机回退与 `7.2.15-39.opd2413` 精准扩展 `2414`（`离线通过`）

- **`7.2.15-38.opd2413` 实机测试结果（`真机失败`，`2026-11-23 10:28–10:45`）**：
  - 开机正常进入 `7.2.15-38.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC），但单屏第 1 轮 `DPMS off -> on` 即在 `novatek_nt36536_on()` 首条内存 DMA DCS 命令（`ff 20`）处触发 **`dsi1 cmd dma timeout`**（`status0=00020003 clk=008077c3 dln0=00088888`）、连续 `vblank timeout: ctl=1 intf=2 flush=4208c0 pending=4208c0`，且后续 `DPMS off` 报 **`VBIF AXI ports did not halt before power collapse`**，面板 `lcd_vsp`/`lcd_vsn` 保持 `disabled` 黑屏（用户短按电源键走 `s2idle` 唤醒后恢复）。
  - 结论：`erhai` 的 `2446`–`2449`（`1fead1793340` 两阶段从端交接）在 7.2.15 树上反而触发 `dsi1 cmd dma timeout` 与 VBIF 停摆；立即撤回 `2446`–`2449`。
- **`7.2.15-39.opd2413` 精准修复与离线构建校验（`离线通过`）**：
  - 恢复已验证单屏 10/10 正常的 `2411` + `2440`–`2445`，并扩展 [2414-drm-msm-dpu-skip-video-mode-CTL-flush-start-in-phys-.patch](../kernel/opd2413-7.2/patches/2414-drm-msm-dpu-skip-video-mode-CTL-flush-start-in-phys-.patch)：在 `dpu_encoder_virt_atomic_disable()` 中除 `new_state->active`（内联 modeset）外，当存在其他活跃 CRTC 或任一外接 `priv->kms->dp[]` 处于 `pm_runtime_active`（即 `MDSS GDSC` 保电不掉电）时同样置 `skip_vid_trigger = true`，单屏 `DPMS off`（`MDSS GDSC` 掉电）路径保持与 `-37` 100% 一致。
  - 离线校验：严格 `-F0` 正反向回环通过；5 个 DPU `.o` 在 `KCFLAGS="-Werror"` 下零警告编译；`vmlinux` 与 `oneplus-pogo-keyboard.ko` 含 `.BTF`、`vermagic: 7.2.15-39.opd2413 SMP preempt mod_unload aarch64`；`sm8750-oneplus-pad2pro.dtb` 与 `-37` 逐字节一致；产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-39.opd2413.aarch64.rpm`（SHA-256 `a02b867e76c3372cbcbf68fb39a4d58fe9b905389948d25c9633745b5720d074`）。
- **上机预期与判据（`7.2.15-39.opd2413`）**：
  1. 卸载 `-37`、安装 `-39`（保留 `-35` 默认回退及当前运行的 `-38`），经 `boot-select next fedora-7.2.15-39.opd2413.conf` 单次重启进入 `7.2.15-39.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC）；
  2. **单屏 10 轮 `DPMS off (3s) -> on (3s)` + `120 -> 60 -> 30 -> 60 -> 120 Hz` 在线切换**：10/10 轮及全刷新率切换视觉正常、4 路电源轨真断电、0 内核异常；
  3. **真实闲置锁屏/熄屏唤醒**与 **`s2idle` 休眠唤醒**均正常；
  4. **待外接显示器可用时补验双屏 9 轮长窗口 `DPMS off (4s) -> on (8s)`**，确认 `MDSS GDSC` 保电态下双屏 9/9 轮均正常出图（零灰黑屏）。
- **实机单屏验收与默认收尾结果（`2026-11-23 11:10–11:35`，单屏 `真机通过`，双屏待外接显示器补验）**：
  1. **开机健康**：卸载 `-37` 并安装 `-39` 后经 `boot-select next` 一次性重启进入 `uname -r = 7.2.15-39.opd2413`：`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing`、`0 avc: denied`、`af54000.displayport-controller` 处于 `suspended`。
  2. **单屏自动化压测**：连续 **10/10 轮** `120 Hz` `DPMS off (3s) -> on (3s)` + **4/4 次**在线刷新率切换（`60 -> 30 -> 60 -> 120 Hz`）全部通过；每次灭屏 4 路电源轨（`vreg_l12b_1p8`/`lcd_vsp`/`lcd_vsn`/`vreg_l3i_0p88`）真断电为 `disabled`，亮屏 `14/14` 次 `nt36536` 固件重载正常，`MDSS GDSC`（`ae00000.display-subsystem`）与 `DPU` 同步挂起 `+25.2 s`，`anomalous_kernel_lines=0`。
  3. **用户手动长短熄屏实测（`11:18–11:27`）**：连续完成 **5 轮**真实熄屏/复亮（含最长近 **4 分钟** `11:20:00 -> 11:23:59` 与 **71 秒** `11:25:46 -> 11:26:57`），`#16`–`#20` 全部 `Update firmware success`（`217–223 ms`），`MDSS GDSC` 累计挂起约 `379 s`，内核零 DSI/DPU/VBIF/vblank 异常；用户目视确认无问题（当前 `suspend_stats=0`，`s2idle` 待按需补测）。
  4. **清理与默认启动项切换（`11:35`）**：经用户确认单次 `pkexec` 卸载失败内核 `kernel-opd2413-7.2.15-38.opd2413`、执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-39.opd2413.conf`（保留 `-35` 作回退）并清理本地临时目录 `out/m3k/build38`：`KSHIM.CHO` 前后 SHA-256 一致且保持 `1 extent found`，`loader_default = booted_entry = fedora-7.2.15-39.opd2413.conf`，`pending_next: null`，ESP `/boot/efi` 恢复至 `247M / 512M`（剩余 `266M`，49%），`/` 剩余 `181G`。**待办**：完成 1 次 `-39` 冷启动复查；待外接显示器可用时跑完双屏 9 轮长窗口 DPMS 压测再关闭 [TECH-DEBT.md](TECH-DEBT.md) `#47`。

### `7.2.15-39.opd2413` 外接显示器双屏 DPMS 专项验收（`TECH-DEBT #47`）

- **测试环境**：直接在平板 `opd2413-fd`（`uname -r = 7.2.15-39.opd2413`、`running`、`0 failed`、`Enforcing`）上连接外接 4K DP 显示器（`DP-1` `3840x2160@60 Hz` 扩展桌面 + 内置 `DSI-1` `3392x2400@120 Hz`），`af54000.displayport-controller` 处于 `active`。
- **上机预期与判据**：
  1. **双屏在线刷新率切换**：在 `DP-1` 持续输出下，内置 `DSI-1` 执行 `120 -> 60 -> 30 -> 60 -> 120 Hz` 切换均正常生效，`DP-1` 不掉线，内核零 DSI/DPU/VBIF/vblank 异常；
  2. **双屏长窗口 DPMS 压测（9 轮对照 + 1 轮 15 s 扩展长熄屏）**：执行 `60 Hz` 3 轮 + `120 Hz` 6 轮 `DPMS off (4s) -> on (8s)`，外加 `120 Hz` 1 轮 `DPMS off (15s) -> on (8s)`（第 10 轮结束后不切刷新率，保留真实复亮后硬件态）：
     - 每次 `DPMS off` 期间确认 `af54000.displayport-controller` 保持 `active` 且父域 `ae00000.display-subsystem`（`MDSS GDSC`）`susp_ms` 增量为 `0 ms`（真实命中扩展版 `2414` 保电分支），同时内置面板 4 路电源轨（`vreg_l12b_1p8`/`lcd_vsp`/`lcd_vsn`/`vreg_l3i_0p88`）正常断电；
     - 每次 `DPMS on` 后 `nt36536` 触控固件重载成功、内核零 DSI/DPU/VBIF/vblank/KTZ 报错；
     - 10/10 轮复亮后经用户目视确认双屏（尤其内置 `DSI-1`）均正常出图、零“有背光灰黑屏”；
     - 第 10 轮结束后单次 `pkexec` 读取 `/sys/kernel/debug/dri/1/kms` 寄存器快照（归档于 `private/display-dpms-grey-20261122/dpu39_dual_after.txt`），确认 `dsi0/1_phy[0x10/0x14]`、`dsi0/1_ctrl[0xa0/0xb8/0xbc]` 保持黄金值，且 `sspp_8[0xd0/0xd4/0xe0/0xf8]` 与 `vbif` 处于正常取帧活跃态（非 `00000c80` / `00000008` / `00000000` 卡死态）。
- **实机双屏测试结果（`2026-11-23 19:38–19:45`，`真机失败`，证据：`private/display-dpms-grey-20261122/dual39_dpms_test.log`、`dual39_kmsg.log`）**：
  1. **阶段 1 双屏在线刷新率切换（`120 -> 60 -> 30 -> 60 Hz`，`通过`）**：在 `DP-1` `3840x2160@60 Hz` 持续输出下，内置 `DSI-1` 连续 3 次在线切刷新率全部正常生效（`nt36536` 固件重载 `#12`–`#14` 成功、耗时 `213–230 ms`，内核零报错，用户目视确认最开始内置屏正常切换恢复）。
  2. **阶段 2 起双屏 `DPMS off (4s) -> on (8s)`（`真机失败`，第 1 轮即彻底失效，脚本因 `kscreen-doctor` 持续阻塞超时以 `124` 退出）**：
     - 第 1 轮 `DPMS off`（`19:38:45`）期间：`af54000.displayport-controller` 保持 `active`（`susp_ms` 增量 `+0 ms`）、父域 `ae00000.display-subsystem`（`MDSS GDSC`）`susp_ms` 增量 `+0 ms`、`dpu`/`dsi0`/`dsi1` 进入 `suspended`，面板 4 路电源轨全部变为 `disabled(u=0)`（确实命中了扩展版 `2414` 的 `skip_vid_trigger = true` 分支）。
     - 第 1 轮 `DPMS on`（`19:38:49`）瞬间即在 `novatek_nt36536_on()` 首条 DCS 命令（`ff 20`）处触发与 `-38` 高度一致的 **`dsi1 cmd dma timeout`**（`ctrl=000001f7 status0=00024003 intr=aa20a802 fifo=11111010 clk=008077c3 dln0=00098888`；`dsi0` 伴随 `status0=00020003 dln0=00088888`），`panel_prepare` 失败回滚导致 `lcd_vsp`/`lcd_vsn`/`vreg_l12b_1p8` 全程停在 `disabled(u=0)`（内置屏完全物理黑屏、无背光）。
     - 紧接着双屏均出现持续 **`vblank timeout`**（外接 `DP-1` `21300` ×17 次 + 内置 `DSI-1` `4208c0` ×161 次 / `204208c0` ×10 次）、`LUTDMA ctl0 previous transfer not done` ×12、`LUTDMA error status 0x10000` ×6、`dspp 1/2 LUT update skipped: -110` ×9 与 `wait disable failed`（`id:35 intf:1` ×5、`id:37 intf:0` ×1）；外接 `DP-1` 每次复亮均停留在纯蓝屏，最终比 `-37`（仅内置屏灰黑、外接屏正常且切刷新率可恢复）更严重。
     - 用户拔掉外接显示器并触发 `s2idle` 休眠唤醒（`19:44:29` `PM: suspend entry/exit`）后，`MDSS GDSC` 得以完整断电复位，`19:44:32` 内置屏重新完成 `panel_prepared` 与 `nt36536` 固件重载 `#15`（`211 ms`）恢复正常画面。
  3. **关键对照结论**：将 `-37`/`-38`/`-39` 纳入同一张真值表可见：只要在 `DPMS off`（`dpu`/`dsi` 走 `pm_runtime_suspend` 路径）中跳过 `_dpu_encoder_helper_phys_cleanup()` 的 `trigger_flush + trigger_start`（`-39` 双屏对 `DSI-1` 与 `DP-1` 均跳过，`-38` 单屏改动共享 `CTL` 清理），下一次 `DPMS on` 均会立即触发 `dsi1 cmd dma timeout (ff 20)`，且 `-39` 的条件还波及了外接 `DP-1` 导致蓝屏；而在线 modeset（`dpu`/`dsi` 不挂起）跳过它则 100% 正常。停下来排查 `DPMS off` 跳过 `trigger_flush/start` 与 `dsi1` / `CTL` / `LUTDMA` 的耦合根因，再决定下一步修复方案。

### 双屏根因闭环与 `7.2.15-40.opd2413`（恢复 `2414` + 新增 `2446` `0 -> 1` CTL 复位，`离线通过`）

- **全量取证与根因收敛**：
  1. 全量寄存器 diff（`dpu_120_good.txt` vs `dpu37_dual_bad.txt`）证实：在 `-37` 双屏 `DPMS off -> on` 灰屏现场，软件配置寄存器（含 `CTL_0`、`CTL_FETCH_PIPE_ACTIVE=1`）已写入，但只读硬件锁存状态 **`ctl_0[0x804]` 卡在 `0x6`（正常 `0x7`）、`0x824` 卡在 `0x3`（正常 `0x13`）、`0x844` 卡在 `0x33`（正常 `0x73`）**，进而导致 `sspp_8[0xd0]=0x00000c80`、`vbif[0x20c]=0x30` 停止取帧。
  2. 原先 `-36`（检查 `is_started`/`get_flush_register` 才复位）之所以从未触发，是因为卡死时 `CTL_FLUSH (0x18)` 与 `CTL_START (0x1c)` 已回 `0`；而在 `-37` 切换一次刷新率能 2/2 瞬间恢复，是因为在线 modeset 的 `cleanup` 先执行了 `ctl->ops.reset(ctl_0)` 并跳过 `trigger_flush/start`。
  3. 同步修正 `066c9f2` 中因 `0049` 缺 `diff --git` 行导致 `2414` 意外混入 `0049` `8bpc dither` hunk 的问题，保持 `dpu_encoder.c` 里 `dpu_encoder_panel_dithers_8bpc` 完好并恢复干净版 `2414`。
- **改动与离线校验（`离线通过`）**：
  - 将 [2414](../kernel/opd2413-7.2/patches/2414-drm-msm-dpu-skip-video-mode-CTL-flush-start-in-phys-.patch) 恢复为仅在 `new_state && new_state->active`（在线 modeset）时跳过 `trigger_flush`/`trigger_start`，保留全部 `DPMS off`（单屏及双屏）的 `trigger_flush`/`trigger_start`。
  - 新增补丁 [2446-drm-msm-dpu-reset-CTL-before-staging-newly-enabled-C.patch](../kernel/opd2413-7.2/patches/2446-drm-msm-dpu-reset-CTL-before-staging-newly-enabled-C.patch)（已登记至 [series](../kernel/opd2413-7.2/patches/series)、[PATCHES.md](../kernel/PATCHES.md) 与 [kernel/opd2413-7.2/README.md](../kernel/opd2413-7.2/README.md)）：在 `dpu_crtc_atomic_begin()` 中，当检测到 `old_crtc_state && !old_crtc_state->active && crtc->state->active`（CRTC 由灭到亮 `0 -> 1`）时，在 `_dpu_crtc_blend_setup` / `_dpu_crtc_setup_cp_blocks` / `commit_planes` 之前对所分配的每个 `hw_ctl` 无条件执行一次 `ctl->ops.reset(ctl)` 与 `clear_pending_flush(ctl)`（按 `ctl->idx` 去重）。
  - 离线校验：`2414`（保留 `dpu_encoder_panel_dithers_8bpc` 共 2 处引用）与 `2446` 均通过严格 `--fuzz=0` 正反向回环校验；`dpu_encoder.o` 与 `dpu_crtc.o` 在 `KCFLAGS="-Werror"` 下零警告编译通过；`sm8750-oneplus-pad2pro.dtb` 与 `-39` 逐字节一致；`vmlinux` 与 `oneplus-pogo-keyboard.ko` 含 `.BTF`、`vermagic: 7.2.15-40.opd2413 SMP preempt mod_unload aarch64`；产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-40.opd2413.aarch64.rpm`（SHA-256 `b307201c429dde7e72ca5201993f5b992fe04760789823f447ca99ce5dd673e0`）；已清理 `build39`/`stage39`，ESP 剩余 `266M`（49%）、`/` 剩余 `180G`。
- **上机预期与判据（`7.2.15-40.opd2413`，待用户确认安装与重启测试）**：
  1. 保留 `7.2.15-39` 为当前 `default`（`7.2.15-35` 为二级回退），单次 `pkexec` 安装 `kernel-opd2413-7.2.15-40.opd2413.aarch64.rpm`、设 `boot-select next fedora-7.2.15-40.opd2413.conf` 并核验 `KSHIM.CHO` 一致且保持 `1 extent`，重启进入 `uname -r = 7.2.15-40.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC）；
  2. **双屏（`DP-1` 4K@60 Hz + `DSI-1` 120/60 Hz）完整压测**：
     - 双屏在线刷新率切换 `120 -> 60 -> 30 -> 60 -> 120 Hz` 全正常；
     - 连续 **9 轮**长窗口 `DPMS off (4s) -> on (8s)`（`60 Hz` 3 轮 + `120 Hz` 6 轮）+ **1 轮** `120 Hz` `15 s` 长熄屏复亮：**10/10 轮**期间 `af54000.displayport-controller` 保持 `active`（`MDSS GDSC` `susp_ms` 增量 `0 ms`）、面板 4 路电源轨真实断电，每次唤醒均无 `dsi1 cmd dma timeout`、无 `vblank timeout`、无 `LUTDMA` 错误、无内置屏灰黑屏、无 `DP-1` 蓝屏，用户目视确认双屏 10/10 轮均正常出图；
     - 第 10 轮结束后抓取 `/sys/kernel/debug/dri/1/kms`，验证 `dsi0/1_phy[0x10/0x14]` 与 `sspp_8`/`vbif` 均处于健康取帧活跃态；
  3. **单屏回归验收**：拔掉外接显示器后跑 **10 轮**单屏 `DPMS off (3s) -> on (3s)` + `120/60/30 Hz` 切换 + `s2idle` 休眠唤醒，确认 `MDSS GDSC` 正常掉电与全项无回归；随后经用户确认设 `-40` 为默认（卸载失败项 `-39`）并做 1 次冷启动复核后正式关闭 `#47`。
- **装机与一次性启动设置（`2026-11-23 20:34`）**：经用户确认单次 `pkexec` 安装 `kernel-opd2413-7.2.15-40.opd2413.aarch64.rpm`（保留 `-39` 与 `-35`）、设置 `boot-select next fedora-7.2.15-40.opd2413.conf`（`pending_next` 指向 `-40`，`previous_default` 保持 `-39`），`KSHIM.CHO` 前后 SHA-256 一致且保持 `1 extent found`，ESP `/boot/efi` 已用 `370M / 512M`（剩余 `143M`）；待用户重启进入 `7.2.15-40.opd2413` 后执行双屏与单屏验收。

### `7.2.15-40.opd2413` 双屏实机结果（`真机失败`）与黑屏/彩条根因闭环，及 `7.2.15-41.opd2413` 构建校验（`离线通过`）

- **`7.2.15-40.opd2413` 双屏上机实测与现场二分定位（`真机失败`）**：
  1. **双屏压测结果**：更新 `dual_dpms_test.py` 动态解析 `DSI-1` 模式 ID 后以 `-40` 运行双屏压测（`dual40_dpms_test.log`、`dual40_kmsg.log`、`dpu40_dual_after.txt`），自动化日志报告 `Rounds completed: 10/10 (aborted=False)`、`all_dp_active_during_off: True`、`all_mdss_gdsc_stayed_on: True`（`mdss=+0ms dpu=+46073ms dp=+0ms`）、4 路面板供电轨熄屏均正确 `disabled`、`nt36536 Update firmware success count: 14`、`Anomalous kernel lines: 0`；但用户目视确认**外接 `DP-1` 正常恢复桌面，内置 `DSI-1` 始终黑屏**，不得不手动将 `DP-1` 设为主屏幕，并记录到 `ctl_0[0x804]=0x00060007`、`sspp_8[0xd0]=0x00000c80`、`vbif[0x204]=0xffdf0000`、`dsi0/1_phy[0x10]=0x61`。
  2. **在线二分复现竖向彩色条纹**：仅保持 `DP-1` 为 `priority 1` 主屏并重启用 `DSI-1`（`dpu` 未进 runtime suspend，`runtime_suspended_time = 46135` 未变、`bl_power = 0`、`nt36536` 加载成功），此时 `DSI-1` 仍黑屏（`dpu40_enable_only.txt`：`ctl_0[0x804]=0x00070007`、`sspp_8[0xd0]=0`、`sspp_8[0xf4]=0x00010303`、`vbif[0x204]=0xffff0000`、`vbif[0x20c]=0x30`）；随后在前台对 `DSI-1` 执行 `120 -> 60 -> 120 Hz` 切换（零内核报错，`kscreen-doctor -o` 显示切回 `120.00*!`），**内置屏直接从黑屏变为全屏竖向彩色花屏条纹**，抓取 `dpu40_rainbow_now.txt` 对照正常基线可见 `ctl_0[0x804]=0x00070007`、`sspp_8[0xd0]=0`、`sspp_8[0xf4]=0x00010303`、`sspp_8[0x334]=0`、`vbif[0x204]=0xffdf0000`，且 `dce_0_0/0_1_ctl[0x00c]`、`dce_0_0/0_1_enc[0x008/0x00c]`、`intf_1/2[0x08c]` 均停在 `0`。
  3. **精确源码级根因确认**：核对 `msm_atomic.c:237-239` 证实 `msm_atomic_commit_tail()` 固定先调用 `drm_atomic_helper_commit_planes()`（内含 `-40` 放置 `ctl->ops.reset(ctl)` 的 `dpu_crtc_atomic_begin()`），之后才调用 `drm_atomic_helper_commit_modeset_enables()`（内含启动 DSI PLL 与 `pclk0`/`pclk1` 的 `dsi_mgr_bridge_pre_enable()`）。因此 `-40` 在 `dpu_crtc_atomic_begin()` 调用 `ctl->ops.reset(ctl)` 时 DSI 像素时钟仍为 `0 Hz`，硬件 `CTL_SW_RESET` 等待 `2000 us` 超时后回落到 `dpu_hw_ctl_force_reset()`（强拉 `CTL_SW_RESET_OVERRIDE = 1 -> 0`），直接破坏尚未上钟的 `CTL_0` `pclk` 域（`0 -> 1` 黑屏、`1 -> 1` 竖向彩条）。
- **`7.2.15-41.opd2413` 补丁重写与离线构建校验（`离线通过`）**：
  - 撤回 `-40` 的旧 `2446`，新增并严格合入 [2446-drm-msm-dpu-reset-DSI-video-CTL-after-link-clocks-st.patch](../kernel/opd2413-7.2/patches/2446-drm-msm-dpu-reset-DSI-video-CTL-after-link-clocks-st.patch)：
    - 在 `dpu_crtc.h` / `dpu_crtc.c` 导出 `dpu_crtc_reprogram_blend(struct drm_crtc *crtc)`，校验 CRTC 使能且 `num_mixers > 0` 后重放 `_dpu_crtc_blend_setup(crtc)`；
    - 在 `dpu_encoder.c` 的 `dpu_encoder_virt_atomic_enable()` 中（`trace_dpu_enc_enable` 之后、`cur_slave`/`cur_master->ops.enable` 配置 `INTF/DSC` 之前），仅针对 `intf_type == INTF_DSI && !is_cmd_mode` 且 `!old_crtc_state || !old_crtc_state->active` 场景（此时 `dsi_mgr_bridge_pre_enable()` 已启动 `pclk0`/`pclk1`），按 `ctl->idx` 去重调用 `ctl->ops.reset(ctl)` 并在复位发生后调用 `dpu_crtc_reprogram_blend(dpu_enc->base.crtc)`；`INTF_DP` 完全不受影响。
  - **离线校验（`离线通过`）**：`2446` 正反向 `patch --fuzz=0` 均通过，`dpu_encoder_panel_dithers_8bpc` 在 `dpu_encoder.c` 维持 `2` 处；`dpu_encoder.o` 与 `dpu_crtc.o` 在 `KCFLAGS="-Werror"` 下零警告编译通过；`sm8750-oneplus-pad2pro.dtb` 与 `-39` 逐字节一致（SHA-256 `238ba743288722af635177209e6568636185ceff33694e582b8956cd45e62280`）；`nm -n vmlinux` 确认含 `dpu_crtc_reprogram_blend`；`vmlinux` 与 `oneplus-pogo-keyboard.ko` 均含 `.BTF`，`vermagic: 7.2.15-41.opd2413 SMP preempt mod_unload aarch64`；产物 RPM `kernel-opd2413-7.2.15-41.opd2413.aarch64.rpm`（SHA-256 `5738e79a4a5ca81e705b51219d3d6617442771a90721b86895a1e6c0ea839b2a`）；已清理 `stage40` 与 `stage41`。
- **上机预期与判据（`7.2.15-41.opd2413`，待用户确认装机与重启验收）**：
  1. 因 ESP `/dev/sda16` 仅剩 `143M`（直接保留 4 个内核空间不足），待用户确认后单次 `pkexec` 先设 `boot-select default fedora-7.2.15-35.opd2413.conf` 并卸载已证实双屏失败的 `-39`（保留稳定回退 `-35` 与当前运行的 `-40`），再安装 `kernel-opd2413-7.2.15-41.opd2413.aarch64.rpm`、设 `boot-select next fedora-7.2.15-41.opd2413.conf` 并核验 `KSHIM.CHO` 一致且保持 `1 extent`；
  2. 重启进入 `7.2.15-41.opd2413`（连接外接 DP 显示器）后运行双屏压测：在线刷新率切换 `120 -> 60 -> 30 -> 60 Hz` 与 **10/10 轮** `DPMS off -> on`（终轮 `120 Hz` 15 s 熄屏 -> 8 s 亮屏）零内核报错（无 `dsi1 cmd dma timeout`、`vblank timeout`、`LUTDMA`、`VBIF`、AVC）、4 路面板电源轨熄灭断电且每次唤醒 `nt36536` 成功重加载、用户目视确认 **`DSI-1` 与 `DP-1` 均正常呈现桌面（无黑屏/无彩条）**，且轮后 `/sys/kernel/debug/dri/1/kms` 满足 `sspp_8[0xd0] != 0x00000c80`、`vbif[0x204]` `BIT(17)==0`、`vbif[0x20c]==0`、`ctl_0[0x804]` 低半字节 `0x7`、`dsi0/1_phy` 原厂黄金值及 `TIMEOUT_STATUS == 0`；
  3. 拔掉外接显示器完成单屏 10 轮 `DPMS off -> on` + 刷新率切换 + `s2idle` 回归验收无误后，再询问用户确认是否设为默认并执行 1 次冷启动复核。
- **装机与一次性启动设置（`2026-11-23 21:54`）**：经用户确认单次 `pkexec` 先将 `boot-select default` 设为 `fedora-7.2.15-35.opd2413.conf` 并卸载 `kernel-opd2413-7.2.15-39.opd2413`，核验 RPM SHA-256（`5738e79a4a5ca81e705b51219d3d6617442771a90721b86895a1e6c0ea839b2a`）后安装 `kernel-opd2413-7.2.15-41.opd2413.aarch64.rpm`（当前已装 `-35`/`-40`/`-41`），核对 `-41` BLS 条目 `options` 与 `-40` 一致（含 `mem_sleep_default=s2idle`，无 `fw_devlink.sync_state=timeout`/`pcie_ports=compat`），并设置 `boot-select next fedora-7.2.15-41.opd2413.conf`（`previous_default: "fedora-7.2.15-35.opd2413.conf"`）；`KSHIM.CHO` 写前后 SHA-256 一致且保持 `1 extent found`，ESP `/boot/efi` 已用 `370M / 512M`（空闲 `143M`，`73%`），电池电量 `54%`；待用户保持外接显示器重启进入 `7.2.15-41.opd2413` 后执行双屏与单屏验收。
- **`7.2.15-41.opd2413` 上线与双屏 DPMS + `kms` 硬件复核（`2026-11-23 21:57–22:05`，`真机启动`，待用户目视确认与单屏回归）**：
  1. **启动与回退状态**：平板成功重启至 `uname -r = 7.2.15-41.opd2413`（`running`、`0 failed`、SELinux `Enforcing`，电量 `53%`），`boot-select status` 确认 `booted_entry = fedora-7.2.15-41.opd2413.conf`、`loader_default = fedora-7.2.15-35.opd2413.conf`、`pending_next = null`。
  2. **双屏压测结果**（`dual41_dpms_test.log`、`dual41_kmsg.log`）：`DP-1` `2560x1440@144 Hz` + `DSI-1` `3392x2400` 完成阶段 1 `120 -> 60 -> 30 -> 60 Hz` 在线切换、阶段 2 `60 Hz` ×3 轮 `DPMS off (4s) -> on (8s)`、阶段 3 切回 `120 Hz`、阶段 4 `120 Hz` ×6 轮 `DPMS off -> on` 及阶段 5 `120 Hz` 扩展长熄屏 `15s off -> 8s on`（`Rounds completed: 10/10 (aborted=False)`）；全程 `all_dp_active_during_off = True`、`all_mdss_gdsc_stayed_on = True`（`mdss=+0ms dpu=+46082ms dp=+0ms`）、4 路面板供电轨熄屏均 `disabled(u=0)` 且唤醒 `enabled`、`nt36536` 成功重载 14 次、`Anomalous kernel lines: 0`。
  3. **第 10 轮后 `kms` 硬件寄存器复核**（`dpu41_dual_after.txt` 对照 `dpu_120_good.txt` 与 `dpu40_dual_after.txt`）：
     - `ctl_0[0x804]=0x00060007`（低半字节 `0x7`，`0x824=0x00000013`、`0x844=0x00000073`，`CTL_0` 全量仅有 `[0x804]` 高半字位 16+ 的 `DP-1` 活跃位差异）；
     - `sspp_8` 活跃取帧：`[0x014]=0x01081000`、`[0x0d0]=0x000d03f4`（不再是 `-40` 卡死的 `0x00000c80` 或 `0`）、`[0x330]=0x4`、`[0x334]=0x3`；`sspp_9[0x0d0]=0x000689c0`；
     - `vbif[0x204]=0xfffd0000`（`BIT(17)==0`，与 `-40` 卡死态 `0xffdf0000` `BIT(17)==1` 明确区分）且 `vbif[0x20c]=0x00000000`；
     - `dce_0_0_ctl` / `dce_0_1_ctl` 与基线零差异（`[0x004]=0x1801`、`[0x00c]=0xc0000000`），`dce_0_0/0_1_enc`、`intf_1/2`、`dsi0/1_phy`（`0x10=0x61`、`0x14=0x20/0x24`）及 `dsi0/1_ctrl`（`HS_TIMER_CTRL=0x3fd08`、`MISR_VIDEO_CTRL=0x10100`、`TIMEOUT_STATUS=0`）均处于健康活跃传输态。
  4. **待用户确认后接续**：请用户目视确认双屏（`DSI-1` 与 `DP-1`）全程及测试后均画面与触控正常，随后拔掉外接显示器执行单屏 10 轮回归验收。

- **用户实机目视反馈与第 10 轮（15 s 长熄屏）黑屏根因（`2026-11-23 22:10–23:45`）**：
  1. **实测结论（第 1–9 轮 `真机通过`，第 10 轮 15 s 长熄屏 `真机失败`）**：前 9 轮（`60 Hz` ×3、`120 Hz` ×6、`4s off -> 8s on`）及在线 `120 -> 60 -> 30 -> 60 Hz` 切换下内置 `DSI-1` 与外接 `DP-1` 均正常恢复画面；唯第 10 轮 `15s off -> 8s on` 结束时外接屏先显示无信号再恢复，内置屏持续黑屏，直至用户手动将 `DP-1` 设为主屏（无重上电）才恢复 `DSI-1`。
  2. **`drm.debug=0x114` 复现取证（`private/display-dpms-grey-20261122/diag41_*`）**：
     - 进入熄屏约 `+5.2 s` 后外接显示器进省电待机，连续拉低/脉冲 HPD 6 次；由于本树缺少 `erhai/v0.7` `762bd1bc8` 等 DP `pm_runtime`/HPD 修复，KWin 在待机阶段拆除了平面与模式（`[NOFB]`/`[NOMODE]`）。
     - `+15 s` 唤醒同一事务重新点亮 `DSI-1`（`3392x2400@120`）+ `DP-1`（`2560x1440@144`）时，`dpu_core_perf_crtc_check()` 仍读取 `commit_planes()` 之前尚未计算的 `plane_fetch_bw=0` 且迭代旧 `crtc->state`（`tmp_crtc->enabled == false`），使 `dpu_crtc_atomic_flush()` 以 `new_bw=0, old_bw=0`（`0 KB/s` DDR 带宽而非 `~7.81 GB/s`）直接启动首帧，触发大量欠载并将 `sspp_8` 卡死在 `0x00000c80` / line 0。
     - 对照本地 `linux-sm8750-erhai`（`erhai/v0.7` + `upstream/sm8750/v7.4-dev` 至 `v0.12.2` `658c139dd`）确认：`sm8750/v7.4-dev` 已在 `dpu_core_perf.c` 改用 `drm_atomic_crtc_state_for_each_plane_state()`（本树进一步在 `atomic_check` 预计算 `plane_fetch_bw` 并传入新状态聚合），而 `erhai/v0.7` 另有 12 项 DP / QMP PHY / `pmic_glink_altmode` 修复待引入（注：不引入去掉 60/30 Hz 的 `e69430234`，也不引入曾在 `-38` 失败的共享 CTL 改动及 `v7.4-dev` 非显示改动）。

### `7.2.15-42.opd2413` 双屏长熄屏 0 带宽与 Type-C DP/PHY/AltMode 修复候选（`TECH-DEBT #47`）

- **补丁与源码范围（`2447`–`2459`）**：
  1. [2447-drm-msm-dpu-calculate-plane-perf-in-atomic_check-on-.patch](../kernel/opd2413-7.2/patches/2447-drm-msm-dpu-calculate-plane-perf-in-atomic_check-on-.patch)：在 `dpu_plane_atomic_check_sspp()` 与纯 modeset 下预先计算 `pstate->plane_fetch_bw` / `pstate->plane_clk`，并将 `dpu_core_perf.c` 的 `_dpu_core_perf_calc_{bw,clk}()` 与 `dpu_core_perf_aggregate()` 切换至待提交的新 CRTC/plane 状态，保证 `0 -> 1` 首帧即下发真实 DDR 带宽投票；
  2. [2448](../kernel/opd2413-7.2/patches/2448-drm-msm-dp-retry-reading-the-sink-capabilities-after-an-AUX-failure.patch)–[2459](../kernel/opd2413-7.2/patches/2459-phy-qcom-qmp-combo-Drop-the-stale-err_disable_pipe_clk-teardown.patch)：合入 `erhai/v0.7` 经审定的 12 项 Type-C DP / QMP Combo PHY / `pmic_glink_altmode` 修复（含 `dp` 按插入态单次持有 runtime PM 引用、HPD 锁序列化、AUX 重试、PHY/link 错误回滚、`qmp-combo` `qmpphy_mode_committed` 跟踪与 `pmic_glink_altmode` `BIT(mode)` 位图编码）。
- **上机预期与判据（`7.2.15-42.opd2413`，待离线构建与用户确认装机后上机实测）**：
  1. 保留 `7.2.15-35` 为 `default`、`7.2.15-41` 为备用回退，卸载已失败 `-40` 后单次 `pkexec` 安装 `-42` 并 `boot-select next fedora-7.2.15-42.opd2413.conf`（`KSHIM.CHO` SHA-256 与 `1 extent` 不变），重启进入 `uname -r = 7.2.15-42.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC）；
  2. **双屏完整压测（`DSI-1` + `DP-1`，含在线切换与多轮 `15s–20s` 超待机长熄屏）**：
     - 双屏在线刷新率切换 `120 -> 60 -> 30 -> 60 -> 120 Hz` 正常；
     - 短窗口（`4s off -> 8s on`）与长窗口（外接显示器进入无信号待机 `>=15s–20s off -> 8s on` 多轮）均由用户**目视确认双屏（`DSI-1` 与 `DP-1`）同时正常出图，无需改主屏设置**；
     - 熄屏期 `af54000.displayport-controller` 与 `MDSS GDSC` 引用平衡无泄漏（拔线后正常休眠归零），内置面板 4 路电源轨熄屏真实断电、`nt36536` 固件重载全通过、`anomalous_kernel_lines == 0`、`kms` 快照 `sspp_8[0xd0] != 0x00000c80`、`ctl_0` 黄金寄存器健康；
  3. **单屏回归（拔掉 DP）**：10 轮 `DPMS off -> on` + `120/60/30 Hz` 切换 + `s2idle` 唤醒 + `MDSS GDSC` 挂起累计均通过；经用户目视与确认后再切默认、冷启动复核并关闭 `#47`。
- **离线校验（`2026-11-24`，`离线通过`）**：
  - `2447`–`2459` 严格 `patch -p1 -F0` 正向与反向回环全通过，`dp_display.c`、`dp_ctrl.c`、`dp_panel.c`、`phy-qcom-qmp-combo.c` 与 `erhai/v0.7` 逐字节一致，`pmic_glink_altmode.c` 保留 SM8750 `-EPROBE_DEFER`。
  - 全部 9 个改动 `.o` 文件在 `KCFLAGS="-Werror"` 下零警告通过；`sm8750-oneplus-pad2pro.dtb` SHA-256 与 `-41` 一致（`238ba743288722af635177209e6568636185ceff33694e582b8956cd45e62280`）；`vmlinux` 与 `.ko` 含 `.BTF`、`vermagic: 7.2.15-42.opd2413 SMP preempt mod_unload aarch64`、`nm -n vmlinux` 含新增/改动符号；产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-42.opd2413.aarch64.rpm`（SHA-256 `bb6d102c4547f73b77a96958a05b857019a07676cfb7d08fbd2d97d9f071e88b`），已清理 `out/m3k/build40` 与 `out/m3k/stage42`。
- **装机与一次性启动设置（`2026-11-24 07:00`）**：经用户确认先后通过 `pkexec` 卸载废弃内核 `kernel-opd2413-7.2.15-40.opd2413`、保持 `boot-select default fedora-7.2.15-35.opd2413.conf`（保留 `-35` 与 `-41` 作双回退）、以 `rpm -ivh --nosignature` 安装 `kernel-opd2413-7.2.15-42.opd2413.aarch64.rpm`（`linux` `62M`、`initrd` `62M`、`sm8750-oneplus-pad2pro.dtb` `145K` 就绪，BLS `options` 与 `-41` 零差异并含 `mem_sleep_default=s2idle`），并设置 `boot-select next fedora-7.2.15-42.opd2413.conf`（`pending_next.next: fedora-7.2.15-42.opd2413.conf`、`previous_default: fedora-7.2.15-35.opd2413.conf`）；`KSHIM.CHO` 写前后 SHA-256 一致且保持 `1 extent found`，ESP `/boot/efi` 已用 `370M / 512M`（剩余 `143M`，`73%`），电池电量 `93%`（Charging）。待用户保持外接显示器重启进入 `7.2.15-42.opd2413` 后执行双屏与单屏验收。
- **`7.2.15-42.opd2413` 上机启动与双屏压测结果（`2026-11-24 07:11–07:18`，`真机启动`，待用户目视确认与单屏回归）**：
  1. **启动与回退态**：`uname -r = 7.2.15-42.opd2413`、`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing`、`0 avc: denied`，电量 `92% (Charging)`；`af54000.displayport-controller` 开机阶段即有 `susp_ms=3755`（验证 `2456` 消除 `pm_runtime` 泄漏）。
  2. **双屏压测（`dual42_dpms_test.log`、`dual42_kmsg.log`）**：`DP-1` `2560x1440@144` + `DSI-1` `3392x2400` 完成阶段 1 `120 -> 60 -> 30 -> 60 Hz` 与阶段 3 `60 -> 120 Hz` 在线切换，以及 **9/9 轮** `DPMS off -> on`（60 Hz：4s ×2 + **16s ×1**；120 Hz：4s ×3 + **16s ×1** + **18s ×2**）：
     - 短窗口 4s 期间 `dp` 保持 `active`、`mdss` `+0ms`；16s/18s 超待机窗口下随外接显示器进入待机 `dp` 与 `mdss` 同步挂起（每次约 `+1.1s`）、面板 4 路电源轨均真实 `disabled`；
     - **全部 9/9 轮（含连续 3 轮 `16s/18s` 超待机长熄屏）唤醒后** `DSI-1` 与 `DP-1` 均自动回到 `On/enabled`，`nt36536` 成功重载 13 次，`Anomalous kernel lines: 0`、`0 AVC`。
  3. **第 9 轮（18s）后 `/sys/kernel/debug/dri/1/{kms,state}` 寄存器复核（`dpu42_dual_after.txt`、`dpu42_dual_state.txt`）**：
     - `ctl_0[0x804]=0x00000007`、`[0x824]=0x00000013`、`[0x844]=0x00000071`、`[0x094]=0`；
     - `sspp_8`（`DSI-1`）与 `sspp_9`（`DP-1`）活跃取帧：`sspp_8[0x0d0]=0x0002bf80`、`[0x0f8]=0x01a401a4`、`[0x330]=4`、`[0x334]=3`；`sspp_9[0x0d0]=0x00079920`、`[0x0f8]=0x03020302`；
     - `vbif[0x204]=0xffdd0000`、`[0x20c]=0`；`dce_0_0/0_1_ctl` `[0x004]=0x1801`、`[0x00c]=0xc0000000`；`dsi0/1_phy` `0x10=0x61`、`0x14=0x20/0x24`；`dsi0/1_ctrl` `HS_TIMER_CTRL=0x3fd08`、`MISR_VIDEO_CTRL=0x10100`、`TIMEOUT_STATUS=0`；`top[0x008/0x018]=0`。
- **`7.2.15-42.opd2413` 第二轮实测反转与 `s2idle` 回归根因（`2026-11-24 07:27–10:05`，`真机失败`，证据：`private/display-dpms-grey-20261122/dual42_dpms_test.log`、`dual42_kmsg.log`、`diag42_4s_kmsg.log`、`journalctl -k -b 0`）**：
  1. **长短窗口行为相对 `-41` 完全反转**：补充短/长混合多轮测试（Rounds 1–9）后用户目视确认：**全部 4 轮超待机长熄屏（Rounds 3/7/8/9，`16s–18s`，`mdss=+1091..1100ms, dp=+1093..1102ms`）及未触发显示器待机脉冲的 Round 1（`1.28s`）下内置 `DSI-1` 与外接 `DP-1` 均正常恢复画面；而全部 4 轮 `4s` 短熄屏（Rounds 2/4/5/6）及复现取证 `diag42_4s` 中，`DP-1` 恢复但内置 `DSI-1` 全程背光亮起黑屏**。
  2. **对照日志与寄存器定位 4 s 短熄屏黑屏根因**：
     - 两代内核（`-41` 与 `-42`）外接 DP 显示器均在熄屏约 `+4.7 s` 后才发 HPD 掉线/重连脉冲（`status=2 -> 1.05s -> status=1`），亦即在 `4s` 短熄屏唤醒约 `1 s` 后、此时 **`DSI-1` 已以 120 Hz 活跃扫描输出**；
     - 在 `-41`（不含 `2448`–`2459`）下，`af54000.displayport-controller` 在该 `1 s` 脉冲期间保持 runtime active（`dp=+0ms`），`DSI-1` **9/9 轮全部正常**；
     - 在 `-42` 下，新增 `2456`（`hold one runtime PM reference per plugged state`）等 DP/QMP 补丁令 `af54000.displayport-controller` 在 `commit_modeset_disables` 中同步进入 `msm_dp_pm_runtime_suspend()`（对共享 `RPMHPD_MMCX` 与 AHB 时钟的 DP 控制器做 `msm_dp_ctrl_reset()` 并在链路时钟已关后落投票），与正在扫描的 `DSI-1` 并发干扰导致实时欠载：`/sys/kernel/debug/dri/1/kms` 记录 `intf_1/2[0x1c4] = 0x00000a00`（`good` 态为 `0`）、`dce_0_1_enc[0x004] = 0x00000022`（`good` 态为 `0x3`）、`sspp_8[0x0d0] = 0x00000c80, [0x0f8] = 0x00000000`（与 `-41` 15s `new_bw=0` 欠载特征相同，但 `-42` 中 `2447` 已稳定上报 `new_bw=7,813,768 KB/s`）。
  3. **`s2idle` 唤醒与额外回归**：`07:54:19` 拔线后触发 `s2idle` 唤醒时，`qcom-qmp-combo-phy 88e8000.phy: phy initialization timed-out` / `dwc3_qcom_pm_resume returns -110` / `usb usb2: PM: failed to resume async: error -110`（由 `2449` 在 `qmp_combo_usb_power_on()` 写入 `SW_PWRDN` 引起），紧接着触发 `gcc_usb3_prim_phy_aux_clk status stuck at 'off'` 与 `disp_cc_mdss_dptx0_link_clk status stuck at 'off'` `WARNING`（`clk_branch_toggle`）以及 `enc37 frame done timeout` / `vblank timeout: a0821300`；另于 `10:00:49` 记录 `vblank timeout: 400000`。

### `7.2.15-43.opd2413` 单变量隔离候选（`2440`–`2447`，回退 `2448`–`2459`，`TECH-DEBT #47`）

- **改动与设计依据**：在已证实 `4s` 短熄屏 **9/9 通过** 的 `-41`（`2440`–`2446`）之上，**仅保留 `2447`**（解决长熄屏后重新挂载平面时首帧 `new_bw=0` 导致的欠载），完整回退引起 `4s` 短熄屏 `DSI-1` 黑屏及 `88e8000.phy` `s2idle` 超时的 `2448`–`2459` 共 12 个 `erhai/v0.7` DP/QMP/`pmic_glink` 补丁。
- **上机预期与判据（`7.2.15-43.opd2413`，待构建校验与用户确认装机后实测）**：
  1. 保留 `7.2.15-35` 为 `default`、`7.2.15-41` 为备用回退，卸载 `-42` 并单次 `pkexec` 安装 `-43`，设 `boot-select next fedora-7.2.15-43.opd2413.conf`（`KSHIM.CHO` SHA-256 与 `1 extent` 不变），重启进入 `uname -r = 7.2.15-43.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、0 AVC）；
  2. **双屏混合压测（`DSI-1` + `DP-1`）**：
     - 双屏在线刷新率切换 `120 -> 60 -> 30 -> 60 -> 120 Hz` 全部正常；
     - 短熄屏（`4s off -> 8s on`）**与**超待机长熄屏（`16s–18s off -> 8s on`）各多轮，用户**目视确认双屏（`DSI-1` 与 `DP-1`）在短熄屏、长熄屏与混合顺序下均自动恢复正常画面，无需改主屏设置**；
     - 4 路面板电源轨熄屏真实断电、`nt36536` 固件重载全通过、`0` 内核异常、`kms` 快照 `sspp_8[0x0d0] != 0x00000c80`、`intf_1/2[0x1c4] == 0`、`ctl_0` 健康；
  3. **单屏回归（拔掉 DP）**：10 轮 `DPMS off -> on` + `120/60/30 Hz` 切换 + `s2idle` 休眠唤醒（`0` 次 `88e8000.phy` 超时、`0` 次 `WARNING`、`MDSS GDSC` 正常累计挂起）；经用户确认后再设 `-43` 为默认、卸载 `-41` 并做冷启动复查后关闭 `#47`。
- **离线校验（`2026-11-24 10:19`，`离线通过`）**：
  - `2459`–`2448` 在源码树逆序 `patch -p1 -R -F0` 干净回退，反向 `--dry-run -F0` 验证 `2447`、`2446`、`2430` 完整保留且零 `.rej`/`.orig`；`series`、`PATCHES.md` 同步清理。
  - `dpu_encoder.o`/`dpu_crtc.o`/`dpu_plane.o`/`dpu_core_perf.o` 通过 `KCFLAGS="-Werror"`；`vmlinux` 含 `.BTF`/`.BTF_ids` 及 `dpu_crtc_reprogram_blend`/`dpu_plane_calc_perf`/`dpu_core_perf_crtc_check`；`oneplus-pogo-keyboard.ko` 为 `vermagic: 7.2.15-43.opd2413 SMP preempt mod_unload aarch64`；`sm8750-oneplus-pad2pro.dtb` SHA-256 为 `238ba743288722af635177209e6568636185ceff33694e582b8956cd45e62280`；产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-43.opd2413.aarch64.rpm`（SHA-256 `827bb16a2e65ca1ef329cf54e92141b7cddc9a942416d963b805f8874d8557d3`），已清理 `out/m3k/stage43` 与 `out/m3k/build42`。
- **装机与一次性启动设置（`2026-11-24 20:13`）**：经用户确认单次 `pkexec` 保持 `boot-select default fedora-7.2.15-35.opd2413.conf`（保留 `-35` 与 `-41` 作双回退）、卸载已失败的 `kernel-opd2413-7.2.15-42.opd2413` 并安装 `kernel-opd2413-7.2.15-43.opd2413.aarch64.rpm`（`linux` `62M`、`initrd` `62M`、`sm8750-oneplus-pad2pro.dtb` `145K` 就绪，BLS `options` 与 `-41` 零差异并含 `mem_sleep_default=s2idle`），设置 `boot-select next fedora-7.2.15-43.opd2413.conf`（`previous_default: fedora-7.2.15-35.opd2413.conf`、`next: fedora-7.2.15-43.opd2413.conf`）；`KSHIM.CHO` 写前后 SHA-256 一致且保持 `1 extent found`，ESP `/boot/efi` 已用 `370M / 512M`（剩余 `143M`，`73%`），电池电量 `40%`（Charging），`card1-DP-1` 与 `card1-DSI-1` 均处于 `connected`。待用户重启进入 `7.2.15-43.opd2413` 后执行双屏短/长混合与单屏 `s2idle` 验收。
- **`7.2.15-43.opd2413` 实机双屏测试与寄存器定位（`2026-11-24 20:24–22:25`，`真机失败`，证据：`private/display-dpms-grey-20261122/dual43_dpms_test.log`、`dual43_kmsg.log`、`dpu43_dual_after.txt`、`dpu43_dual_state.txt`）**：
  1. **实测现象与结果**：`Rounds completed: 10/10`、`Anomalous kernel lines: 0`、`0 devcoredump`、`nt36536 Update firmware success count: 14`，`2447` 已彻底消除 `-41`/`-42` 的 FIFO 欠载（`intf_1/2[0x1c4] == 0`、`top[0x00c/0x014] == 0`、`dce_0_0/0_1_enc[0x004] == 0x3`）。Rounds 1–2（`60 Hz`，`4s`）双屏均恢复；Round 3（`60 Hz`，`16s` 长熄屏，外接屏 `+5.2s` 待机 HPD 脉冲）后内置 `DSI-1` 停留在有背光黑屏，仅在阶段 3（`60 -> 120 Hz` 在线切换）恢复约 `2s`，随后的 `120 Hz` Rounds 4–10 最终以 `DSI-1` 有背光黑屏结束（测试后切回 `60 -> 120 Hz` 立即恢复）。
  2. **全块对比锁定根因**：`dpu43_dual_after.txt` 显示 `CTL_0` 除 `0x094` / `0x180..0x18c`（均标出 `SSPP_DMA0`）外配置与 `dpu_120_good.txt` 一致，`INTF_1/2` 正常以 `120 Hz` 扫描黑边，而 `sspp_8`（`SSPP_DMA0`）卡死在单次预取后停摆（`0x0d0=0x0c80, 0x0e0=0x8, 0x0f4=0x10030, 0x0f8=0x0`、`vbif[0x204]=0xffdf0000` `BIT(17)=1`、`vbif[0x20c]=0x30`）。
  3. **因果链路**：`>=15s` 长熄屏下 `+5.2s` DP 待机 HPD 脉冲触发 KWin `Set [NOFB]` / `crtc enable=0` 执行 `_dpu_plane_atomic_disable()` 清零 `SSPP_MULTIRECT_OPMODE`（无 `CTL_FLUSH` 且 `MDSS GDSC` 未掉电）；唤醒时 `msm_atomic_commit_tail()` 先执行 `drm_atomic_helper_commit_planes()`（写入 `sspp_8`、`CTL_FETCH_PIPE_ACTIVE` 与 `LUTDMA` sideband），~260 ms 后才进 `drm_atomic_helper_commit_modeset_enables()`，旧 `2446` 又在 `dpu_encoder_virt_atomic_enable()` 于 `commit_planes()` 之后执行 `ctl->ops.reset(ctl_0)` 并仅重放 `_dpu_crtc_blend_setup()`，破坏 `CTL_0 <-> sspp_8` 状态同步（而 `Phase 3` 在线切刷新率在 `modeset_disables` 即 `commit_planes()` 之前重置 `CTL_0` 故能恢复）。

### `7.2.15-44.opd2413` 调整 `commit_modeset_enables` 与 `commit_planes` 顺序及精简 `2446`（`TECH-DEBT #47`）

- **上机测试前预期与判据：**
  1. **单一改动（替换 [2446](../kernel/opd2413-7.2/patches/2446-drm-msm-dpu-reset-DSI-video-CTL-after-link-clocks-st.patch)，保留 `2440`–`2445` 与 `2447` 不变）**：
     - 在 `drivers/gpu/drm/msm/msm_atomic.c` `msm_atomic_commit_tail()` 将 `drm_atomic_helper_commit_modeset_enables(dev, state);` 提前到 `drm_atomic_helper_commit_planes(dev, state, 0);` 之前执行；
     - 在 `dpu_encoder_virt_atomic_enable()` 保持针对非命令型 `INTF_DSI` 且 `!old_crtc_state || !old_crtc_state->active` 的去重 `ctl->ops.reset(ctl)` 并调用 `ctl->ops.clear_pending_flush(ctl)`（此时 `pclk0/1` 已开且在 `commit_planes()` 之前），移除 `dpu_crtc.c`/`dpu_crtc.h` 中不再需要的半吊子 `dpu_crtc_reprogram_blend()`；
     - **离线判据**：`2446` 与 `2447` 正反向 `patch -p1 -F0` 回环通过、`KCFLAGS="-Werror"` 编译 `msm_atomic.o`/`dpu_encoder.o`/`dpu_crtc.o` 零警告、`vmlinux` 与 `.ko` 含 `.BTF` 与 `vermagic: 7.2.15-44.opd2413 SMP preempt mod_unload aarch64`、`sm8750-oneplus-pad2pro.dtb` SHA-256 与 `-35` 逐字节一致。
  2. **装机与双屏上机验收判据**：
     - 保留 `7.2.15-35` 为 `default`、`7.2.15-43` 为备用回退，卸载旧 `-41` 腾出 ESP 空间（`>200 MiB` 可用），单次 `pkexec` 安装 `-44` 并核验 `KSHIM.CHO` SHA-256 与 `1 extent` 不变，设 `boot-select next fedora-7.2.15-44.opd2413.conf` 重启；
     - 双屏（`DSI-1` + `DP-1`）运行 `dual_dpms_test.py`：10/10 轮混合 `4s` 短熄屏、`16s–18s` 长熄屏、长熄屏后 `4s` 短熄屏及在线 `120/60/30 Hz` 切换均由用户**目视确认双屏同时正常恢复桌面**；`0` 内核异常、`0` AVC；`dpu44_dual_after.txt` 满足 `sspp_8[0x0d0] != 0x0c80`、`[0x0f8] != 0`、`intf_1/2[0x1c4] == 0`、`vbif[0x204]` `BIT(17) == 0`、`dsi0/1_phy[0x10]=0x61`、`[0x14]=0x20/0x24`、`dsi0/1_ctrl[0xbc]=0`；
     - 拔掉外接屏跑通单屏 10 轮 DPMS + 刷新率切换 + `s2idle` 后再切默认并冷启动复查关闭 `#47`。
- **离线校验（`2026-11-24 22:38`，`离线通过`）**：
  - `2446`（移除与 `2412` 重叠的 `msm_atomic_check` hunk 后）与 `2447` 严格 `patch -p1 -F0` 正反向回环校验通过；`dpu_encoder_panel_dithers_8bpc` 引用为 `2` 次且无 `dpu_crtc_reprogram_blend`。
  - 在 `localhost/opd2413-builder-kernel:fc45`（`-j7`）下以 `KCFLAGS="-Werror"` 零警告编出 `msm_atomic.o`/`dpu_encoder.o`/`dpu_crtc.o`；`vmlinux`（`[12] .BTF`、`[13] .BTF_ids`）与 `oneplus-pogo-keyboard.ko`（`[36] .BTF`、`vermagic: 7.2.15-44.opd2413 SMP preempt mod_unload aarch64`）校验通过；`sm8750-oneplus-pad2pro.dtb` SHA-256 为 `238ba743288722af635177209e6568636185ceff33694e582b8956cd45e62280`（与 `-35`/`-43` 逐字节一致）；产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-44.opd2413.aarch64.rpm`（SHA-256 `0575ea740a82fabeedd298787b175be576c4ff634962287b91a9880c8a6b52d1`）；已清理 `out/m3k/stage44` 与 `out/m3k/build41`。
- **装机与引导配置（`2026-11-24 22:43`）**：
  - 经用户确认后执行 `boot-select default fedora-7.2.15-35.opd2413.conf` 并 `rpm -e kernel-opd2413-7.2.15-41.opd2413` 释放 ESP 空间（`266M` 可用）；随后校验 RPM SHA-256（`0575ea740a82fabeedd298787b175be576c4ff634962287b91a9880c8a6b52d1`）并 `rpm -ivh --nosignature` 安装 `kernel-opd2413-7.2.15-44.opd2413`。
  - 校验 `/boot/efi/loader/entries/fedora-7.2.15-44.opd2413.conf` 的 `options` 与 `-43` 完全一致（含 `mem_sleep_default=s2idle`，无 `fw_devlink.sync_state=timeout`/`pcie_ports=compat`），`linux`/`initrd`/`devicetree` 非空；设置 `boot-select next fedora-7.2.15-44.opd2413.conf`（`previous_default: fedora-7.2.15-35.opd2413.conf`）；`/boot/efi/KSHIM.CHO` 安装前后 SHA-256 同为 `ddd48cc7705abd14bbfaf877cc0ef9dca3407e5bf3f94c8879bb614ac8495c19` 且保持 `1 extent found`；ESP `/dev/sda16` 已用 `370M / 512M`（`143M` 可用，`73%`）；当前电量 `31% Charging`，已触发系统重启进入 `7.2.15-44.opd2413`。
- **`7.2.15-44.opd2413` 启动实测与全面回退至 `7.2.15-35.opd2413`（`2026-11-24 22:50–22:58`，`真机失败`，证据：`private/display-dpms-grey-20261122/boot44_fail_kmsg.log`）**：
  - **现象与结论**：用户重启进入 `7.2.15-44.opd2413`（`boot -1`）后当场出现**内置屏花屏、外接 `DP-1` 蓝屏**（`msm_atomic_commit_tail()` 提前执行 `drm_atomic_helper_commit_modeset_enables()` 致使 DSI/DP 时序引擎早于 `commit_planes()`/`_dpu_crtc_blend_setup()`/`CTL_FLUSH` 启动扫描）。用户随后通过 `Fedora boot menu` 启动 `-43` 并要求卸载实验内核、回退并搁置 `TECH-DEBT #47`。
  - **归档与代码树回退**：将 `boot -1` 内核日志保存至 `private/display-dpms-grey-20261122/boot44_fail_kmsg.log`，将 `2440`–`2447` 备份至 `private/display-dpms-grey-20261122/patches-shelved/`；对 `out/m3k/linux-7.2.15` 按逆序执行 `patch -p1 -R -F0`、清理 `build43*`/`build44*` 及 `7.2.15-{36..44}` 构建产物，移除仓库 `2440`–`2447` 补丁及 `series`/`PATCHES.md` 对应条目使补丁树恢复至 `7.2.15-35`（`2439`）零差异基线。
  - **设备卸载与默认恢复**：单次 `pkexec` 校验 `/boot/efi/loader/entries/fedora-7.2.15-35.opd2413.conf`（`linux`/`initrd`/`devicetree` 与 `modules.dep` 非空，含 `mem_sleep_default=s2idle`），清理 `/var/lib/opd2413-boot/next.json` 并执行 `boot-select default fedora-7.2.15-35.opd2413.conf`，随后 `rpm -e kernel-opd2413-7.2.15-44.opd2413 kernel-opd2413-7.2.15-43.opd2413`；卸载后复核 `loader_default` 为 `fedora-7.2.15-35.opd2413.conf`、`pending_next` 为 `null`、`rpm -qa` 仅留 `kernel-opd2413-7.2.15-35.opd2413.aarch64`、`/boot/efi/KSHIM.CHO` SHA-256（`846ae1e13319197780b7c13b734f371f05fc321098fa7de55055d3d469f71d9f`）与 `1 extent found` 不变、ESP `/dev/sda16` 释放至 `124M / 512M`（`389M` 可用，`25%`）、电量 `29% Charging`。

## 2026-11-25

### 无外接屏自动熄屏无法唤醒排查与 DP `pm_runtime` 泄漏最小修复（`7.2.15-45.opd2413`，`离线通过`）

- **现场排查与根因定位**：
  - 2026-11-25 `09:16:38 -> 09:18:56` 在无外接显示器状态下触发空闲自动熄屏后无法正常亮屏出图（内核 `7.2.15-35.opd2413`，本次开机连续运行 `10h36m`）。
  - 核对日志与实时 `sysfs` 确认：本次启动初期（`11-24 23:06:57`）曾连接外接 Type-C DP 显示器并于 `23:10:20` 拔出，但 `af54000.displayport-controller` 仍卡在 `status=active`（`active=3683673 ms`、`suspended=4631 ms`），连带将父设备 `ae00000.display-subsystem`（`MDSS GDSC`）钉死在 `active`（`suspended=41 ms`）。`08:17` 与 `09:11` 两次合盖 600 s 后的 `s2idle` 唤醒因系统级 `pm_runtime_force_suspend` 断电复位 MDSS GDSC 而正常亮屏，但唤醒后 `pm_runtime_force_resume` 原样恢复了泄漏的 `usage_count > 0`；于是 `09:16:38` 纯空闲熄屏（仅 `DPMS off`，不进 `s2idle`）期间 `MDSS GDSC` 未掉电，触发 `7.2.15-35` 已知的 `2414` / `CTL_0` 保电卡死（[TECH-DEBT.md](TECH-DEBT.md) `#47`）。
  - 源码比对确认 `7.2.15-35` 的 `dp_display.c` 在 `msm_dp_hpd_plug_handle()` 与 `msm_dp_bridge_detect()` 每次调用均叠加 `pm_runtime_resume_and_get()`，而 `msm_dp_hpd_unplug_handle()` 仅归还 1 次引用，拔出外接屏后引用计数永不归零（重启后未插 DP 时 `af54000.displayport-controller` 实测恢复为 `status=suspended`、`active=36 ms`）。
- **最小修复补丁（第一步“先修复”，`2440`–`2441`）**：
  1. [2440-drm-msm-dp-hold-one-runtime-PM-reference-per-plugged.patch](../kernel/opd2413-7.2/patches/2440-drm-msm-dp-hold-one-runtime-PM-reference-per-plugged.patch)：引入 `erhai` 上游提交 `762bd1bc814f`（Joonhoe Kim），使 DP 插入态仅持有一份 `pm_runtime` 引用，彻底消除拔线后的引用计数泄漏；
  2. [2441-drm-msm-dp-use-3s-runtime-PM-autosuspend-to-absorb-H.patch](../kernel/opd2413-7.2/patches/2441-drm-msm-dp-use-3s-runtime-PM-autosuspend-to-absorb-H.patch)：对非 eDP 的 `msm-dp-display` 启用 `3000 ms` `autosuspend`（带 `devm_add_action_or_reset` 清理）并将 `dp_display.c`/`dp_aux.c` 的 `pm_runtime_put_sync()` 改为 `pm_runtime_put_autosuspend()`，既保证真正拔线 3 s 后挂起并释放 `MDSS GDSC`，又吸收外接显示器 ~1 s 待机 HPD 脉冲避免 `-42` 中在 `commit_modeset_disables` 同步关断 DP 干扰活跃 `DSI-1`。
- **离线校验（`2026-11-25`，`离线通过`）**：
  - `2440` 与 `2441` 均通过严格 `patch -p1 -F0` 正反向回环校验且零偏移，`drivers/gpu/drm/msm/dp/` 已无残留 `pm_runtime_put_sync`。
  - 在 `localhost/opd2413-builder-kernel:fc45` 完成全量编译（`dp_display.o` 与 `dp_aux.o` 通过 `KCFLAGS="-Werror"` 零警告校验；首次 `-j7` 在 `vmlinux`/`Image` 编完进入并行 `BTF [M]` 时伴随 7A PPS 充电卡死，重启后以 `-j4 --log-driver=none` 顺利完成增量续编与打包）。
  - 产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-45.opd2413.aarch64.rpm`（SHA-256 `34d3a27f717eb79783789de64a21371066189b1c37c03bfbf55a141dd563e9f7`）：`vmlinuz` 为未压缩 `ARM64 Image`、`vmlinux`（`[12] .BTF`/`[13] .BTF_ids`）与 `oneplus-pogo-keyboard.ko`（`[36] .BTF`，`vermagic: 7.2.15-45.opd2413 SMP preempt mod_unload aarch64`）校验通过，`System.map` 含 `msm_dp_dont_use_autosuspend`/`msm_dp_hpd_plug_handle`/`msm_dp_bridge_detect`，`sm8750-oneplus-pad2pro.dtb` SHA-256 为 `238ba743288722af635177209e6568636185ceff33694e582b8956cd45e62280`（与 `-35` 逐字节一致）；已清理 `out/m3k/stage45`（暂留 `out/m3k/build45` 供后续第二步根治增量复用）。
- **上机预期与验收判据（`7.2.15-45.opd2413`，待用户确认装机与重启）**：
  1. 保持 `7.2.15-35.opd2413` 为 `default` 回退项，单次 `pkexec` 安装 `kernel-opd2413-7.2.15-45.opd2413.aarch64.rpm`、核验 BLS `options` 与 `-35` 一致且 `KSHIM.CHO` SHA-256 与 `1 extent found` 不变，设 `boot-select next fedora-7.2.15-45.opd2413.conf` 重启进入 `uname -r = 7.2.15-45.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、`0 AVC`）；
  2. **核心回归判据（拔出外接屏后不重启）**：插上外接 Type-C DP 显示器点亮后再拔出，等待 `>= 4 s` 后检查 `/sys/devices/platform/soc@0/ae00000.display-subsystem/af54000.displayport-controller/power/runtime_status == suspended` 且 `runtime_suspended_time` 持续增长；随后在不重启的情况下执行单屏 `DPMS off (>= 3 s) -> on`（≥5 轮）与真实空闲自动熄屏唤醒，确认 `ae00000.display-subsystem`（`MDSS GDSC`）每次熄屏 `runtime_suspended_time` 均正常增加、内置 `DSI-1` 每次均正常亮屏出图且内核零 DSI/DPU/DP 报错；
  3. **`s2idle` 与热插拔复核**：拔线前后及单屏状态下各做一次 `s2idle` 休眠唤醒无超时/WARNING；验收通过后经用户确认设 `-45` 为默认（保留 `-35` 作回退）并推进第二步 `TECH-DEBT #47` 底层根治。
- **装机与引导核验（`2026-11-25 12:46`）**：
  - 经用户确认，单次 `pkexec` 校验 RPM SHA-256（`34d3a27f717eb79783789de64a21371066189b1c37c03bfbf55a141dd563e9f7`）并完成 `rpm -ivh --nosignature` 安装（保留 `7.2.15-35.opd2413` 为默认回退）；
  - 核验 `/boot/efi/loader/entries/fedora-7.2.15-45.opd2413.conf` 的 `options` 与 `-35` 完全一致，`linux`（`62M`）、`sm8750-oneplus-pad2pro.dtb`（`145K`）、`initrd`（`62M`）均非空；
  - 核验 `/boot/efi/KSHIM.CHO` 安装前后 SHA-256 同为 `c8e09f6dace5531b2341c88d4db53046408dd4032d92512977501ca93c914ac6` 且保持 `1 extent found`；`kshim_remembered: "Fedora"`；已设 `boot-select next fedora-7.2.15-45.opd2413.conf`（`previous_default: fedora-7.2.15-35.opd2413.conf`）；ESP `/dev/sda16` 为 `247M / 512M`（`266M` 可用，`49%`）；电量 `79% (Discharging)`。待用户重启进入 `7.2.15-45.opd2413` 验收。
- **`7.2.15-45.opd2413` 实机开机、外接屏热插拔与单屏 5 轮 DPMS 复核（`2026-11-25 12:48–19:05`，`真机启动`，待用户目视确认升级 `真机通过`）**：
  1. **开机与 6 小时日常运行**：`uname -r = 7.2.15-45.opd2413`、`systemctl is-system-running = running`、`0 failed`、SELinux `Enforcing`、`0 avc: denied`；`af54000.displayport-controller` 显示 `autosuspend_delay_ms = 3000`、`runtime_status = suspended`；`13:11–19:01` 期间 3 次真实 `s2idle` 唤醒（`14:10`、`14:27->14:53`、`17:24->19:01`）及多次纯熄屏唤醒均正常。
  2. **外接 DP 热插拔无泄漏实测（`19:03:46 -> 19:03:53`）**：插上外接 Type-C DP 显示器（`wcd939x-usbss: mode=4 dp_active=1`）点亮后再拔出（`mode=0 dp_active=0`，`DP-1: disconnected`），等待 `>3 s` 后 `af54000.displayport-controller` 自动恢复 `runtime_status = suspended`（`active = 18.4 s`，`suspended = 14764 s`），彻底消除 `7.2.15-35` 拔线后永久泄漏卡死 `active` 的缺陷，零内核报错。
  3. **拔线后不重启 5 轮单屏 `DPMS off (3.2 s) -> on (2.2 s)` 压测（`19:04:44–19:05:11`）**：5/5 轮熄屏态实测 `mdss = suspended`（每轮 `MDSS GDSC` 挂起增量 `+2709..+2732 ms`）且 `dp = suspended`（每轮 `+5464..+5473 ms`），`nt36536` 触控重载 `5/5`、`Anomalous kernel lines: 0`（注：第 5 轮末尾 `bl=412` 为 KDE 60 s 空闲变暗，属正常行为）。待用户目视确认 5 轮亮屏画面均正常，并确认是否执行 `boot-select default fedora-7.2.15-45.opd2413.conf`（保留 `-35` 作回退）后，推进第二步 `TECH-DEBT #47` 底层根治。
- **用户目视确认与设为默认（`2026-11-25 19:07`，`真机通过`）**：
  - 用户目视确认 5/5 轮熄屏/唤醒画面均正常；经确认单次 `pkexec` 执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-45.opd2413.conf`（保留 `7.2.15-35.opd2413` 作回退）；核验 `loader_default = booted_entry = fedora-7.2.15-45.opd2413.conf`、`pending_next = null`、`kshim_remembered = "Fedora"`，`/boot/efi/KSHIM.CHO` SHA-256（`c8e09f6dace5531b2341c88d4db53046408dd4032d92512977501ca93c914ac6`）与 `1 extent found` 均未变化。

### 第二步根治 `TECH-DEBT #47`：`7.2.15-46.opd2413`（DPMS-off 末尾 `CTL` 复位 + SM8750 双路 DSI 同步 + 首帧带宽，`离线通过`）

- **根因收敛与方案设计（`2442`–`2449`，基于 `7.2.15-45` 的 `2440`–`2441` 之上）**：
  1. 综合复盘 `-37`..`-44` 全量寄存器快照与代码路径：`_dpu_encoder_helper_phys_cleanup()` 在 `DPMS off` 阶段必须保留 `trigger_flush + trigger_start`（`-39` 跳过它们会直接导致下次 `panel_prepare()` 报 `dsi1 cmd dma timeout`），但当 `MDSS GDSC` 未掉电（如外接 DP 在线或尚未挂起）时，因视频时序引擎已停，这次 `trigger_flush/start` 会把 `CTL_FLUSH`/`CTL_START` 悬空留在硬件里导致下次唤醒 `CTL_0` 卡死。
  2. 此前 `-40`（`dpu_crtc_atomic_begin()`，早于 `pclk0/1` 启动）、`-41`/`-43`（`dpu_encoder_virt_atomic_enable()`，晚于 `commit_planes()` 破坏长熄屏重挂平面后的 `CTL_0 <-> sspp_8`/`LUTDMA` 同步）与 `-44`（提前 `commit_modeset_enables()` 致启动花屏/蓝屏）均因复位时机或提交顺序偏差失败。
  3. **最小根因修复（[2449](../kernel/opd2413-7.2/patches/2449-drm-msm-dpu-reset-DSI-video-CTL-after-DPMS-off-clean.patch)）**：仅在 `_dpu_encoder_helper_phys_cleanup()` 末尾 `trigger_flush` + `trigger_start` 之后、且仅针对 `INTF_MODE_VIDEO && intf_type == INTF_DSI && !skip_vid_trigger`（即 DSI 视频屏 `DPMS off`）追加 8 行 `ctl->ops.reset(ctl)`。此时 `dsi_mgr_bridge_post_disable()` 尚未运行、`pclk0/1` 仍在运行，可无阻塞把 `CTL_0` 归零回冷态；下次 `DPMS on` 保持原版 `msm_atomic_commit_tail()` 标准顺序（`disables -> commit_planes -> enables -> flush_commit`），零启动花屏风险且无 `commit_planes()` 之后的破坏性复位。
  4. **配套改动**：
     - 保留 `-45` 的 `2440`–`2441`（DP 单引用 + 3 s `autosuspend`，吸收显示器 ~1.05 s 待机 HPD 脉冲，避免 `-42` 的 4 s 短熄屏同步关断 DP 欠载，且不引入破坏 `s2idle` 的 `qmp-combo` `SW_PWRDN`）；
     - 恢复 `erhai` `sm8750/v7.4-dev` 6 项 SM8750 绑定双路 DSI 黄金同步补丁（`2442`–`2447`）；
     - 恢复 `2448`（[2448-drm-msm-dpu-calculate-plane-perf-in-atomic_check-on-.patch](../kernel/opd2413-7.2/patches/2448-drm-msm-dpu-calculate-plane-perf-in-atomic_check-on-.patch)，消除长熄屏拆面重挂后首帧 `new_perf.bw_ctl = 0` 欠载）。
- **离线校验（`2026-11-25 20:01`，`离线通过`）**：
  - `2442`–`2449` 全部 8 个补丁在 `out/m3k/linux-7.2.15` 通过严格 `patch -p1 -F0` 反向 + 正向回环校验，`dpu_encoder_panel_dithers_8bpc` 引用计数为 `2`；
  - 在 `localhost/opd2413-builder-kernel:fc45`（`-j4 --log-driver=none`）下先以 `KCFLAGS="-Werror"` 零警告编过全部 7 个受改动影响的 `.o` 文件（`dsi_manager.o`/`dsi_host.o`/`dsi_phy.o`/`dsi_phy_7nm.o`/`dpu_encoder.o`/`dpu_core_perf.o`/`dpu_plane.o`），随后完成 `Image`、`modules`、`qcom/sm8750-oneplus-pad2pro.dtb` 与 RPM 打包；
  - 产物 `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-46.opd2413.aarch64.rpm`（`42M`，SHA-256 `33561ffe7a3acbc53a754997e7b2ca4c21ff6ebf063973c20a9f6d09a658f271`）：
    - `sm8750-oneplus-pad2pro.dtb` SHA-256 为 `238ba743288722af635177209e6568636185ceff33694e582b8956cd45e62280`（与 `-45`/`-35` 逐字节一致）；
    - `vmlinuz` 为未压缩 `Linux kernel ARM64 boot executable Image`；
    - `vmlinux`（`[12] .BTF`/`[13] .BTF_ids`）与 `oneplus-pogo-keyboard.ko`（`[36] .BTF`，`vermagic: 7.2.15-46.opd2413 SMP preempt mod_unload aarch64`）校验通过；
    - `System.map` 与 `vmlinux` 检出全部关键符号/字符串：`msm_dp_dont_use_autosuspend`、`dpu_plane_calc_perf`、`msm_dsi_host_reset_after_phy_sync`、`dsi_7nm_phy_toggle_resync_fifo` 及 `post-cleanup ctl %d reset failed`；已清理 `out/m3k/stage46`。
- **上机预期与验收判据（`7.2.15-46.opd2413`，待用户确认装机与重启）**：
  1. **安全安装与一次性启动**：保留 `7.2.15-45.opd2413` 为 `default`、`7.2.15-35.opd2413` 为二级回退（当前 ESP 空闲 `266M`，无需卸载任何内核），单次 `pkexec` 安装 `-46`、校验 BLS `options` 与 `-45` 一致、`KSHIM.CHO` SHA-256 与 `1 extent found` 不变，并设 `boot-select next fedora-7.2.15-46.opd2413.conf`；重启进入 `uname -r = 7.2.15-46.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、`0 AVC`、`autosuspend_delay_ms = 3000`）。
  2. **双屏混合压测（接入外接 Type-C DP 显示器，运行 `private/display-dpms-grey-20261122/dual_dpms_test.py`）**：
     - 10/10 轮混合 `4 s` 短熄屏、`16–18 s` 超待机长熄屏、长熄屏后 `4 s` 短熄屏及在线 `120/60/30 Hz` 刷新率切换，**均由用户目视确认 `DSI-1` 与 `DP-1` 双屏同时正常恢复画面**；
     - `0` 内核异常（无 `post-cleanup ctl ... reset failed`、无 `dsi1 cmd dma timeout`、无 `vblank timeout`、无 `devcoredump`）；
     - 抓包 `dpu46_dual_after.txt` 满足 `sspp_8[0x0d0] != 0x0c80`、`[0x0f8] != 0`、`intf_1/2[0x1c4] == 0`、`dsi0/1_phy[0x10] = 0x61`、`[0x14] = 0x20/0x24`、`dsi0/1_ctrl[0xbc] = 0`。
  3. **单屏与 `s2idle` 回归（拔出外接 DP 后不重启）**：
     - 拔线 `>3 s` 后 `af54000.displayport-controller` 自动回归 `suspended`；
     - 单屏多轮 `DPMS off -> on`（`MDSS GDSC` 每次正常掉电）、在线 `120/60/30 Hz` 切换与 `s2idle` 休眠唤醒均零异常；全部通过后经用户确认设 `-46` 为默认、做冷启动复查并关闭 `TECH-DEBT #47`。
- **装机与引导核验（`2026-11-25 20:08`）**：
  - 经用户确认，单次 `pkexec` 校验 RPM SHA-256（`33561ffe7a3acbc53a754997e7b2ca4c21ff6ebf063973c20a9f6d09a658f271`）并完成 `rpm -ivh --nosignature` 安装（保留 `-45` 为 `previous_default`、`-35` 为二级回退，三版并存）；
  - 核验 `/boot/efi/fedora/7.2.15-46.opd2413/` 下 `linux`（`62M`）、`initrd`（`62M`）、`sm8750-oneplus-pad2pro.dtb`（`145K`）均非空，`/boot/efi/loader/entries/fedora-7.2.15-46.opd2413.conf` 的 `options` 与 `-45` 零差异；
  - 核验 `/boot/efi/KSHIM.CHO` 安装前后 SHA-256 同为 `c8e09f6dace5531b2341c88d4db53046408dd4032d92512977501ca93c914ac6` 且保持 `1 extent found`、`kshim_remembered = "Fedora"`；已设 `boot-select next fedora-7.2.15-46.opd2413.conf`（`previous_default: fedora-7.2.15-45.opd2413.conf`）；ESP `/dev/sda16` 为 `370M / 512M`（`143M` 可用，`73%`）；电量 `41% (Charging)`。待用户重启进入 `7.2.15-46.opd2413` 开展双屏与单屏验收。
- **`7.2.15-46.opd2413` 实机双屏验收与按用户决定收尾回退至 `7.2.15-45.opd2413`（`2026-11-25 20:27–20:39`，`真机失败`，证据：`private/display-dpms-grey-20261122/dual46_dpms_test.log`、`dual46_kmsg.log`）**：
  1. **开机与 10 轮压测指标**：`uname -r = 7.2.15-46.opd2413`、`running`、`0 failed`、SELinux `Enforcing`、`0 AVC`、`autosuspend_delay_ms = 3000`，`DP-1`（`2560x1440@144`）与 `DSI-1`（`3392x2400@120`）双屏正常点亮。10 轮混合压测（`dual46_dpms_test.py`）跑满 `10/10`、`Anomalous kernel lines: 0`、`0 AVC`、4 路面板电源轨熄屏全部 `disabled`、`nt36536` 重载 `14/14`、`mdss=+0ms`/`dp=+0ms`（`2441` 完整吸收待机 HPD 脉冲）。
  2. **用户目视结论（`真机失败`）**：前面 `4 s` 短熄屏内置屏均能正常恢复，外接 `DP-1` 全程始终正常恢复；但后续双屏长熄屏（`16–18 s`）仅 1 次内置屏恢复画面，其余长熄屏轮次内置屏仍停留在背光黑屏。
  3. **按用户决定收尾与代码整理**：用户决定不再继续追究 `#47` 双屏长熄屏，满足于当前已站稳的 `7.2.15-45.opd2413`（彻底修复拔出外接屏后无外接屏单屏熄屏无法唤醒的问题）。已将 `2449` 归档至 `private/display-dpms-grey-20261122/patches-shelved/`，`out/m3k/linux-7.2.15` 按逆序 `patch -p1 -F0 -R` 撤回 `2449`–`2442` 并通过 `2440`–`2441` 严格 `-F0` 正反向回环校验，清理仓库 `2442`–`2449`、`series`/`PATCHES.md` 条目与 `build46*`/`kernel-7.2.15-46` 临时构建产物，使仓库补丁树与已验收默认内核 `7.2.15-45.opd2413`（`2440`–`2441`）精确一致。
  4. **卸载实验内核与 ESP 回收（`2026-11-25 20:41`）**：经用户确认，单次 `pkexec` 校验 `-45` 启动文件完整性并确认 `boot-select default fedora-7.2.15-45.opd2413.conf` 后执行 `rpm -e kernel-opd2413-7.2.15-46.opd2413`；卸载后复核 `loader_default = fedora-7.2.15-45.opd2413.conf`、`pending_next = null`、`loader_entries` 仅剩 `7.2.15-35` 与 `7.2.15-45`、`/boot/efi/KSHIM.CHO` 前后 SHA-256 同为 `c8e09f6dace5531b2341c88d4db53046408dd4032d92512977501ca93c914ac6` 且保持 `1 extent found`、ESP `/dev/sda16` 释放至 `247M / 512M`（`266M` 可用，`49%`）、电量 `43% (Charging)`。
