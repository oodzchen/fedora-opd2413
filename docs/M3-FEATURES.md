# M3：在 7.2 内核上逐项合入 erhai 的功能

2026-11-11 用户确认的路线（见 AGENTS.md 决定表）。取代原来的"M3 = 换到 Fedora 7.3.3 基线"，后者的记录和暂停时的状态在
[M3-KERNEL.md](M3-KERNEL.md)，现在是里程碑 M6。

## 为什么

- 要的是功能：休眠、9 V PD/PPS 充电、蓝牙、摄像头、传感器、合盖、视频硬解。它们都来自 erhai，而 erhai v0.7.2 基于 7.2.15，不需要 7.3。
- Fedora 45 发行时自带 7.2.11；用户态在 `7.2.6-3.opd2413` 上已真机验收（桌面、GPU 硬件渲染、SELinux、防火墙）。
  设备包排除了 Fedora 自己的内核包，`dnf upgrade` 不会换内核。
- 7.3.3 上 GMU 启动复位、Wi-Fi 扫不到 AP、声卡 deferred，三个问题都是 7.2→7.3 带来的；erhai 作者还没做 7.3，自己先做等于替上游踩坑。
- Fedora 在一个发行版内会持续换内核大版本，"跟 Fedora 基线"是每两三个月一次的持续成本，不是一次性的。

代价：7.2 系列的稳定版修复要自己跟（现在是 7.2.6，上游到 7.2.15）；内核配置不是 Fedora 的；7.2 停止维护后仍要跟到新版本。

## 做法

1. 基础是内核 3 的源码（`out/kernel-tree`：Armada 7.2.6 + `1411`、`1412`，见 `kernel/README.md`）。
2. 一次只加一个功能的补丁序列，构建成下一个 `7.2.6-<N>.opd2413`，按 [KERNEL-UPDATE.md](KERNEL-UPDATE.md) 上机；内核 3 始终留作回退项。
3. 每个功能有自己的判据，真机通过后才进功能表；不通过就退回上一个内核，不叠着往下做。
4. 取证用 [BOOT-LOGGING.md](BOOT-LOGGING.md) 的通道（ramoops 自动存档、`tools/bootlog/fetch-bootlogs.py`、短按电源取 journal）。
5. 引入的补丁保留原作者和来源提交，登记在 `kernel/PATCHES.md`。

## 初步评估（2026-11-11，只读，未验证）

erhai v0.7.2 相对它的 7.2.15 基础有 437 个非合并提交。逐个单独对内核 3 的源码试应用（`git apply --check`，互不叠加）：

| 结果 | 数量 | 含义 |
|---|---|---|
| 已存在 | 60 | 内核 3 已经有（Armada 的 `1400`–`1402`、`1408` 就是从 erhai 早期版本移植的） |
| 可直接应用 | 192 | 其中一大半是 erhai 顺带合入的上游稳定版修复（wifi、iio、smb、KVM、USB、mtd 等），与本机功能无关 |
| 冲突 | 185 | 多数是同一序列里依赖前一个提交造成的连带失败，要按序列顺序应用才知道真实冲突数 |

按功能粗分（关键词匹配，会有重叠和遗漏）：

| 功能 | erhai 提交数 | 单独试应用 | 备注 |
|---|---|---|---|
| 休眠（s2idle、suspend/resume、唤醒） | 约 37 | 10 已存在、8 可应用、19 冲突 | 含不少 `TEMP:` 诊断提交和它们的 revert，要挑最终状态 |
| 电池与充电（qcom_battmgr、PD、PPS、SC8547A） | 约 29 | 7 可应用、22 冲突 | 明显是一个前后依赖的序列 |
| 蓝牙 | 很少 | 1 可应用、1 配置 | 主要是设备树和配置；第 13 次启动里 erhai 的设备树下 `hci0` 初始化成功 |
| 摄像头（camss、传感器驱动、CSI PHY） | 约 40 | 多数冲突 | 新驱动为主，冲突应是连带的 |
| 设备树 | 71 | 62 冲突 | 两边的板级 dts 文件名不同（`sm8750-oneplus-pad2pro.dts` 对 `sm8750-erhai.dts`），要逐项移过去 |

这张表只说明量级，不是工作量结论。**第一件事是把每个功能的提交挑成有序序列，在内核 3 源码的副本上顺序试应用**，得到真实的冲突清单。

## 顺序（2026-11-11 用户确认）

| 序 | 内容 | 理由 |
|---|---|---|
| 1 | 蓝牙 | 改动最小，验证"挑序列→构建→上机→验收"这条流程 |
| 2 | 电池读数、9 V PD，再到 PPS 快充 | 日常最有用；序列完整；PPS 单独一步，先关着 |
| 3 | 休眠（s2idle）和唤醒，随后合盖、电源键、音量键 | 收益大、风险也最大，放在流程跑顺之后；做完可去掉技术债 #8 和部分 #1 |
| 4 | 传感器与自动旋转、摄像头、视频硬解（补 `vpu35_4v.mbn`） | 互相独立，按需要排 |

第 0 步（用户确认）：先把基线从 7.2.6 升到 7.2.15，与 erhai 的基础对齐；补丁不变，只换基线。要先离线确认 Armada 的补丁序列在 7.2.15 上能应用。
它是独立的一步，真机通过后再开始第 1 项。2026-11-11 离线通过，见 [kernel/opd2413-7.2/README.md](../kernel/opd2413-7.2/README.md)；
2026-11-12 真机通过（`7.2.15-1.opd2413` 为默认内核，冷启动复查通过，记录见 WORKLOG）。

## M3.1 蓝牙（2026-11-12 真机通过）

现状（7.2.15-1，只读查看）：`hci0` 起来了，WCN7860 固件 `qca/gngbtfw20.mbn`、`gngbtnv20.bin` 加载成功，bluetoothd 运行，rfkill 没有阻断；
BD 地址由 Armada `0501`（ROCKNIX）按设备序列号生成，每次相同。开机后控制器是关着的（`Powered: no`），还没有试过打开、扫描和配对。
蓝牙设备树节点与 erhai v0.7.2 完全相同。

erhai v0.7.2 相对 7.2.15 与蓝牙有关的改动只有三处：

| erhai 提交 | 内容 | 处理 |
|---|---|---|
| `5fbc7cbd1` FROMLIST: hci_qca 断电时复位 IBS 睡眠状态 | 2 s 内关开、或开机后用户态马上设地址时，命令超时、控制器被重置（`Frame reassembly failed (-84)` 后 `-110`） | 刷新注释上下文后引入为 `2001` |
| `eb313ec77` 配置：BT_LE、RFCOMM、RFCOMM_TTY、BNEP、UHID | 桌面要用的协议 | 内核 3 已有 BT_LE、RFCOMM、HIDP、UHID；补 `RFCOMM_TTY`、`BNEP`（模块） |
| `67cdfbca6` 恢复合并时被截掉的 hci_qca.c 尾部 | erhai 自己的合并事故修复 | 不需要：本树的 hci_qca.c 完整，另有 erhai 没有的 WCN7750 支持（Armada `1166`） |

`7.2.15-2.opd2413` 离线核对：配置与 7.2.15-1 只差 `BT_RFCOMM_TTY`、`BT_BNEP` 和两个过滤选项；DTB 相同；模块只多 `bnep.ko`；
`tests/package-install-test.sh` 通过（initramfs 66 个设备固件齐全）。

真机：对照测试里 7.2.15-1 快速关开 5 次都正常（`5fbc7cbd1` 的故障在本机没复现，修复是预防性的）；7.2.15-2 上用户用一个蓝牙音箱和一个蓝牙耳机配对、连接、断开、播放都正常，冷启动复查通过。7.2.15-2 是默认内核（WORKLOG 2026-11-12"M3.1 蓝牙"）。没测的：BNEP 网络共享、蓝牙键盘鼠标、通话（HFP）。

注意：本机 7.2.15-1 开机日志里也有一次 `Frame reassembly failed (-84)`（下载固件时），之后 setup 成功；是否会出现 `5fbc7cbd1` 描述的超时，要上机先在 7.2.15-1 上试一次关开作对照。

## M3.2 电池与充电（2026-11-12，M3.2a 真机通过，M3.2b 离线通过）

现状（7.2.15-2，只读查看）：电量、电压、电流、温度、健康度、满充容量都能读，upower 正常。问题：

- 插着 PD/PPS 充电器（UCSI 报 `PD`、`PD_PPS`）只按 5 V 充（USB 侧约 4.8 V、1.3 A），`qcom-battmgr-usb` 的 `usb_type` 显示 `SDP`。
- 电池节点有可写的 `charge_control_start/end_threshold`。按 erhai `68d5b3b62` 的分析，上游 SM8550 的阈值实现会发 0x48 请求、读写属性 25/26，
  而本机固件（SM8550 协议加 OPLUS 扩展）把它们用作 `BC_VOOC_STATUS_GET`、`BATT_SET_PDO`、`BATT_SET_QC`。现在没有东西写它（KDE 电池保养上限没设），但一写就是未知行为。
- `current_now` 符号与电源类约定相反；`power_now` 是固件里一个与电池功率无关的数（erhai `49cb36105` 实测）。

erhai 的做法：`qcom_battmgr.c` 上 21 个提交（读数修正、阈值改用 OPLUS 属性 24、USB 外设供电、固定 9 V PD、USB 类型、充电通知不唤醒、PPS 挂钩），
PPS 本身在单独的 `erhai_pps`、`sc8547a` 驱动里（另有手写笔充电 `cps8601`，不在范围内）。这段历史经过一次 7.2.10 合并和补回截断（`67cdfbca6`），
在 7.2.15 上不能逐个重放（顺序试应用：8 个可应用、3 个要模糊、17 个冲突）。最终文件在本树上单独就能编译（W=1 无警告），所以整文件引入为 `2101`。

分两步：

| 步 | 内容 | 版本 |
|---|---|---|
| M3.2a | `2101`：battmgr 整文件；PPS 驱动不编译，只有固定 9 V PD | `7.2.15-3` |
| M3.2b | PPS：`2102`（wcd939x-usbss，erhai `af5949fb9` 的这部分）、`2103`（`sc8547a`、`erhai_pps` 整文件，含 12–44 °C 温度窗口），配置为模块；板级 DTS 里两个 SC8547A 节点 Armada 已经有了 | `7.2.15-4` |

M3.2a 真机结果：快充充电器上开机 2 s 内协商到固定 9 V（8.94–8.98 V，输入上限 2 A）；电脑 USB 口只有 5 V，驱动正确地留在 5 V；
电流符号正确（拔电 −0.8 至 −1.0 A）；`power_now` 消失。附带变化：电池节点名 `battery` → `qcom-battmgr-bat`，不再导出 `charge_now`、
`constant_charge_current*`（技术债 #33）。没测：USB 外设供电、充电阈值写入。

另有 UCSI 的四个修复（`522a9444a`、`91d87a2c4`、`8f3bbe849`、`836663239`）能严格应用，这一步不带，需要时单独加。

## M3.3 休眠与按键（2026-11-12 真机通过）

现状（7.2.15-3，只读）：`/sys/power/state` 为 `freeze mem disk`，`mem_sleep` 为 `s2idle [deep]`（固件广告 PSCI SYSTEM_SUSPEND，内核默认选 deep）；
设备包 `90-opd2413-no-suspend.conf` 禁止了所有睡眠（技术债 #8），logind 报 CanSuspend=no；logind 是默认的 `HandlePowerKey=poweroff`、`HandleLidSwitch=suspend`；KDE 接管电源键，用户的设置是插电时电源键熄屏（`PowerButtonAction=64`）。
按键硬件已经齐了：板级 DTS（Armada）里有 `gpio-keys`（音量减、霍尔开关报 `SW_LID`）、`pon_resin` 作音量加、`pmic_pwrkey`；`gpio_keys.c` 与 erhai 相同。
交换区是 Fedora 默认的 zram 8 GiB（`min(ram, 8192)`），没有磁盘交换区。

erhai 的做法（`onepluspad-2pro-mainline/docs/SUSPEND.md`）：只用 s2idle，cmdline 固定 `mem_sleep_default=s2idle`（deep 下 ADSP 的 IPCC 消息会让整机完全醒来）；
实测 CX 塌陷和 DDR 自刷新驻留约 98 %，电源键、RTC、合盖（霍尔开关 `msmgpio 97`）可唤醒；不做 hibernation（休眠到磁盘）。

按文件比较本树与 erhai v0.7.2（两边都基于 7.2.15）：erhai 改过的 221 个文件中，47 个与本树相同（含 `gpio_keys.c`、`oneplus-pogo-keyboard.c`、`tsens.c`），
103 个本树还是 7.2.15 原样，71 个两边各改各的（多是显示、GPU、音频、ath12k，Armada 序列也改过）。
与挂起/恢复相关、本树缺的改动分布在：板级 DTS（PCIe WAKE# 等；霍尔开关和音量加本树已有）、gcc-sm8750 的 PCIe GDSC、pcie-qcom 和 QMP PHY 唤醒通路、
pmdomain 性能态恢复、clk、dwc3-qcom（挂起期间推迟 VBUS 覆盖）、qcom-geni 串口、LPASS 宏和 SoundWire、DPU/DSI 运行时 PM、a6xx 挂起后的 rpmh 投票、ufs、
以及配置（挂起卡住时 panic、hung task 检测）。数量大、跨子系统，不能一次全上。

真机（7.2.15-3，WORKLOG 09:15 起）：`pm_test` 三级都通过；一次真正的 s2idle 60 s 由 RTC 唤醒、恢复正常，但 `cxsd`/`ddr` 计数为 0（只到 CPU 空闲）。

拆成两步：

| 步 | 内容 |
|---|---|
| M3.3a（真机通过） | 用户可用的挂起：启动参数加 `mem_sleep_default=s2idle`，去掉设备包的禁止休眠配置，电源键和合盖接到挂起，验证电源键、合盖、RTC 唤醒和恢复后的外设 |
| M3.3b（真机通过） | 睡深：逐个去掉 `clk_ignore_unused`、`pd_ignore_unused`、`regulator_ignore_unused`（技术债 #1），按需合入 erhai 的 PCIe/LPASS/pmdomain 等挂起改动，以 `qcom_stats` 的 CX 塌陷驻留为判据 |

M3.3a 实际做法：设备包 0.1-9 的 `90-opd2413-sleep.conf`（`MemorySleepMode=s2idle`），没改启动参数；电源键、合盖动作由用户在 KDE 电源管理里设为睡眠。
电源键 2 次、合盖 3 次、`systemctl suspend`+RTC 1 次，全部 s2idle、失败 0、唤醒源正确、恢复后外设正常（WORKLOG 09:30 起）。

M3.3b 实际结果：去掉三个 `*_ignore_unused` 后功能正常但 CX 仍不塌陷；真正的阻塞是 `sync_state() pending`——相机 ISP（`ad27000.isp`）、两个 CSI PHY、GPU 的 GMU 没有驱动，interconnect、RPMh 电源域、gcc 等一直保持开机时的最大投票。加 `fw_devlink.sync_state=timeout`（启动约 10 s 后强制 sync_state）后，60 s 挂起里约 59.5 s CX 塌陷、DDR 自刷新。键盘按键不能唤醒（2026-11-12 查明，与 erhai 相同）：`oneplus-pogo-keyboard` 在挂起时给已连接的键盘发休眠命令，只在没接键盘时把检测脚（gpio96）设为唤醒中断（接上键盘会唤醒）；键盘走 UART（`880000.serial`），挂起期间没有任何来自键盘的唤醒中断（`serial0-0` 的 wakeup 计数一直是 0）。原厂驱动按显示状态让键盘睡/醒。要支持按键唤醒，得先确认睡眠中的键盘按键时会不会在 UART 上发数据，再把 UART RX 脚设成唤醒中断（geni 串口支持），并防误唤醒。现在能唤醒的是电源键、开盖、RTC。

现行启动参数：没有 `*_ignore_unused`，有 `fw_devlink.sync_state=timeout`（技术债 #34：等相机 ISP/CSI PHY 驱动（M3.4）和 GMU 驱动绑定（erhai `6f237b23c` 等）合入后去掉）。

## M3.4 传感器、摄像头、视频硬解（2026-11-12 真机通过）

erhai v0.7.2 的状态（`onepluspad-2pro-mainline` README）：视频硬解（Iris，H.264/H.265/VP9，GStreamer 和 Firefox VA-API）✅；前后摄（SC820CS/SC1300CS，libcamera）🟡 能预览拍照、
画质未调；自动旋转、环境光、指南针、陀螺仪（SSC）✅，接近传感器本机没有。

| 子项 | 内核 | 固件 | 用户态（Fedora 45） | 备注 |
|---|---|---|---|---|
| 视频硬解 | iris 20 个文件 +186/−36（本树与 erhai 各改各的，要逐个合） | `qcom/sm8750/erhai/vpu35_4v.mbn`，主机上没有，要从设备的原厂分区只读提取 | GStreamer v4l2 解码在 Fedora 里有；Firefox 的 VA-API 要 erhai 的 `iris-vaapi` | 现在每次挂起/恢复都在找这个固件（日志噪声） |
| 摄像头 | camss、CSI PHY 驱动、两个传感器驱动、对焦马达 `cn3927`，共约 +4900 行 | 无 | Fedora 有 libcamera 0.7.2（软件 ISP），可能要 erhai 的调校文件 | 合入后相机 ISP/CSI PHY 有了驱动，可以去掉 `fw_devlink.sync_state=timeout`（技术债 #34）；GMU 还要另外处理 |
| 传感器 | 基本不用改（FastRPC 已在） | 每台机器的 sensor registry 在 Android 的 persist 分区，只读复制 | Fedora 没有 `hexagonrpcd`、`libssc`；`iio-sensor-proxy` 3.9 没编 SSC 支持 → 要自己打三个包 | registry 必须在 ADSP 传感器域建立前就位；改动全在用户态 |

用户定的顺序：摄像头 → 传感器（视频硬解之后再说）。

摄像头（M3.4b，`7.2.15-5`）真机通过：erhai 的 46 个相机提交 `2301`–`2346`，libcamera 0.7.2（Fedora）simple 管线 + 软件 ISP，Snapshot 前后摄预览、拍照、录像正常，约 32 fps。已知限制：没有自动对焦、没有传感器调校（偏色、四角暗、画质低）。相机 ISP/CSI PHY 有了驱动后，interconnect、rpmhpd、camcc 的 sync_state 自然完成，技术债 #34 只剩 GMU。
录像无声音而是满幅噪音：麦克风采集本身坏了（见 WORKLOG 2026-11-12 M3.4b），另立"麦克风"一项。

## M3.4a 视频硬解（2026-11-12 真机通过）

只缺固件：`vpu35_4v.mbn`（OnePlus 签名，从 erhai 检出按哈希取得，进 `opd2413-firmware` 600-2 的清单）；现有内核的 iris 即可，没有合 erhai 的 iris 改动。
GStreamer 的 `v4l2h264dec`/`v4l2h265dec`/`v4l2vp9dec`/`v4l2av1dec` 注册，1080p30 10 s 片源解码约 0.35 s、几乎不占 CPU；`playbin` 自动选硬件解码。
Showtime（Fedora 源）设为默认视频播放器：H.264、HEVC 硬解流畅；V4L2 VP9 在播放器开播的刷新后停帧（erhai 同），设备包 0.1-13 用 `GST_PLUGIN_FEATURE_RANK=v4l2vp9dec:0` 让 VP9 走软解。
限制：mpv、Firefox 用 Fedora `ffmpeg-free`，没有 H.264/HEVC 硬解接口，仍是软解；可选方案 erhai 的 `iris-vaapi`（VA-API）或 RPM Fusion ffmpeg，用户暂不需要。

## M3.4c 传感器（2026-11-12 真机通过）

`packaging/opd2413-sensors/`：按 erhai-sensors 打 Fedora RPM（来源和改动见该目录 README）。私有前缀 `/usr/libexec/opd2413-sensors` 下的 hexagonrpcd、libssc、带 SSC 的
iio-sensor-proxy（Fedora 的 iio-sensor-proxy 文件不动，用 systemd drop-in 换 ExecStart），ROM 传感器配置从 erhai 检出读取并按哈希核对，
每台机器的 registry 从主机上的 persist 分区备份（11-02）只读导出（`private/sensors-persist-20261102/`，361 个文件）。
`tools/build-sensors-rpm.sh 0.1 1`：在 aarch64 Fedora 45 容器里构建，hexagonrpc 测试 19/19 通过、libssc 投递测试通过；私有库经 RUNPATH 解析。
平板上有 `/dev/fastrpc-adsp-secure`，Fedora 的 iio-sensor-proxy 已装（未运行）。

真机：导入 registry 并重启后三个服务 active、AVC 0；自动旋转方向正确（用户实测），环境光随遮挡变化（约 85 → 1 lux），指南针、陀螺仪可用；挂起时传感器流暂停、恢复后重启，CX 塌陷不受影响。KDE Plasma 6.8 没有环境光自动亮度（用户暂不需要）。

## M3.5 麦克风、M3.6 键盘（2026-11-12 真机通过）

麦克风：录到满幅噪音、且逐次启动时好时坏。根因：WCD939x 的 ADC1–4 共用一个 SoundWire 端口，`wcd939x_get_swr_port()` 按端口报告开关状态，
`alsactl` 保存/恢复混音器状态后 ADC2/ADC3 的通道位被置上，编解码器发 4 声道而 SoC 收 2 声道。修复：内核 `2407`（按声道报告和切换）+ UCM 打开麦克风时先关 ADC2/ADC3（opd2413-audio 0.1-12）。
排查中试过但不是原因的：erhai 的 lpass-tx/va-macro（`2401`，保留，带 HPF 控件）、整套 erhai 音频驱动（实验内核 7.2.15-7，已删）、TX SoundWire 端口布局（`2402`，已撤）、
ADSP 丢消息修复（`2404`–`2406`，保留，消除了开机的 `qcom-apm CMD timeout`）。

键盘：麦克风键发 F13、锁屏键发 F24 → 设备包 0.1-11 的 hwdb 映射为 `micmute`、`screenlock`；Esc 键固件发 AC Back → 内核 `2403` 报 `KEY_ESC`。
按住放大镜键时用户确认 F3/F6 可用。

## 回馈 erhai

用户同意把发现和修复同步给 erhai。每次提交前先问用户；不带序列号、MAC、UUID、IP 等本机数据。目前可整理的候选：

| 内容 | 状态 |
|---|---|
| 7.3.3 上的三个问题（GMU 启动时整机复位、ath12k 扫不到 AP、声卡 deferred）及取证方法 | 只有现象和定位范围，没有修复；对 erhai 作者做 7.3 时有参考价值 |
| ramoops 在本机可用，以及 systemd-pstore 会搬走并覆盖记录、`quiet` 下控制台区几乎为空这两个坑 | 已真机验证，可写成说明 |
| erhai 没有而本机验证过的修复：开机显示交接（Armada `1404`–`1407`、`1409`）、熄屏保持面板供电（`1411`） | 原作者是 Armada/本仓库，回馈时保留来源 |
| wcd939x 开关按端口报告导致多开声道（`2407`，wcd938x 同样写法） | 已真机验证，可提交上游/erhai |
| erhai `095062299` 的 TX 端口布局：单独不是麦克风坏的原因（与 `2407` 配合时 erhai 布局可用） | 已验证，回馈时说明 |
| 键盘：Esc 键（`2403`）、麦克风/锁屏键（hwdb） | 已真机验证 |
| 在 7.2 上合入各功能时发现的问题 | 随做随记到这里 |
