# 实现进度

状态词：待调研、有源码线索、离线通过、真机启动、真机通过、真机失败。
"未开始"只用于还没动手的工作步骤。

## 唯一的下一步

**`opd2413-netshare-0.1-10.noarch`（平板）与 `out/netshare/opd-netshare.apk`（手机，`114K`）已完成真机闭环验收：`p2p0` IPv6 双栈打通（`tailscale netcheck` `IPv6: yes`、`ping -6` / `curl -6` 通过）、多次开关切换稳定建连（BLE+RFCOMM `~1–2 s`），且手机在「伴侣关联 + 允许后台 + 最近任务锁卡」下可在长锁屏状态后台自动拉起连接（见 [WORKLOG.md](WORKLOG.md) 与 [TECH-DEBT.md](TECH-DEBT.md) `#40`/`#41`）。唯一的下一步：按用户节奏决定是否提交当前工作区改动，或继续内核 Batch 4 功耗排查（`a600000.usb`/`88e8000.phy`、`LPASS`/`SoundWire`、`aosd=0`）。**
- 2026-11-15 `7.2.15-28.opd2413` 根因修复与上机验证通过（见 [WORKLOG.md](WORKLOG.md)）：对 `-27` 首次冷启动卡死提取 `boot -1` 与反汇编，定位到 `sound/soc/qcom/qdsp6/q6dsp-lpass-clocks.c` 在 `dev_set_drvdata()` 前即通过 `devm_of_clk_add_hw_provider()` 公开时钟，并发探针的 `va_macro` 在 `clk_q6dsp_prepare()` 读取 `NULL + 0x348`（`struct q6dsp_cc.desc`）触发 Oops 并带 `clk_prepare_lock` 死锁；新增补丁 `2434` 将 `dev_set_drvdata()` 提前至时钟注册之前（`-F0` 合入、`pkg-test28` 通过）。卸 `-27`（保留 `-26` 为默认回退）并装 `-28` 后，经 `tools/tablet-reboot.py --entry fedora-7.2.15-28.opd2413.conf` `59 s` 上线：`uname -r = 7.2.15-28.opd2413`、`running`、`0 failed`、SELinux `Enforcing`、`0 AVC`、`dmesg` 零 Oops/`0x348`/`adsp` 崩溃、`aplay -l`/`opd2413-sensors-*`/`bluetooth`/`opd-netshare`/`Adreno 830`、`DPMS off/on` 断电复核与 5 s `s2idle` 均正常。
- 2026-11-15 功耗与续航 Batch 3（`7.2.15-27.opd2413`）真机通过（见 [WORKLOG.md](WORKLOG.md)；`-27` 因无 `2434` 出现冷启动竞态卡死，已由 `-28` 取代并卸载）：`2431`（erhai `5930568b2`）、`2432`（erhai `8ebec9278` 刷新上下文）与 `2433`（回退 `1411`）严格合入 7.2.15；将 `-26` 设默认回退并卸 `-25` 后装机，`-27` 一次性冷启动上线后完成 3 次 `kscreen-doctor --dpms off/on` 校验（灭屏 `lcd_vsp`/`lcd_vsn`/`vreg_l12b_1p8` 全部 `disabled`/`users=0`、亮屏重新下载 `nt36536` 固件且无 DSI/DPU/KTZ 报错）、30 s 拔线 `rtcwake -m mem -s 30`（`pm_wakeup_irq=242` `pm8xxx_rtc_alarm`、`cxsd`/`ddr` `30.87 s`、`aosd=0`）、用户目视确认画面与触控正常，并实测仅 `DPMS off` 即可使电池放电由 `~530–593 mA`（`2.33–2.60 W`）降至 `~113–135 mA`（`0.50–0.59 W`），`TECH-DEBT.md` `#19` 已解除。
- 2026-11-15 功耗与续航 Batch 2（`7.2.15-26.opd2413`）真机通过（见 [WORKLOG.md](WORKLOG.md)）：`2425`–`2430`（`c5590c6a0`、`81aafa28f`、`39636e8c3`+`f12f2ab7a`、`870167fad`、`627372bef`、`a1576b156`）+ `m3-3-power.config`（`CONFIG_HOTPLUG_PCI_PCIE=y`）严格合入 7.2.15；将 `-25` 设默认回退并卸 `-24` 后装机，仅调整 `-26` 启动条目 `options` 去掉 `fw_devlink.sync_state=timeout`/`pcie_ports=compat` 并添加 `mem_sleep_default=s2idle`，`58 s` 一次性上线：`/sys/power/mem_sleep` 为 `[s2idle] deep`、`pciehp`/`pcie_pme`/`aer` 就绪，30 s `rtcwake -m mem -s 30` 睡满无误唤醒、`cxsd`/`ddr` 各塌陷 `31.08 s`（`Count +3`）、`ddr_stats` 印证 DDR 不再锁死 `4224 MHz`、唤醒重连 Wi-Fi/蓝牙/GPU 全正常。
- 2026-11-15 功耗与续航 Batch 1（`7.2.15-25.opd2413`）真机通过（见 [WORKLOG.md](WORKLOG.md)）：`2418`–`2424`（`62ed205f1..6f237b23c`、`1055cf6dc`、`39919af08`）按 `-F0` 严格合入 7.2.15；卸掉 `-23` 后安装 `-25`（保留 `-24` 作回退默认项），在 `-25` 启动条目去掉 `fw_devlink.sync_state=timeout` 后一次性引导 `66 s` 上线：`3d37000.gmu` 绑定 `adreno_gmu`、全系统无 `waiting_for_supplier != 0`、`gpu_cc_cx_gdsc`/`gx_clkctl_gx_gdsc`/`gmxc`/`gfx` 空闲塌陷 `off-0`、`llcc_mc` 中 `3d00000.gpu` 在 active 下投票清为 `0/0`、`eglinfo`（Adreno 830）与 5 s `s2idle` 短休眠唤醒正常；`TECH-DEBT.md` `#34` 已标记实机验证可移除，待最终同步 `/etc/kernel/cmdline` 与默认条目后完全关闭。
- 2026-11-15 `opd2413-netshare 0.1-8` + Android APK 图标统一与 Wayland 窗口图标修复已完成装机与主要实测（见 [WORKLOG.md](WORKLOG.md)）：桌面与手机统一采用重采样且无透明白边的 `icon.png`（hicolor `48/64/128/256`、`tray_{black,green,yellow}.png` `128×128` 分别降噪压缩至 `2.5–37K` / `4.2–7.1K`；Android 5 档 `mipmap` + `432×432` 自适应前景 `6.0K` + 108dp `ic_launcher_monochrome` + 24dp 六边形通知/磁贴单色矢量 `ic_opd_share.xml`）。平板 `opd-netshare-tray` 新增 `app.setDesktopFileName("opd-netshare")` 与多尺寸 `setWindowIcon()`，`WAYLAND_DEBUG=client` 实测 `StatusDialog` 打开时向 KWin 发送 `xdg_toplevel.set_app_id("opd-netshare")` 及 `xdg_toplevel_icon_manager_v1.set_icon`（4 档 `wl_buffer`）；Qt 会话探针四态加载（`connected` `g=2124`）及 D-Bus SNI 实时切换 `idle`/`off`（`0.40x` 透明度）/`advertising`（`y=2034`）均通过（`connected` 实时 SNI 切换待手机亮屏建连时一并目视确认）；手机端 `opd-netshare.apk`（`90K`）已 `adb install -r` 覆盖升级且 `NetShareService` 前台通知正常。
- 2026-11-15 `kernel-opd2413-7.2.15-24.opd2413` 设默认启动并冷启动复查通过（见 [WORKLOG.md](WORKLOG.md)）：执行 `/usr/libexec/opd2413/boot-select default fedora-7.2.15-24.opd2413.conf` 并插电 `systemctl poweroff` 冷启动，`46.3 s` 后无干预回到 `7.2.15-24.opd2413`（`running`、`0 failed`、SELinux `Enforcing`、`0 AVC`、`country CN`、`opd-netshare` `Mode: auto`/`State: idle`，`7.2.15-23` 保留作回退入口）。
- 2026-11-15 `opd2413-netshare 0.1-7` + Android 伴侣端联调修复真机通过（见 [WORKLOG.md](WORKLOG.md)）：针对手机忘记蓝牙重配对并断开平板 Wi-Fi 后无法共享的问题，修复平板 `opd-netshare-daemon` 在 `hci0` 掉电/重配对后未监听 `Adapter1.Powered` / `Device1.Paired` 及未校验 `LEAdvertisement1` `ActiveInstances` 导致广播静默丢失、以及手机 `ACTION_BOND_STATE_CHANGED`（`BOND_BONDED`）未清冷却重扫的缺陷；同时新增 `last_wlp_5g_freq` 断网信道记忆、`failed_freqs` 冷却与基于手机 `sta_freq` 的同会话 `peer_sta_freq` 跨频段选频（配合伴侣端 `failCount < 5` 与 `14_000L` ms 等待）。真机实测 `bluetoothctl power off` 与 `rfkill` 自愈建连（`CURL_HTTP=200`）、`mode auto` 断开 `wlp1s0` 沿用 `5240 MHz` 建连（`1200.9 MBit/s`、`CURL_T28=200`/`CURL_T44=200`）并无 `#41` 超时平滑重连、断网强制 `5745 MHz` 起播时识别 `sta_freq=5240` 同会话切换至 `5240 MHz`（`CURL_CASEC=200`），且 WirePlumber `Audio Sink`/`Handsfree` 隔离回归通过（`5240 -> 2462 MHz` 跳过冲突 5 GHz 信道已由离线单测验证；另实证手机深休眠 `Dozing` 受 ColorOS `OplusProxyWakeLock` / `OplusHansManager` 节流，需亮屏唤醒触发）。
- 2026-11-15 `opd2413-netshare 0.1-5` 蓝牙音频角色隔离真机通过（见 [WORKLOG.md](WORKLOG.md)）：通过 `50-opd2413-bt-roles.conf` 将 WirePlumber `monitor.bluez.properties` 的 `bluez5.roles` 设为 `[ a2dp_source bap_source hfp_ag hsp_ag ]`；重启 `wireplumber` 无解析报错，`hci0` 广播不再包含 `Audio Sink`（`0000110b`）与 `Handsfree`（`0000111e`）而保留 `Audio Source` / `Handsfree Audio Gateway`；手机在 `5240 MHz / 80 MHz` 保持连接超过 `25 s` 且通过 `p2p0` 访网（`HTTP/1.1 200 OK`）期间，平板 `bluetoothd` 无 `/sep2/fd0` 与 AVRCP 接入、`wpctl` 无蓝牙节点，手机 `A2dpService`/`HeadsetService` 保持断开、`STREAM_MUSIC` 停留在 `speaker(2)`；切回 `auto` 双端清理正常（另附带确认手机深夜 `nightDeepDoze|LcdOff` 会冻结 `local.opd2413.netshare`，唤醒屏幕后即刻自动配对）。
- 2026-11-15 `7.2.15-24` + `opd2413-netshare 0.1-4` 5 GHz AP 端到端实测完成（见 [WORKLOG.md](WORKLOG.md)）：`iw reg get` 开机及断网期均稳态为 `country CN: DFS-FCC`（`global` 与 `phy#0`）；`mode force` 下与手机配对建成 `5240 MHz / 80 MHz`（对称 `1080.6 MBit/s HE-MCS 10 NSS 2`，`tx retries: 0`），经手机转发公网 `ping`/`HTTPS 200` 及直连 TCP 上传 `725.36 Mbps` / 下载 `783.33 Mbps` 均通过，切回 `auto` 双端清理零残留；无上行断网下可于 `5745 MHz (80 MHz)` 拉起 `p2p0`，同时暴露了 `p2p0` 占 `5745 MHz` 时 `wlp1s0` 连回异频 `5240 MHz` 路由器会在 9 ms 内认证超时的硬件并发局限（`#41`）。
- 2026-11-14 跨设备自动网络共享阶段 3（`opd2413-netshare-0.1-3.noarch` + Android Companion `opd-netshare.apk`）真机验收通过：完成蓝牙 RFCOMM Profile SDP 信道补全（`"Channel": GLib.Variant("q", 22)`）与硬件过滤 `PendingIntent` BLE 扫描 / `464XLAT` 路由识别修复，实测 `mode force`、`auto` 断网自动触发与恢复释放、`wlan0 <-> 5G 蜂窝`（`rmnet_data3`）在线无缝切换及连接态 `systemctl restart opd-netshare.service` 双端清理均通过；2026-11-15 用户确认手机开启允许后台后已可正常使用（[TECH-DEBT.md](TECH-DEBT.md) `#40` 已缓解，免手动设置所需的 `CompanionDeviceManager` 按需接续）。
- 2026-11-14 开机灰闪（`#9`）调查与 `2415`–`2417` 补丁已写入 `kernel/opd2413-7.2/patches/`（`-F0` 严格合入）与 [WORKLOG.md](WORKLOG.md)。
- 2026-11-13 `7.2.15-12.opd2413`（含 `2408`–`2410`）：先经 `2408`+`2409` 实现 Pogo 键盘在 `s2idle` 下通过 `gpio3` 4 簇脉冲过滤按任意键唤醒并屏蔽 10.001 s 脉冲与 22.659 s 电池上报拍频碰撞；再通过 erhai `b30d759d3`（`2410`：`LLCC_ISLAND1` 改用 `res_ways = 0x7fffffff`）修复自 `7.2.15-6`（`2401`）引入的冷启动 30–60 s 内进 `s2idle` 在 `PM: suspend-to-idle` 后触发 `PS_HOLD` 硬件复位的问题。
- 待续与长尾候选（详见下面 `M4` 与 [TECH-DEBT.md](TECH-DEBT.md)）：
  - **显示**：#20（60/30 Hz）、#35（Night Light DSPP）与 #9（开机灰闪）已相继解除；余下 `#39`（冷启动选入口后偶发黑屏自动重启）、`#36`（`2414` 寄存器级根因与无缝 VFP 切换）、`#37`（快速切换触控 `-112`）与 `#19`（熄屏断电）。
  - **系统/电源**：#34 合入 erhai GMU 绑定（`6f237b23c` 等）消除 `fw_devlink.sync_state=timeout`；M3.2b PPS 快充缺 PPS 充电器搁置；PMIC RTC 在早先硬件复位后停在 `2026-10-17` 且平板 `chronyc` 解析到代理保留地址未同步（`Not synchronised`）。
  - **外设与回馈**：USB 3 双向、DP 外接与音频；向 erhai 回馈修复前先问用户。
- 测试新内核用 `tools/tablet-reboot.py --entry …`；装新内核前先 `boot-select default <当前条目>`。拔线调试时每次重启后都要重新起 `opd2413-debug-inhibit`。

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

没有全局阻塞（第 2 次冷启动偶发选入口后黑屏自动重启已另立为 `#39` 后续排查）。平板当前默认并运行 `7.2.15-29.opd2413`（`running`、`0 failed`，保留 `-28` 与 `-26` 作回退，`boot-select default` 已将 `loader.conf` 默认项设为 `fedora-7.2.15-29.opd2413.conf`）。Fedora 45 KDE 正常运行。

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

## 设备状态（2026-11-16）

- 当前运行：Fedora 45 KDE，已于 `2026-11-16` 经单次安全引导 `90 s` 上线至内核 **`7.2.15-29.opd2413`**（合入补丁 `2435` 修复 `#42`），并经 `boot-select default` 设为默认（`booted_entry: fedora-7.2.15-29.opd2413.conf`，`loader_default: fedora-7.2.15-29.opd2413.conf`，`pending_next: null`，保留 `-28`、`-26` 作回退）。内核及实拍核验：`uname -r = 7.2.15-29.opd2413`、`running`、`0 failed`、SELinux `Enforcing`、`0 AVC`、`/proc/cmdline` 不含 `fw_devlink.sync_state=timeout` 与 `pcie_ports=compat` 并含 `mem_sleep_default=s2idle`、`/sys/power/mem_sleep = [s2idle] deep`、`dmesg` 无 Oops/`qsh_process`/`fatal error` 且零 `ac7b000.cci` 超时、`bound 3d37000.gmu`、`remote processor adsp is now up`、`[nt36536] Update firmware success!`、`cn3927` 从 `/lib/modules/7.2.15-29.opd2413/kernel/drivers/media/i2c/cn3927.ko` 加载（`/tmp/cn3927.ko` 已清除）、`/sys/class/devlink/i2c:10-000c--i2c:10-0036/runtime_pm = 1`、相机实拍及 GUI 冒烟后 `10-000c`/`10-0036` 均恢复 `suspended`、`opd2413-sensors-*`/`bluetooth`/`opd-netshare`/`opd2413-face`/`wireplumber` 均为 `active`、`aplay -l` 正常列出 `card 0: OnePlusPad2Pro`、`KSHIM.CHO` 哈希（`65d97e12...`）与 `1 extent` 前后完全一致、电池 `94% (charging)`（此前 `-28` 亦于 `2026-11-15 12:11:28` 完成未插电冷启动并保留作回退）。
- systemd-boot：`kshim_remembered: "Fedora"`，`loader_default: "fedora-7.2.15-29.opd2413.conf"`，`pending_next = null`；平板当前已装条目包含 `fedora-7.2.15-29.opd2413`（默认）、`fedora-7.2.15-28.opd2413`（保留回退）与 `fedora-7.2.15-26.opd2413`（保留回退）。
  ESP `/dev/sda16` 总计 512M、已用 370M、空闲 143M（73 %）。固定路径 `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb` 是 7.2.15 的（与内核 3 相同）。
- `boot_b` = `07bf1b53…`（fedora1：菜单 ColorOS / Fedora / Fedora boot menu，倒计时 10 s，默认项仍是 ColorOS）；KSHIM.CHO 记住 Fedora。
  上一版 `492f2cdf…` 的整分区回读在主机 `private/bootflow-20261111/boot_b-readonly.img`。
- 软件包：内核 `kernel-opd2413-7.2.15-29.opd2413`（当前默认条目）、`kernel-opd2413-7.2.15-28.opd2413`（保留回退条目）与 `kernel-opd2413-7.2.15-26.opd2413`（保留回退条目），以及 `opd2413-device-0.1-14`、`opd2413-audio-0.1-12`、`opd2413-sensors-0.1-1`、`opd2413-netshare-0.1-8`、`libcamera{,-ipa,-tools}-0.7.2-5.fc45.opd2413.3`、`python3-libcamera-0.7.2-5.fc45.opd2413.3`、`opd2413-camera-0.1-2`、`opd2413-face-0.1-10`、`wireless-regdb-2026.09.03-1.fc45`、`opd2413-firmware-16.0.10.600-2`、`showtime`（registry 在 `/var/lib/opd2413/sensors`）。`rpm -ivh --nosignature` 不受 `installonly_limit=2` 自动淘汰。
  内核 3（`7.2.6-3`）08:45 经用户同意卸载，它的包仍在主机 `out/rpms/`。
- 7.3 测试内核、"M3 test" 和 "Log capture" 两个条目、ESP 上的 `opd2413-bootlog/` 已于 11-11 23:29 删除。
- `/etc/modprobe.d/opd2413-pps.conf` 已删除（11-12）。`/etc/kernel/tries` 已删除。
- `/var/lib/opd2413-pstore/` 下有 9 个按计数器命名的记录目录（`000001`–`000009`，含本次根因取证 `000009`）；本次无调试冷启动 `/sys/fs/pstore/` 为空。
- SELinux enforcing，firewalld 运行中（public 区）。sshd 只允许密钥登录；2026-11-12 起 firewalld 不再对所有来源开放 ssh，只放行家里局域网的 /24 网段和 IPv6 链路本地（rich rule，已持久化）。
  换网络后 SSH 进不来时，在平板上用 `firewall-cmd --zone=public --list-rich-rules` 查、按新网段改。
- 自动登录到 `colin`，自动锁屏已关；KDE 空闲熄屏已恢复默认。当前可切换 `120 / 60 / 30 Hz`，`~colin/.config/kwinrc` 中 `[NightColor] Active=true`、`[Plugins] nightlightEnabled=true`。
- 系统时钟：此前早期硬件复位使 PMIC RTC 回到 `2026-10-17` 08:00，当前平板侧 `chronyc sources` 指向代理 fake-ip 不可达（`Not synchronised`），需要准确时间戳时可在主控操作前经 `date -s` 临时校时或排查 NTP 解析。
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
| `private/display-*` | 黑屏排查的证据和抓取脚本（含 `private/display-nightlight-20261112/` 夜灯触发 `ctl_0` 卡死黑屏与 `dspp_pcc` 残留的寄存器快照） |
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
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-10.opd2413.aarch64.rpm` | M3.5 麦克风、M3.6 基础键位内核；`out/rpmbuild/RPMS/noarch/opd2413-device-0.1-14`、`opd2413-audio-0.1-12` |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-11.opd2413.aarch64.rpm` | M3.6 键盘唤醒内核（`2408`–`2409`，不含 `2410`） |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-12.opd2413.aarch64.rpm` | 当前默认内核（合入 `2410` 修复冷启动早休眠 `PS_HOLD` 复位）；`out/m3k/pkg-test12/` 是它的容器安装校验 |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-18.opd2413.aarch64.rpm` | 旧测试内核（`2411`–`2413`，手动切 60 Hz 时复现 `CTL_0` 卡死，已从平板卸载） |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-22.opd2413.aarch64.rpm` | 上一版内核，现保留为平板回退条目（`2411`–`2414`，`SHA256: 139a520f...`） |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-23.opd2413.aarch64.rpm` | 上一版内核，现保留为平板回退条目（合入 `2415`–`2417` 解除开机灰闪，`SHA256: cbfdd4108e0278b2ea426fc158a994587716e1e17ade72bda77dfc2c2c67deb8`） |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-24.opd2413.aarch64.rpm` | 历史内核（`m3-wifi-reg.config` 5 GHz AP 调控域支持；`SHA256: a8e0dc41...`） |
| `out/rpmbuild/RPMS/aarch64/kernel-opd2413-7.2.15-29.opd2413.aarch64.rpm` | 当前默认内核（含 `2418`–`2434` 及 `2435` 修复后摄 `cn3927` 物理 AF，同步存档于 `out/m3k/rpms29/`；`out/m3k/pkg-test29/`、`out/camera-verify/` 为离线与实拍证据；`SHA256: 0acbb9b0...`） |
| `private/m3-kbdwake-20261113/` | 2026-11-13 Pogo 键盘唤醒排查、4 簇过滤验证、`ramoops-000009-s2idle.txt` 及 `7.2.15-12` 两次冷启动验收日志 |
| `out/rpmbuild/RPMS/aarch64/opd2413-sensors-0.1-1.aarch64.rpm`、`out/sensors/` | 传感器包及其源码包、构建日志 |
| `private/sensors-persist-20261102/` | 从 persist 备份导出的传感器 registry（本机数据） |
| `private/m3-sensors-20261112/` | 传感器安装、读数、挂起证据 |
| `private/m3-mic-20261112/` | 麦克风排查全过程：录音统计、寄存器转储、实验 DTB、坏录音样本 |
| `out/m3-rpm5/` | 诊断内核 `7.3.3-5.opd2413` 的构建脚本和日志（编译完成，19:50 在打包前中止，没有包） |
| `out/rpmbuild/RPMS/noarch/opd2413-device-0.1-13.noarch.rpm` | 平板上现在装的设备包（0.1-9 起允许 s2idle，0.1-10 修 boot-select 的条目 id，0.1-11 加键盘 hwdb，0.1-13 VP9 走软解） |
| `out/rpmbuild/RPMS/noarch/opd2413-firmware-16.0.10.600-2.noarch.rpm` | 平板上的固件包（加 Iris 固件） |
| `out/rpmbuild/RPMS/noarch/opd2413-netshare-0.1-8.noarch.rpm`、`out/netshare/opd-netshare.apk` | 跨设备自动网络共享平板端 RPM（`99K`，含 `0.1-4` 80 MHz/`CN`/SCC、 `0.1-5` WirePlumber BT Sink/HF 隔离、`0.1-6`/`0.1-7` BT 断电/重配对自愈、`0.1-8` Wayland `setDesktopFileName`/多尺寸 `hicolor` 应用图标与 4 态 `128×128` 托盘图标）与 Android 伴侣 APK（`90K`，v3 签名，含自适应/单色桌面图标及 24dp 六边形通知/磁贴矢量） |
| `out/rpmbuild/RPMS/aarch64/libcamera*-0.7.2-5.fc45.opd2413.3.aarch64.rpm` | `libcamera` SoftISP / LSC / AF 与 Stage 1 调校/视角修复 RPM 产物（含 `0101`–`0107` 及调校更新） |
| `out/rpmbuild/RPMS/aarch64/opd2413-camera-0.1-2.fc45.aarch64.rpm` | ZSL 多帧 RAW10 HDR+ 相机 CLI（`opd-camera-cli`）与 Qt6 Wayland GUI（`opd-camera`）RPM（含自动亮度/肤色保护鲜艳度及后摄 AF 控制） |
| `out/rpmbuild/RPMS/aarch64/opd2413-face-0.1-10.fc45.aarch64.rpm` | 原生人脸识别守护进程、PAM、锁屏覆盖与 GUI 录入向导 RPM |
| `out/video/`、`private/m3-video-20261112/` | 视频测试片源、解码记录 |
| `private/cam-stage1-20261115/` | Stage 1 / Stage 2 HDR+ 相机前后摄真机对比样张与量化指标证据 |
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
| M4 | 外设逐项验收和长尾问题（灰闪、USB 3 方向、DP 音频等） | 进行中：#9 开机灰闪已在 `7.2.15-23` 解除；#39 冷启动选入口偶发黑屏重启等长尾待继续 |
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
| 显示、背光 | 真机通过 | `7.2.15-23.opd2413`（`2415`–`2417`）：3 次热重启 + 3 次冷启动解除开机灰闪（`#9`），且复核 `120/60/30 Hz` 切换、`DPMS off -> on`、Night Light 与 `s2idle`；第 2 次冷启动偶发选入口后黑屏自动重启见 [TECH-DEBT.md](TECH-DEBT.md) `#39`，`2414` 规避机制与无缝切换见 `#36` |
| 触控 | 真机通过 | 用户确认触屏正常（2026-11-10）；面板重新 prepare 后触控固件也能重新下载 |
| GPU 硬件渲染 | 真机通过 | Fedora 原版 Mesa 26.2.6：KWin 用 OpenGL ES 3.2 / Adreno 830（freedreno），Vulkan 为 turnip；不需要带补丁的 Mesa |
| Pogo 键盘、触控板 | 真机通过 | 用户确认打字和触控板正常（2026-11-10）；日志有 libinput "touch jump" 警告；2026-11-13 `7.2.15-12`（`2408`–`2409`）支持 `s2idle` 下按键盘按键直接唤醒并点亮屏幕（休眠时 MCU 硬件关闭触控板） |
| Wi-Fi | 真机启动 | 开机自动连上家里的 Wi-Fi，SSH 可用（2026-11-10）；HE 160 MHz 2161 Mbit/s，省电模式开（默认），ping 丢包 0、4–22 ms（2026-11-11）；断线重连和长时间传输未测 |
| 扬声器 | 真机通过 | 用户确认播放、音量调节、静音正常（2026-11-10）；左右与逐颗未单独验 |
| 麦克风 | 真机通过 | 2026-11-12，7.2.15-10（`2407`）+ opd2413-audio 0.1-12，见 M3-FEATURES M3.5 |
| 蓝牙 | 真机通过 | 2026-11-12，7.2.15-2 起：音箱、耳机配对/连接/播放（M3.1） |
| 跨设备网络共享 | 真机通过（`5240 MHz` 断网记忆、BT 自愈、音频隔离与跨频切频已验；`0.1-8` 图标与 Wayland 窗口已实装） | 2026-11-14，`opd2413-netshare-0.1-3` + Companion APK 全链路（BLE/RFCOMM/`464XLAT`/蜂窝切换/重启清理）通过（`#40` 允许后台缓解）；2026-11-15 `7.2.15-24` + `0.1-4` 验通 `COUNTRY=CN`、`5240 MHz / 80 MHz` SCC（`1080.6 MBit/s`，上传 `725.36 Mbps` / 下载 `783.33 Mbps`、`ping`/`HTTPS 200`）及断网 `5745 MHz / 80 MHz` 拉起；`0.1-5` 经 WirePlumber `bluez5.roles` 剔除 `Sink`/`HF` 防蓝牙音频劫持（控制器保留 `Audio Source`/`Handsfree Audio Gateway` UUID，真无线耳机实际播放待按需复测）；`0.1-7` + 新版 APK 实机通过蓝牙断电/`rfkill` 自愈、`mode auto` 断开 `wlp1s0` 记忆 `5240 MHz` 建连（`CURL=200`）与无 `#41` 超时平滑重连、强制 `5745 MHz` 起播时按手机 `sta_freq=5240` 同会话切换 `5240 MHz`（`CURL=200`）及音频隔离回归（`5240 -> 2462 MHz` 跳过冲突 5 GHz 由离线单测覆盖；手机 `Dozing` / 后台分别受 ColorOS `OplusProxyWakeLock` 与 `OplusHansManager` 节流，需亮屏唤醒触发，见 `#40`/`#41`）；`0.1-8` + `90K` 新版 APK 统一 `icon.png` / `tray_*.png`（`128×128` 托盘、`48–256` hicolor、`432×432` Android 自适应前景与 24dp 六边形通知/磁贴单色矢量），`WAYLAND_DEBUG=client` 实测 `set_app_id("opd-netshare")` 与 `xdg_toplevel_icon_manager_v1.set_icon` 发送成功，会话 Qt 探针四态及 D-Bus SNI `idle`/`off`（`0.40x`）/`advertising` 切换通过（`connected` 实时 SNI 切换待手机亮屏建连目视） |
| 休眠 | 真机通过 | 2026-11-12：s2idle，电源键/合盖/RTC 唤醒，挂起时 CX 塌陷约 98 %（M3.3）；2026-11-13 `7.2.15-12` 增补 `2410`（`LLCC_ISLAND1` `res_ways`）修冷启动 30–60 s 内早休眠 `PS_HOLD` 硬件复位，并加 Pogo 键盘空格键唤醒（无调试服务冷启动 21 s 实测通过）；拔线待机耗电未测 |
| 充电（9 V PD） | 真机通过 | 2026-11-12，7.2.15-3 起（M3.2a）；PPS 快充驱动已装、待电量低于 75 % 实测（M3.2b） |
| 电量、温控 | 真机通过 | 电量、电流（符号正确）、温度读数正常（M3.2a）；温控未单独验 |
| 传感器、自动旋转 | 真机通过 | 2026-11-12，opd2413-sensors（M3.4c）：自动旋转、环境光、指南针、陀螺仪；KDE 无自动亮度 |
| 摄像头 | 真机通过 | 2026-11-12 起；2026-11-15 Stage 1 `libcamera-0.7.2-5.fc45.opd2413.3` 完成 `0101`–`0107` 补丁及高光零溢出/16:9 居中视角调校，Stage 2 `opd2413-camera-0.1-1` 通过前/后摄 ZSL 多帧 RAW10 HDR+（`black_level_10b=64.0`、中性灰黑阴影、EXIF 完整）及 `opd-camera` Qt6 Wayland 实况预览与 `opd-face` 协同；2026-11-16 升级 `opd2413-camera-0.1-2`（`LUX` 中心加权自动亮度、暗部归零/肤色保护鲜艳度、后摄 AF 控制）并随默认内核 `7.2.15-29.opd2413`（补丁 `2435`）持久化修复后摄 `cn3927` 物理对焦：`cn3927` 原生加载、晨光实拍 Contrast AF 锁定 `af_state=2`（`2.053D`）与手动 `0.0D`/`10.0D` 近距贴纸清晰切焦、5 秒 Wayland GUI 冒烟及用户真机试用均零 CCI 超时通过，`opd2413-face` 与 `wireplumber` 协同正常，`#42` 已消号（室内后摄白墙略带轻微偏黄绿暖调按需微调） |
| 人脸识别解锁（`opd2413-face`） | 真机通过 | 2026-11-15，`opd2413-face-0.1-10`（锁屏屏保待命→唤醒视觉扫描→刷脸解锁、`sudo`/`polkit` 人脸授权、冷启后解锁、Qt 录入向导及 `face-smile` 图标均经用户实测通过） |
| 视频硬解 | 真机通过 | 2026-11-12（M3.4a）：固件 600-2 后 GStreamer 硬解 H.264/HEVC，Showtime 为默认播放器；VP9 走软解；mpv/Firefox 仍软解（ffmpeg-free） |
| DP 外接显示 | 有源码线索 | erhai |
| USB 3 双向 | 待调研 | |
| 合盖、电源键、音量键 | 真机通过 | 合盖/电源键挂起唤醒（M3.3）；音量键正常；键盘 Esc、麦克风键、锁屏键（M3.6）。拔线时关机不会自动开机 |
| SELinux enforcing | 真机通过 | 内核 3 加入 selinux；首启 relabel 23 s；permissive 和运行中 enforcing 下用户试用触控、键盘、声音、亮度、浏览器、设置均无拒绝；改为开机 enforcing 后冷启动 AVC 0（2026-11-11） |
| 防火墙 | 真机启动 | firewalld `running`，public 区绑定 wlp1s0；SSH 可连；规则本身未逐条验证 |
