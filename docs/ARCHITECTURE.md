# 整体架构

目标：一加平板 2 Pro 上运行**标准、可变的 Fedora 45 aarch64 + KDE Plasma**，与 ColorOS 双启动。
Fedora 的软件包原样安装、由 dnf 管理；设备适配只通过几个独立的 RPM 加进去。

## 1. 分层

```
┌──────────────────────────────────────────────────────────────┐
│ 桌面策略   opd2413-desktop：缩放、电源键、合盖、屏幕键盘等默认值   │ 换桌面时重写
├──────────────────────────────────────────────────────────────┤
│ 集成层     kernel-install 钩子、dracut 配置、ESP 布局            │ 换发行版时重写
├──────────────────────────────────────────────────────────────┤
│ 设备层     opd2413-device：udev、ufs-guard、地址服务             │
│            opd2413-audio：UCM、AudioReach 拓扑                   │ 与发行版基本无关
│            opd2413-sensors：hexagonrpc、libssc、iio-sensor-proxy │
├──────────────────────────────────────────────────────────────┤
│ 硬件层     kernel-opd2413：内核、模块、DTB                        │
│            opd2413-firmware：原厂固件（本地构建，不分发）          │ 与发行版无关
├──────────────────────────────────────────────────────────────┤
│ 发行版     Fedora 45 官方仓库的软件包，不修改                      │
├──────────────────────────────────────────────────────────────┤
│ 启动链     ABL → kShimC → U-Boot → systemd-boot（已固化，不动）   │
└──────────────────────────────────────────────────────────────┘
```

规则：

- 不修改 Fedora 自己的文件。必须替换的组件（例如带补丁的 Mesa、iio-sensor-proxy）单独成包，
  上游或 Fedora 支持后删除。
- 硬件层不依赖桌面、显示管理器或固定账户。
- 本机唯一数据（校准、MAC、蓝牙地址、传感器 registry）不进任何包，安装时从本机导入。
- 不做统管一切的常驻服务。

## 2. 启动链

```
开机 → OEM ABL（不替换）
     → boot_b 里的 kShimC 菜单（记住上次选择，记录在 ESP 的 KSHIM.CHO）
        ├─ ColorOS：原 Android 内核，原样交接
        ├─ "Armada"：          U-Boot quiet 模式，不显示菜单，启动 systemd-boot 默认项
        ├─ "Armada boot menu"：U-Boot menu 模式，显示 systemd-boot 菜单（回滚入口）
        └─ "Armada USB disk"： U 盘恢复入口
     → U-Boot（嵌在 boot_b 里，UFS 只读）
        从 LUN0 上 PARTLABEL=ARMADA 的 FAT 分区加载：
          /dtbs/qcom/sm8750-oneplus-pad2pro.dtb
          /EFI/BOOT/BOOTAA64.EFI（systemd-boot）
        然后 bootefi，把这份 DTB 交给 EFI
     → systemd-boot 读 ESP 上的 /loader/entries/*.conf
     → Linux EFI stub → initramfs → Fedora 根
```

这条链对发行版一无所知，所以换成 Fedora **不需要重写 `boot_b`**，只要满足三个约定：

1. ESP 的分区名仍是 `ARMADA`，仍是 FAT。
2. DTB 在 ESP 的 `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb`。
3. systemd-boot 在 `/EFI/BOOT/BOOTAA64.EFI`，内核和 initramfs 都在 ESP 上
   （systemd-boot 只能读 FAT；U-Boot 的 UFS 驱动只读且有白名单）。

菜单项标题里的 "Armada" 字样写在 `boot_b` 里，改名需要重写 `boot_b`，列为可选的后续项。

### Fedora 侧的集成方式

- 用 Fedora 自带的 `kernel-install`，布局 `bls`：每个内核装到 ESP 的
  `/fedora/<kver>/{linux,initrd,<dtb>}`，条目写到 `/loader/entries/fedora-<kver>.conf`。
  设置放在 `/usr/lib/kernel/install.conf.d/50-opd2413.conf`
  （`/usr/lib/kernel/install.conf` 本身属于 `systemd-udev`，不能由我们的包提供）。
- `/usr/lib/kernel/devicetree` 指定 DTB，`kernel-install` 会把它拷进条目目录并写 `devicetree` 行。
- 内核命令行在 `/etc/kernel/cmdline`，条目前缀在 `/etc/kernel/entry-token`（`fedora`）。
  这两个文件含本机信息，由安装步骤生成，不进包。
- 插件 `95-opd2413-dtb.install` 把正在安装的内核的 DTB 同步到约定 2 的固定路径。
- `/usr/share/dnf5/libdnf.conf.d/50-opd2413-kernel.conf` 排除 Fedora 自己的 `kernel*` 包：
  它们装上后会成为 ESP 上最新的条目，而这台机器启动不了通用内核。
- systemd-boot 本体用 `bootctl --esp-path=/boot/efi --no-variables update` 更新（U-Boot 的 EFI 没有持久变量）。
  2026-11-11 起 ESP 上是 Fedora 45 的 262.1，旧的 259 由 bootctl 留作 `systemd-boot-fallbackaa64.efi`。
- `dracut-config-rescue` 的 kernel-install 插件被 `opd2413-device` 屏蔽（ESP 放不下第二个 initramfs）。
- 不装 GRUB 和 shim。

内核实际用的是条目里 `devicetree` 行指定的那份：systemd-boot 用它替换 U-Boot 交给 EFI 的设备树，U-Boot 再通过 EFI 设备树
修补协议补上 `/chosen` 和内存等信息。2026-11-11 真机验证（条目 DTB 里加的标记属性出现在 `/proc/device-tree/chosen`，
`u-boot,version` 也在）。所以每个内核用自己同次构建的 DTB，回滚内核时 DTB 一起回滚；固定路径那份只给 U-Boot 自己用，
也是没有 `devicetree` 行的条目的兜底。

### ESP 容量

ESP 512 MiB（FAT16）。现在一套 Armada 内核占 149 MB（未压缩内核 64 MB + 非 hostonly 的
initramfs 84 MB），三套就满了。Fedora 侧：

- `installonly_limit=2`（`opd2413-device` 设置），只保留两个内核。
- initramfs 用 hostonly（在设备上生成）：63 MB，每个内核在 ESP 上约 128 MB。
- 内核升级到 Fedora 配置后启用 `EFI_ZBOOT` 压缩。

## 3. 存储布局

UFS LUN0（4 KiB 扇区），不改分区表：

| 分区 | 名称 | 大小 | 用途 |
|---|---|---|---|
| sda1–14 | 原厂 | — | 不动，Linux 下只读 |
| sda15 | `userdata` | 204 GiB | Android 数据，Linux 下只读 |
| sda16 | `ARMADA` | 512 MiB | ESP，FAT16，挂在 `/boot/efi`。Fedora 的内核和 initramfs、systemd-boot、固定路径的 DTB、`KSHIM.CHO` |
| sda17 | `ARMADA_BOOT` | 1 GiB | 原 Armada 的 ext4 `/boot`。Fedora 不需要，用途待定 |
| sda18 | `ARMADA_ROOT` | 254.5 GiB | btrfs（zstd:1）。Fedora 的根在子卷 `fedora`，home 在子卷 `fedora-home` |

分区名保留 `ARMADA*`：U-Boot 按名字找 ESP，ufs-guard 按名字放行写入。

Fedora 是在运行中的 Armada 里装进新子卷的（没有重新 mkfs），首次启动验收后删除了 Armada 的
`root`、`var`、`home` 三个子卷（2026-11-11）。过程见 [M1-INSTALL.md](M1-INSTALL.md)。

其余 LUN（1–5）在 Linux 下整盘只读。

## 4. 软件包

全部放在本仓库 `packaging/`，构建产物进本地 dnf 仓库（后续可换 COPR；固件包永远只在本地）。

| 包 | 内容 | 层 |
|---|---|---|
| `kernel-opd2413` | `/usr/lib/modules/<kver>/{vmlinuz,dtb/,kernel/…}`，布局与 Fedora 内核包一致，由 `kernel-install` 部署 | 硬件 |
| `opd2413-firmware` | `/usr/lib/firmware/` 下的原厂固件，附逐文件 SHA-256 清单。从用户自己的 OTA 提取，**不分发** | 硬件 |
| `opd2413-device` | udev 规则、`ufs-guard`、dracut 配置（早期固件列表）、`kernel-install` 插件、`/etc/kernel/cmdline` 默认值、Wi-Fi MAC 和蓝牙地址服务 | 设备 + 集成 |
| `opd2413-audio` | UCM 配置和 AudioReach 拓扑 | 设备 |
| `opd2413-sensors` | hexagonrpc、libssc、带补丁的 iio-sensor-proxy、传感器配置 | 设备 |
| `opd2413-desktop` | KDE 默认值：缩放、电源键与合盖行为、屏幕键盘 | 桌面策略 |
| `opd2413-mesa`（仅在需要时） | 带补丁的 Mesa。先验证 Fedora 45 自带的 26.2.6 能否驱动 Adreno 830 | 设备 |

内核版本号用 `7.2.6-<N>.opd2413`，每次构建 `N` 加一、不复用（模块 BTF 与内核必须同次构建，旧模块配新内核会加载失败）。
一个版本号不能是另一个的前缀：kernel-install 卸载内核时会删除所有 `fedora-<kver>*.conf`。

## 5. 内核路线

**第一步（M1）**：原样使用 Armada 分支已真机验证的内核
（7.2.6 + 补丁序列 + `sm8750-oneplus-pad2pro.dts`，构建产物 `kern2`），只重新打成 RPM。
这一步唯一的变量是发行版用户态。

**第二步（M3）**：以 Fedora 45 当时的内核（dist-git 的 `kernel.spec` 和配置）为基线。
2026-11-10 核对 Fedora 45 updates 仓库，内核已经是 **7.3.3**（立项时按主机上未更新的 7.2.15 估计，有误）。
所以 Armada（7.2.6）和 erhai（7.2.14）的补丁都要前移一个大版本，其中一部分可能已被 7.3 收录，
合入前先逐个核对上游状态。合入内容：

- Armada 序列中 SM8750 通用部分和 OPD2413 专用的 `1400`–`1409`；
  其他掌机（SM8250 / SM8550 / SM8650 / SM7750）的补丁不带。
- erhai v0.6（7.2.14）里 Armada 没有的功能：s2idle 休眠、9 V PD 与 SC8547A 电荷泵充电、
  SC820CS / SC1300CS 摄像头与 SM8750 camss、iris 与 GMU 修复、霍尔合盖。
- 两边重叠的部分（面板、触控、Pogo 键盘、音频）逐项对比后选一个来源，不混用。

补丁来源和修改说明记在 `kernel/PATCHES.md`。

## 6. 原厂固件与专有部分

ColorOS 的内核模块（6.6 GKI）和 HAL（bionic）不能在 Fedora 上加载。能从 ColorOS 拿的是：

| 类别 | 内容 | 来源 |
|---|---|---|
| 远端处理器固件 | ADSP、ADSP DTB、SoCCP（CDSP 待评估） | OTA 的 `modem` 分区 |
| GPU / 视频 | `gen80000_zap.mbn`（OnePlus 签名）、`vpu35_4v.mbn` | OTA 的 `vendor` |
| 触控 | `nt36536-xn242.bin` | OTA 的 `dtbo` 内嵌数据 |
| 功放 | `aw882xx_acf.bin` | OTA 的 `odm` |
| Wi-Fi / 蓝牙 | regdb、板级数据、`gng*` | OTA 的 `odm` / `vendor` / `bluetooth` |
| 传感器配置 | SSC json 与 registry | OTA 的 `vendor` / `odm`，registry 来自本机 `persist` |
| 本机身份与校准 | Wi-Fi MAC、蓝牙地址、扬声器校准 | 只能来自本机 |
| 参考答案 | 运行时设备树、寄存器时序、上电顺序 | 本机只读采集 |

通用固件优先用 Fedora 的包。2026-11-10 核对 Fedora 45 仓库：`qcom-firmware` 已有 Adreno 830 的
`gen80000_{sqe,gmu,aqe}`；`atheros-firmware` 只有 WCN7850，**没有 WCN7860**，蓝牙的 `gng*` 也没有，
所以这 9 个文件暂时由 `opd2413-firmware` 提供，Fedora 收录后删除。

**不支持、也不计划支持**：SUPERVOOC / UFCS 快充、指纹、原厂相机算法（ICP）、Widevine / HDCP、
NFC、手写笔（用户决定忽略）。详见 [HARDWARE.md](HARDWARE.md)。

## 7. initramfs

- 用 dracut，在设备上生成。M1 用非 hostonly 模式（首次生成在安装用的 chroot 里，主机探测不可靠）。
- dracut 模块 `90opd2413` 负责把下面的固件装进去，清单取自 `opd2413-firmware` 自带的哈希清单。
- 这几样固件驱动探测时就要用，但不能通过 `MODULE_FIRMWARE` 自动发现，必须显式装进 initramfs：
  触控固件、GPU zap 与 SQE / GMU / AQE、ADSP 与 SoCCP、功放 ACF、音频拓扑。
  缺了它们不会启动失败，只会让触控和 GPU 静默失效（Armada 上踩过，见 armada 计划文档 §19.44）。
- 清单里的文件缺一个，initramfs 生成就失败。

## 8. 更新与回滚

- 用户态：`dnf upgrade`，和普通 Fedora 一样。
- 内核：装新的 `kernel-opd2413` → `kernel-install` 写新条目 → 旧内核保留为上一项。
  启动失败时在 kShimC 里选 "Armada boot menu"，从 systemd-boot 菜单选旧内核。
- 根文件系统：btrfs 子卷，重大升级前可以手动快照。
- 救援：kShimC 的 USB 入口；最坏情况回 Android 后用 adb 处理 ESP。
- ColorOS OTA 会覆盖 `boot`：需要重新把 kShimC 镜像写回活动槽（流程待在 M5 整理）。

## 9. 仓库结构

```
AGENTS.md           规则与已确认的决定
docs/               架构、状态、工作日志、技术债、硬件清单
kernel/             补丁序列、DTS、配置、来源记录
packaging/          各 RPM 的 spec 和文件
device/             设备层文件（udev、dracut、kernel-install 插件等）
tools/              构建脚本（主机上运行）和安装脚本（平板上运行）
tests/              离线测试
private/            （忽略）固件、备份、日志、本机数据
out/                （忽略）构建输出
```
