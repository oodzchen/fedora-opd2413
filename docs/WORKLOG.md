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
