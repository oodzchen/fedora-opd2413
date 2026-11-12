# 实现进度

状态词：待调研、有源码线索、离线通过、真机启动、真机通过、真机失败。
"未开始"只用于还没动手的工作步骤。

## 唯一的下一步

**M3 完成，下一个方向待用户定。** PPS 快充（M3.2b）缺 PPS 充电器，搁置；有 PPS 充电器时：电量 < 75 % 插上，看 `PD_PPS`、VBUS 升到 8.4 V 以上、电池电流、温度、拔线回退。
候选方向见下面"之后可以做的"。7.2.15-10 已冷启动验证（2026-11-12 16:32）。
测试新内核用 `tools/tablet-reboot.py --entry …`；装新内核前先 `boot-select default <当前条目>`。拔线调试时每次重启后都要重新起 `opd2413-debug-inhibit`。

M3.4a 视频硬解 2026-11-12 真机通过：固件 `opd2413-firmware-16.0.10.600-2`（加 `vpu35_4v.mbn`），GStreamer 硬解 H.264/HEVC，Showtime 为默认播放器，VP9 软解（设备包 0.1-13）。
M3.4c 传感器 2026-11-12 真机通过：`opd2413-sensors-0.1-1`（hexagonrpcd + libssc + SSC 版 iio-sensor-proxy，registry 已导入），自动旋转、环境光、指南针、陀螺仪可用。
M3.5 麦克风、M3.6 键盘 2026-11-12 真机通过：默认内核 `7.2.15-10.opd2413`，设备包 0.1-11，音频包 0.1-12。
M3.4b 摄像头 2026-11-12 真机通过：`7.2.15-5.opd2413`，前后摄预览、拍照、录像；无自动对焦、无调校。
M3.2b PPS：`7.2.15-4` 起驱动加载、电荷泵探测、`pps_enable=Y`，快充本身待测。

M3.3 2026-11-12 真机通过：s2idle 可用（设备包 0.1-9/0.1-10，`MemorySleepMode=s2idle`），用户在 KDE 里把电源键、合盖设为睡眠；
启动参数去掉三个 `*_ignore_unused`、加 `fw_devlink.sync_state=timeout` 后，挂起时 CX 塌陷、DDR 自刷新约 98 %（插着 USB）。
另修了 `boot-select` 的一个错误：之前写入 loader.conf 的精确条目名不带 `.conf`，systemd-boot 匹配不上、退回最新条目。

M3 第 2 项 M3.2a 2026-11-12 真机通过：`7.2.15-3.opd2413`（erhai v0.7.2 的 battmgr 整文件）是默认内核；快充充电器上固定 9 V PD，电流符号正确，冷启动复查通过。
M3 第 1 项蓝牙 2026-11-12 真机通过：`7.2.15-2.opd2413`（erhai `5fbc7cbd1` + RFCOMM TTY、BNEP）是默认内核，用户用音箱和耳机实测正常，冷启动复查通过。
M3 第 0 步（内核基线 7.2.6 → 7.2.15）2026-11-12 真机通过：`7.2.15-1.opd2413` 是默认内核，冷启动复查通过，用户确认画面、触控、键盘和触控板、
声音、亮度、熄屏亮屏正常（WORKLOG"20:55 起"）。`boot-select next` 加自动恢复也已真机通过（[BOOT-CONTROL.md](BOOT-CONTROL.md)）。
M3 顺序：~~蓝牙~~ → ~~电池与充电（9 V）~~ → 休眠与按键 → 传感器/摄像头/硬解（[M3-FEATURES.md](M3-FEATURES.md)）。
7.3 基线暂停，改为 M6（[M3-KERNEL.md](M3-KERNEL.md) 顶部有暂停时的状态）。发现和修复可以回馈 erhai，每次提交前先问。

M2 剩下的被动观察项：开机提示音毛刺再出现时当场取证；空闲自动熄屏能否恢复。

## 当前阻塞

没有阻塞。默认内核 `7.2.15-3.opd2413`，Fedora 45 KDE 正常运行；7.2.15-2 是回退项（内核 3、7.2.15-1 已卸载）。

已知的坑：

- 一次性启动的测试内核如果在挂上根分区之前就复位，会一直重复启动它：在 kShimC 菜单选 "Fedora boot menu"，再在 systemd-boot 里选正常内核。
- 用 ramoops 取证时：长按电源会丢记录；不是每种复位都保内存。
- 没有网络和画面时先**短按**电源键，用户态活着就会正常关机，journal 完整。（现在 KDE 里电源键设成了睡眠，短按会挂起而不是关机。）
- **没插电时 `systemctl poweroff` 不会自动开机**，要人按电源键；冷启动验证前先确认插着电。
- 改了 `/etc/modprobe.d` 要重新生成 initramfs（`kernel-install add <版本> /lib/modules/<版本>/vmlinuz`），否则 initramfs 里加载的模块还用旧参数。

## 接手时先做这几件事

1. 读本文件；需要了解启动链和安装过程时读 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [M1-INSTALL.md](M1-INSTALL.md)。
2. 平板默认就进 Fedora（kShimC 菜单里的 "Fedora" 项，`boot-select status` 可查）。重启测试用 `tools/tablet-reboot.py`。SSH：`OPD_OS=fedora private/ssh.sh`，
   拷文件 `OPD_OS=fedora private/scp.sh`；IP 变了设 `OPD_HOST`，或在局域网里扫 22 端口找。
3. 改了 `device/` 或任何 spec，按 [BUILD.md](BUILD.md) 重新构建、跑离线测试，再拷到平板用 `dnf install ./*.rpm` 装。
4. 关机会自动重新开机（插着电时）。需要冷启动验证时可以直接经 SSH `systemctl poweroff`，约 40 秒后回来。

## 设备状态（2026-11-12 15:20）

- 15:20 运行：Fedora 45 KDE，内核 `7.2.15-10.opd2413`（默认，`fedora-*`；摄像头、麦克风可用），`running`。装了 `libcamera-tools`、`snapshot`。启动参数没有 `*_ignore_unused`、有 `fw_devlink.sync_state=timeout`。
  s2idle 可用，挂起时 CX 塌陷。PPS 引擎已开（`pps_enable=Y`）。用户拔线放电中（电量 97 %）。蓝牙打开，有一个用户配对的设备。
  `/etc/kernel/cmdline` 改前的备份在 `/var/tmp/opd2413/m3-sleep/cmdline-100831/`；删掉的 `opd2413-pps.conf` 备份在 `/var/tmp/opd2413/m3-pps-20261112/`。
- systemd-boot：`loader.conf` 默认 `fedora-*`（选版本最高的）；条目 `fedora-7.2.15-10.opd2413`、`fedora-7.2.15-9.opd2413`（回退，参数相同）。
  ESP 空闲约 268 MiB；固定路径 `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb` 是 7.2.15 的（与内核 3 相同）。
- `boot_b` = `07bf1b53…`（fedora1：菜单 ColorOS / Fedora / Fedora boot menu，倒计时 10 s，默认项仍是 ColorOS）；KSHIM.CHO 记住 Fedora。
  上一版 `492f2cdf…` 的整分区回读在主机 `private/bootflow-20261111/boot_b-readonly.img`。
- 软件包：`kernel-opd2413-7.2.15-10`、`7.2.15-9`，`opd2413-device-0.1-14`、`opd2413-audio-0.1-12`、`opd2413-sensors-0.1-1`、`opd2413-firmware-16.0.10.600-2`、`showtime`（registry 在 `/var/lib/opd2413/sensors`）。`installonly_limit=2`：再装一个内核会卸掉 7.2.15-9。
  内核 3（`7.2.6-3`）08:45 经用户同意卸载，它的包仍在主机 `out/rpms/`。
- 7.3 测试内核、"M3 test" 和 "Log capture" 两个条目、ESP 上的 `opd2413-bootlog/` 已于 11-11 23:29 删除（备份在 `/var/tmp/opd2413/m3k-install-*/`）。
- `/etc/modprobe.d/opd2413-pps.conf` 已删除（11-12）。`/etc/kernel/tries` 已删除。
- `/var/lib/opd2413-pstore/` 下有 6 个按启动命名的记录目录。
- SELinux enforcing，firewalld 运行中（public 区）。sshd 只允许密钥登录；2026-11-12 起 firewalld 不再对所有来源开放 ssh，只放行家里局域网的 /24 网段和 IPv6 链路本地（rich rule，已持久化）。
  换网络后 SSH 进不来时，在平板上用 `firewall-cmd --zone=public --list-rich-rules` 查、按新网段改。
- 自动登录到 `colin`，自动锁屏已关；KDE 空闲熄屏已恢复默认。显示模式只有 120 Hz。
- sda17（`ARMADA_BOOT`）：未挂载、clean；保留旧 `/boot` 文件和 `opd2413-bootlog/` 下 11-11 的采集日志（都已取回主机）。
  16:36 的整分区备份在主机。分区表、Android 各分区未改动。
- 2026-11-12 清理：`/var/tmp/opd2413/`（约 948 MB 实验备份、安装包副本、录音，证据已在主机 `private/`）和旧的 pstore 记录目录已删除；pstore 记录改为只保留最新 20 份（设备包 0.1-14）。

## 主机上的产物（都在忽略目录里，不进仓库）

| 路径 | 内容 |
|---|---|
| `out/rpms/` | 四个软件包和 `SHA256SUMS`（内核 3 和设备包 0.1-5，比平板上的旧；现用的在 `out/rpmbuild/RPMS/`） |
| `out/old-rpms/` | 以前的内核包（1、2、opd1、diag1、diag2），2 是平板上的回退内核 |
| `out/pkg-test/`、`out/qemu-test/` | 两个离线测试的证据 |
| `private/esp-20261110/esp-sda16.img` | ESP 整分区备份（含 `KSHIM.CHO`） |
| `out/kernel-tree/` | kern2 源码树的副本 + 1411/1412 + `fedora-netfilter-lsm.config`，见 kernel/README.md |
| `private/display-*` | 黑屏排查的证据和抓取脚本 |
| `private/bootlogs/` | `tools/bootlog/fetch-bootlogs.py` 每次取回的日志（pstore、sda17 采集文件、内核 journal） |
| `private/m3-exp12-20261111/`、`m3-exp13-…`、`m3-exp14-…` | 第 12–14 次的脚本和记录；第 13 次的含 7.3 启动的完整 journal |
| `out/m3k/` | 7.2.15 源码树（git，分支 `series3`，可由 `tools/kernel/apply-armada-series.sh` 重现）、`build.sh`、构建和测试日志 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-1.opd2413.aarch64.rpm` | 平板上的默认内核 |
| `private/m3k-install-20261111/` | 7.2.15 装机和冷启动复查的证据 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-2.opd2413.aarch64.rpm` | 平板上的默认内核（M3.1 蓝牙）；`out/m3k/rpms2/`、`pkg-test2/` 是它的离线测试 |
| `private/m3-bt-20261112/` | M3.1 蓝牙的对照、安装、用户实测和冷启动证据 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-3.opd2413.aarch64.rpm` | 平板上的默认内核（M3.2a）；`out/m3k/rpms3/`、`pkg-test3/` 是它的离线测试 |
| `private/m3-batt-20261112/` | M3.2a 的安装、读数、拔插采样和冷启动证据 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-4.opd2413.aarch64.rpm` | 平板上的默认内核（M3.2b PPS）；`out/m3k/rpms4/`、`pkg-test4/` 是它的离线测试 |
| `private/m3-pps-20261112/` | M3.2b 的安装、挂起、冷启动证据 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-5.opd2413.aarch64.rpm` | 平板上的默认内核（M3.4b 摄像头）；`out/m3k/rpms5/`、`pkg-test5/` 是它的离线测试 |
| `private/m3-cam-20261112/` | M3.4b 的安装、相机抓帧统计、麦克风测试 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-10.opd2413.aarch64.rpm` | 平板上的默认内核（M3.5/M3.6）；`out/rpmbuild/RPMS/noarch/opd2413-device-0.1-11`、`opd2413-audio-0.1-12` |
| `out/rpmbuild/RPMS/aarch64/opd2413-sensors-0.1-1.aarch64.rpm`、`out/sensors/` | 传感器包及其源码包、构建日志 |
| `private/sensors-persist-20261102/` | 从 persist 备份导出的传感器 registry（本机数据） |
| `private/m3-sensors-20261112/` | 传感器安装、读数、挂起证据 |
| `private/m3-mic-20261112/` | 麦克风排查全过程：录音统计、寄存器转储、实验 DTB、坏录音样本 |
| `out/m3-rpm5/` | 诊断内核 `7.3.3-5.opd2413` 的构建脚本和日志（编译完成，19:50 在打包前中止，没有包） |
| `out/rpmbuild/RPMS/noarch/opd2413-device-0.1-13.noarch.rpm` | 平板上现在装的设备包（0.1-9 起允许 s2idle，0.1-10 修 boot-select 的条目 id，0.1-11 加键盘 hwdb，0.1-13 VP9 走软解） |
| `out/rpmbuild/RPMS/noarch/opd2413-firmware-16.0.10.600-2.noarch.rpm` | 平板上的固件包（加 Iris 固件） |
| `out/video/`、`private/m3-video-20261112/` | 视频测试片源、解码记录 |
| `private/m3-sleep-20261112/` | M3.3 的 pm_test、s2idle、按键挂起证据 |
| `private/ssh.sh`、`private/scp.sh` | 连平板的 SSH / scp 包装（`OPD_OS=fedora` 用 Fedora 的地址和主机密钥） |
| `private/install.env` | 用户给的初始密码 |

## 里程碑

| 里程碑 | 目标 | 状态 |
|---|---|---|
| M0 | 立项：决定、仓库、架构和进度文档 | 完成（2026-11-10） |
| M1 | Fedora 45 KDE 用现有 7.2.6 内核从机内启动，功能与 Armada 持平，然后取代 Armada | 完成（2026-11-11） |
| M2 | 运行中面板重新打开黑屏（已修）；标准化：SELinux、防火墙、每条目 DTB、内核升级和回滚流程（[KERNEL-UPDATE.md](KERNEL-UPDATE.md)）都已完成；开机提示音毛刺待再现 | 基本完成 |
| M3 | 在 7.2 内核（基线 7.2.15）上逐项合入 erhai 的功能：蓝牙、电池与充电、休眠与按键、传感器、摄像头、视频硬解（[M3-FEATURES.md](M3-FEATURES.md)） | 完成（2026-11-12）：基线 7.2.15、蓝牙、电池与 9 V 充电、休眠与按键（含睡深）、摄像头、麦克风、键盘、传感器、视频硬解都真机通过；PPS 快充（M3.2b）驱动就绪、缺 PPS 充电器未实测 |
| M4 | 外设逐项验收和长尾问题（灰闪、USB 3 方向、DP 音频等） | 未开始 |
| M5 | 维护：软件包自动重建、ColorOS OTA 后恢复流程、对外文档 | 未开始 |
| M6 | 内核基线跟到 Fedora 45 的当前内核（7.3.x 或更新），原 M3（[M3-KERNEL.md](M3-KERNEL.md)） | 暂停（2026-11-11）：跳过 GPU 时真机启动；带 GPU 时真机失败（GMU 启动时复位） |

### M1 步骤

| 步 | 内容 | 碰设备 | 状态 |
|---|---|---|---|
| 1.1 | 只读取证：ESP 备份和现有启动条目、内核产物和配置核对 | 只读 | 完成 |
| 1.2 | `kernel-opd2413` RPM（原样打包 `kern2`）；容器里验证 `kernel-install` 布局 | 否 | 离线通过 |
| 1.3 | `opd2413-firmware` RPM：62 个原厂固件 + 9 个 WCN7860 固件，逐文件校验哈希 | 否 | 离线通过 |
| 1.4 | `opd2413-device` 与 `opd2413-audio` RPM：ufs-guard、dracut 早期固件、kernel-install 插件、UCM、拓扑 | 否 | 离线通过 |
| 1.4b | QEMU：平板同款 U-Boot + 真实 ESP 副本 + Fedora 条目，systemd-boot 启动内核 | 否 | 离线通过 |
| 1.5a | 在运行中的 Armada 里只读核对安装前提 | 只读 | 完成 |
| 1.5b | 在运行中的 Armada 里把 Fedora 45 KDE 原生安装到新子卷 `fedora`、`fedora-home` | 写 `ARMADA_ROOT` | 完成（2026-11-10） |
| 1.6 | 移除两套 Armada 回滚部署腾出 ESP 空间，安装内核和设备包，加入 Fedora 条目，默认项仍是 Armada | 写 ESP、Armada 的 ostree | 完成（2026-11-10），Armada 重启验证通过 |
| 1.7 | 首次启动：kShimC 选 "Armada boot menu" → 手选 Fedora；按验收清单检查；冷启动回归 | 启动 | 完成（2026-11-10） |
| 1.8 | 切换默认项为 Fedora；换 systemd-boot 262；删除 Armada 的子卷和 ESP 上的文件 | 写 ESP 和 `ARMADA_ROOT` | 完成（2026-11-11） |

1.5–1.8 的路线、写入范围和判据见 [M1-INSTALL.md](M1-INSTALL.md)。

M1 验收清单（Fedora 下逐项真机确认）：进入 Plasma 桌面；触控和多点；KWin 使用 Adreno 830 硬件渲染；
Pogo 键盘和触控板；Wi-Fi 联网；扬声器播放；亮度调节；`systemctl --failed` 为空；
Android 分区在 Linux 下只读；重启回 ColorOS 正常。

## 功能状态（Fedora 下）

Armada 下的结论见 [HARDWARE.md](HARDWARE.md)。换了发行版后都要重验，所以这里从头记。

| 功能 | 状态 | 说明 |
|---|---|---|
| 启动链（kShimC → U-Boot → systemd-boot） | 真机通过 | Fedora 的 ESP 布局 + systemd-boot 262；多次关机重启均正常 |
| 机内启动 Fedora | 真机通过 | 2026-11-10/11，首次启动和 6 次关机重启均 `running`、失败单元 0 |
| 显示、背光 | 真机通过 | 开机显示、亮度调节正常；熄屏后亮屏恢复（内核 `1411`，用户目视确认多次）。只有 120 Hz：60/30 Hz 黑屏（`1412` 已去掉这两个模式），见 WORKLOG 2026-11-11 |
| 触控 | 真机通过 | 用户确认触屏正常（2026-11-10）；面板重新 prepare 后触控固件也能重新下载 |
| GPU 硬件渲染 | 真机通过 | Fedora 原版 Mesa 26.2.6：KWin 用 OpenGL ES 3.2 / Adreno 830（freedreno），Vulkan 为 turnip；不需要带补丁的 Mesa |
| Pogo 键盘、触控板 | 真机通过 | 用户确认打字和触控板正常（2026-11-10）；日志有 libinput "touch jump" 警告 |
| Wi-Fi | 真机启动 | 开机自动连上家里的 Wi-Fi，SSH 可用（2026-11-10）；HE 160 MHz 2161 Mbit/s，省电模式开（默认），ping 丢包 0、4–22 ms（2026-11-11）；断线重连和长时间传输未测 |
| 扬声器 | 真机通过 | 用户确认播放、音量调节、静音正常（2026-11-10）；左右与逐颗未单独验 |
| 麦克风 | 真机通过 | 2026-11-12，7.2.15-10（`2407`）+ opd2413-audio 0.1-12，见 M3-FEATURES M3.5 |
| 蓝牙 | 真机通过 | 2026-11-12，7.2.15-2 起：音箱、耳机配对/连接/播放（M3.1） |
| 休眠 | 真机通过 | 2026-11-12：s2idle，电源键/合盖/RTC 唤醒，挂起时 CX 塌陷约 98 %（M3.3）；拔线待机耗电未测 |
| 充电（9 V PD） | 真机通过 | 2026-11-12，7.2.15-3 起（M3.2a）；PPS 快充驱动已装、待电量低于 75 % 实测（M3.2b） |
| 电量、温控 | 真机通过 | 电量、电流（符号正确）、温度读数正常（M3.2a）；温控未单独验 |
| 传感器、自动旋转 | 真机通过 | 2026-11-12，opd2413-sensors（M3.4c）：自动旋转、环境光、指南针、陀螺仪；KDE 无自动亮度 |
| 摄像头 | 真机通过 | 2026-11-12，7.2.15-5 起（M3.4b）：前后摄预览/拍照/录像；无自动对焦、无调校 |
| 视频硬解 | 真机通过 | 2026-11-12（M3.4a）：固件 600-2 后 GStreamer 硬解 H.264/HEVC，Showtime 为默认播放器；VP9 走软解；mpv/Firefox 仍软解（ffmpeg-free） |
| DP 外接显示 | 有源码线索 | erhai |
| USB 3 双向 | 待调研 | |
| 合盖、电源键、音量键 | 真机通过 | 合盖/电源键挂起唤醒（M3.3）；音量键正常；键盘 Esc、麦克风键、锁屏键（M3.6）。拔线时关机不会自动开机 |
| SELinux enforcing | 真机通过 | 内核 3 加入 selinux；首启 relabel 23 s；permissive 和运行中 enforcing 下用户试用触控、键盘、声音、亮度、浏览器、设置均无拒绝；改为开机 enforcing 后冷启动 AVC 0（2026-11-11） |
| 防火墙 | 真机启动 | firewalld `running`，public 区绑定 wlp1s0；SSH 可连；规则本身未逐条验证 |
