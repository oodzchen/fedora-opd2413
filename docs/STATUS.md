# 实现进度

状态词：待调研、有源码线索、离线通过、真机启动、真机通过、真机失败。
"未开始"只用于还没动手的工作步骤。

## 唯一的下一步

**M3a：查清 7.3 内核在平板上为什么启动后很快复位**。下一个实验（待用户同意）：给 ESP 上的测试启动项
`opd2413-m3test.conf`（7.3.3-3）加上 `earlycon=efifb keep_bootcon`，使参数与唯一一次越过复位的那次完全相同。
越过了：说明 earlycon 影响结果，而且屏幕上能看到后面的日志；仍复位：问题在 7.3.3-3 相对 7.3.3-2 的唯一改动 SHM bridge 上。
所有上机记录和已排除的假设见 [WORKLOG.md](WORKLOG.md) 2026-11-11"M3a 上机"一节。
M2 剩下的被动观察项：开机提示音毛刺再出现时当场取证；空闲自动熄屏能否恢复。

## 当前阻塞

7.3 内核在平板上起不来：选中后黑屏或红字后几秒内整机复位；唯一一次越过（7.3.3-2 + earlycon）在约 10 秒后黑屏卡死，
SSH 连不上。复位后没有任何日志可读（ramoops 在这台机器上重启后不保留，见 WORKLOG）。内核 3 不受影响，是默认项。

## 接手时先做这几件事

1. 读本文件；需要了解启动链和安装过程时读 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [M1-INSTALL.md](M1-INSTALL.md)。
2. 平板默认就进 Fedora（kShimC 菜单里的 "Armada" 项）。SSH：`OPD_OS=fedora private/ssh.sh`，
   拷文件 `OPD_OS=fedora private/scp.sh`；IP 变了设 `OPD_HOST`，或在局域网里扫 22 端口找。
3. 改了 `device/` 或任何 spec，按 [BUILD.md](BUILD.md) 重新构建、跑三个离线测试，再拷到平板用 `dnf install ./*.rpm` 装。
4. 关机会自动重新开机（插着电时）。需要重启验证时可以直接经 SSH `systemctl poweroff`，约 60 秒后回来。

## 设备状态（2026-11-11）

- 平板运行 Fedora 45 KDE，内核 `7.2.6-3.opd2413`（默认项，带 SELinux 和 Fedora 的 netfilter 配置）。
  `7.2.6-2.opd2413` 已卸载。设备包 `opd2413-device/audio-0.1-5`（`installonly_limit=2`）。
- 另装了测试内核 `kernel-opd2413-7.3.3-3.opd2413`：kernel-install 生成的条目已改名为 `opd2413-m3test.conf`
  （标题 "M3 test: 7.3.3-3 (no boot counter)"，排在菜单最后，不是默认项），参数去掉了 `quiet loglevel=3`、加了 `ignore_loglevel`。
  这个条目是手工改的，卸载该内核时 kernel-install 不会删它，要手动删。
- ESP 固定路径的 `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb` 已被 `95-opd2413-dtb` 插件换成 7.3 的 DTB（只给 U-Boot 用；
  每个条目用自己的 DTB，内核 3 不受影响）。回到只用内核 3 时，可对内核 3 重跑 `kernel-install add` 换回来。
- `/etc/modprobe.d/opd2413-pps.conf`：`options erhai_pps pps_enable=0`（只对 7.3 内核有意义）。`/etc/kernel/tries` 已删除。
- SELinux enforcing（`/etc/selinux/config`，启动参数里已没有 `enforcing=0`），firewalld 运行中（public 区）。
- 自动登录到 `colin`，自动锁屏已关；KDE 空闲熄屏已恢复默认。
- 显示模式只有 120 Hz。
- Armada 已完全删除；`boot_b`、分区表、Android 各分区未改动。
- 没有正在运行的设备任务。kShimC 记住的菜单项可能是 "Armada boot menu"（会停在 systemd-boot 菜单）。

## 主机上的产物（都在忽略目录里，不进仓库）

| 路径 | 内容 |
|---|---|
| `out/rpms/` | 四个软件包和 `SHA256SUMS`，与平板上装的一致（内核 3） |
| `out/old-rpms/` | 以前的内核包（1、2、opd1、diag1、diag2），2 是平板上的回退内核 |
| `out/pkg-test/`、`out/qemu-test/` | 两个离线测试的证据 |
| `private/esp-20261110/esp-sda16.img` | ESP 整分区备份（含 `KSHIM.CHO`） |
| `out/kernel-tree/` | kern2 源码树的副本 + 1411/1412 + `fedora-netfilter-lsm.config`，见 kernel/README.md |
| `private/display-*` | 黑屏排查的证据和抓取脚本 |
| `private/ssh.sh`、`private/scp.sh` | 连平板的 SSH / scp 包装（`OPD_OS=fedora` 用 Fedora 的地址和主机密钥） |
| `private/install.env` | 用户给的初始密码 |

## 里程碑

| 里程碑 | 目标 | 状态 |
|---|---|---|
| M0 | 立项：决定、仓库、架构和进度文档 | 完成（2026-11-10） |
| M1 | Fedora 45 KDE 用现有 7.2.6 内核从机内启动，功能与 Armada 持平，然后取代 Armada | 完成（2026-11-11） |
| M2 | 运行中面板重新打开黑屏（已修）；标准化：SELinux、防火墙、每条目 DTB、内核升级和回滚流程（[KERNEL-UPDATE.md](KERNEL-UPDATE.md)）都已完成；开机提示音毛刺待再现 | 基本完成 |
| M3 | 内核升到 Fedora 45 的当前内核（7.3.3），以 erhai v0.7.2 为设备改动主体，合入休眠、充电、蓝牙、相机、传感器（[M3-KERNEL.md](M3-KERNEL.md)） | 进行中：离线通过，真机失败（启动后复位），排查中 |
| M4 | 外设逐项验收和长尾问题（灰闪、USB 3 方向、DP 音频等） | 未开始 |
| M5 | 维护：软件包自动重建、ColorOS OTA 后恢复流程、对外文档 | 未开始 |

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
| 麦克风 | 待调研 | |
| 蓝牙 | 有源码线索 | erhai |
| 休眠 | 有源码线索 | erhai；M1 期间禁用 |
| 充电（9 V PD） | 有源码线索 | erhai |
| 电量、温控 | 有源码线索 | |
| 传感器、自动旋转 | 有源码线索 | erhai |
| 摄像头 | 有源码线索 | erhai |
| 视频硬解 | 真机失败 | 缺 `qcom/sm8750/erhai/vpu35_4v.mbn`（Armada 下同样失败）；固件在原厂 OTA 的 vendor 里，erhai 已收录 |
| DP 外接显示 | 有源码线索 | erhai |
| USB 3 双向 | 待调研 | |
| 合盖、电源键、音量键 | 有源码线索 | erhai；关机后插着电会自动重新开机，待拔线复测 |
| SELinux enforcing | 真机通过 | 内核 3 加入 selinux；首启 relabel 23 s；permissive 和运行中 enforcing 下用户试用触控、键盘、声音、亮度、浏览器、设置均无拒绝；改为开机 enforcing 后冷启动 AVC 0（2026-11-11） |
| 防火墙 | 真机启动 | firewalld `running`，public 区绑定 wlp1s0；SSH 可连；规则本身未逐条验证 |
