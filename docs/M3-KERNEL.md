# M3：换到 Fedora 45 的内核基线

目标：平板运行以 Fedora 45 当前内核（7.3.3-300.fc45）为基线、带本机设备支持的内核，功能不低于内核 3
（`7.2.6-3.opd2413`），再逐项加上 erhai 的休眠、充电、蓝牙、摄像头、合盖、视频硬解。

## 调查结论（2026-11-11）

| 项 | 结论 |
|---|---|
| Fedora 45 内核 | updates 仓库是 `kernel-7.3.3-300.fc45`。src.rpm 里是 `linux-7.3.3.tar.xz` + `patch-7.3-redhat.patch`（79 个文件）+ `kernel-aarch64-fedora.config` |
| erhai | 最新是 `erhai-v0.7.2`（`870167fad`，2026-11-06），基于 7.2.15，比 v0.6 多了 9 V PD 和 PPS 快充（SC8547A）、s2idle、摄像头方向和分辨率修正、面板只给 120 Hz。master 分支只是上游 7.3-rc7 的镜像，作者还没有做 7.3 |
| Armada 的 OPD2413 支持 | `1400`–`1402`、`1408` 本身就是从 erhai（v0.6 时期）挑出来移植的。Armada 自己的是开机显示交接 `1404`–`1407`、`1409`，以及我们的 `1411`。erhai 没有这些（`msm_mdss.c` 未改，面板熄屏仍断电） |
| 上游 7.3 已收录 | nt36536 面板驱动及绑定、KTZ8866、AW88261、SM8750 的时钟、显示目录、iris 平台数据、互联、引脚 |
| erhai 前移的难度 | 以 7.2.15 为合并基础，把 erhai v0.7.2 三方合并到 Fedora 7.3.3：**36 个文件冲突，约 100 处**，其余自动合并。冲突集中在音频（`sc8280xp.c` 24 处、`common.c` 10 处、qdsp6 和 lpass 宏），其次是 nt36536 面板（上游版本与 erhai 版本分叉）、dsi_host、DP、iris、remoteproc |
| 逐提交重放 | 437 个 erhai 独有提交顺序 cherry-pick：155 个直接应用、131 个上游已有、151 个冲突（多为连带失败）。不采用 |

## 路线

**设备改动以 erhai 为主体，Armada 只补它独有的修复。** 两边实现的是同一套驱动，Armada 的版本是 erhai 早期版本的子集；
以 erhai 的最终状态为准，冲突最少，也能直接得到快充、休眠和摄像头。

1. **基线**：`linux-7.3.3` + `patch-7.3-redhat.patch`，配置 `kernel-aarch64-fedora.config`。
2. **erhai 合并**：三方合并（基础 7.2.15 = `497791a0a`，一边 Fedora 7.3.3，一边 `erhai-v0.7.2`），逐个解决冲突。
   原则：上游已收录的以上游为准，只补 erhai 多出的行为；不确定的保留上游版本并记录。
   结果按主题拆成补丁序列（显示、触控与键盘、音频、充电、摄像头、iris、Wi-Fi 与蓝牙、DTS、其他），放 `kernel/opd2413-7.3/`，
   每个补丁记来源提交。erhai 带进来的与本机无关的通用修复（smb、kvm、thunderbolt 等），7.3 已有的自然消失，其余删掉。
3. **Armada 独有修复**：`1404`–`1407`、`1409`（开机显示交接）、`1411`（熄屏面板保持供电），逐个移植到上游版本的 nt36536 和
   msm 驱动上。`1412` 由 erhai 的同类提交代替。
4. **配置**：Fedora 的 aarch64 配置 + erhai 的 `sm8750-peripherals.config` 和板级片段里本机需要的选项（尽量 `=m`）+ 我们的需求，
   作为一个配置片段放进仓库。Fedora 配置自带 SELinux 和 netfilter。
5. **构建与打包**：第一阶段沿用 `kernel-opd2413` 的二进制打包（版本 `7.3.3-<N>.opd2413`，`N` 从 1 开始），只改内核这一个变量；
   开机通过后再评估改用 Fedora 的 `kernel.spec` 交叉构建（技术债 #12）。
6. **离线检查**：编译通过；DTB 与内核 3 的 DTB 逐节点对比，差异逐条解释；`tests/package-install-test.sh` 和 QEMU 启动链测试通过。
7. **上机**：按 [KERNEL-UPDATE.md](KERNEL-UPDATE.md)。内核 3 已真机通过，装 7.3 内核时 `installonly_limit=2` 卸掉的是 2，
   内核 3 保留为回退项。

## 完成标准

**M3a（替换内核 3）**：7.3 内核冷启动后，M1 验收清单全部通过（桌面、触控与多点、KWin 硬件渲染、键盘和触控板、Wi-Fi、扬声器、
亮度、`systemctl --failed` 为空、Android 分区只读、重启回 ColorOS），并且 SELinux enforcing 无拒绝、firewalld 运行、
熄屏亮屏恢复、开机 5 次都有画面（`1407` 修的是约四分之一的开机黑屏）。

**M3b（erhai 功能）**：每项单独上机验证并写进 STATUS 功能表：s2idle 休眠与唤醒（电源键、键盘、合盖）、9 V PD 与 PPS 充电、
电量和温度、蓝牙、霍尔合盖、摄像头出图、视频硬解（需要补 `vpu35_4v.mbn` 固件）、去掉技术债 #1 的三个调试启动参数。

## 进度

| 步 | 状态 | 说明 |
|---|---|---|
| 1 基线 | 完成 | `out/m3-tree` 分支 `fedora-7.3.3` |
| 2 erhai 合并 | 完成（未拆分） | 冲突的处理见下节；结果暂存为一个大补丁 `kernel/opd2413-7.3/patches/0001`，按主题拆分是技术债 |
| 3 Armada 修复 | 完成 | `1404`、`1406`、`1407`、`1409`、`1411`（带 `keep_powered` 参数）；`1405`（出错时的寄存器打印）未带 |
| 4 配置 | 完成 | `kernel/opd2413-7.3/opd2413.config`，做法见下节 |
| 5 构建 | 完成 | `7.3.3-1.opd2413`：5859 个模块，`vmlinuz.efi` 18.7 MB，去调试段后模块 564 MB |
| 6 离线检查 | 完成 | 编译无错误、改动过的文件无警告；DTB 对比差异都能解释；容器安装测试 PASS（66 个固件齐全，通用 initramfs 122 MB）；QEMU 启动链 PASS（systemd-boot 262 启动压缩 EFI 内核） |
| 7 上机 | 待用户确认 | |

## 冲突怎么处理的

- **上游已收录的以上游为准**：面板 Kconfig、热管理、QMI、lpass 宏的 PM 时钟框架、q6v5 的一次性中断、phy-core、ubwc、DP（erhai 的 DP 改动整体放弃，M3b 做外接显示时再看）。
- **nt36536 面板**：7.3 上游的 `panel-novatek-nt36536.c` 是联想 Legion Y700 Gen4 的驱动（只匹配 `csot,pp8807hb1-1`），
  erhai 用同一个文件名写了本机的驱动。上游的保留，erhai 的改名为 `panel-novatek-nt36536-xn242.c`（`DRM_PANEL_NOVATEK_NT36536_XN242`）。
  DSC 每包 slice 数改用上游的 `MIPI_DSI_MODE_DSC_ALL_SLICES_IN_PKT`（2 个 slice 正好是全部），`dsi_host.c` 和 `drm_mipi_dsi.h` 保持上游。
- **音频**：`common.c` 取 erhai 的多 codec TDM 版本（上游只支持单 codec，本机 6 颗功放）；`sc8280xp.c` 以上游重构后的版本为底，
  TDM 部分改用多 codec 接口、保留链路格式、加 `convert-*` 修正、sm8750 开 `mi2s_bclk_enable`；`audioreach.c` 取 erhai 的 TDM 和
  `bits_per_sample`，声道映射用上游（与内核 3 相同）；rx/tx/va/wsa 宏用上游版本 + 系统休眠时强制运行时挂起，tx 再叠 Armada `0080`
  （UCM 同时用 DEC0、DEC1）。erhai 的 TX 高通滤波控件没带（UCM 不用）。
- **其他**：q6v5_pas 同时保留上游的 `qcom_pas_context` 改名和 erhai 的开机总线投票；spi-geni 保留 erhai 的 GPI DMA 延迟 QoS，
  `geni_icc_get` 用上游的位置；iris 合并两边的控件。

## 配置怎么定的

Fedora 7.3 的配置**没有开 SM8750 的 GCC、引脚、互联**，原版 Fedora 内核在这台平板上起不来。片段的来源：

1. 在平板上（内核 3）只读列出已加载模块和已绑定驱动，用 `tools/kernel/mod2config.py` 映射到 Kconfig 选项（177 个）。
2. 内核 3 里 `=y` 而 Fedora 不是的（约 50 个：时钟、引脚、互联、UFS、显示、remoteproc、GLINK 等）照样编进内核：
   dracut 的 hostonly 是在内核 3 上算的，那时这些驱动在内核本体里，不能指望 initramfs 带上它们的模块。
3. 依赖链上的父选项（DRM、TYPEC、RPMSG、QRTR、MHI、IIO、UFS 核心、RPMB 等）用 `tools/kernel/fixdeps.py` 迭代补齐，
   直到片段里每一项都生效。
4. erhai 新驱动：快充 SC8547A 和 PPS 编成模块（PPS 上机时先用 `options erhai_pps pps_enable=0` 关掉，M3b 单独验证）；
   摄像头相关编成模块；手写笔充电 CPS8601 不开。

## DTB 对比（内核 3 的 DTB 与新 DTB）

固件路径（firmware-name）完全相同。差异：GPU compatible `adreno-44050000` → `44050001`（7.3 上游目录里的 Adreno 830）并带
速度档熔丝；去掉 Armada 的 DPU LUT DMA 寄存器；新增上游 7.3 的 CoreSight 节点（tmc、replicator、ctcu、tpdm，内核 3 下同类的
funnel/cti/tmc/stm 驱动都正常加载过）；手写笔充电器节点（驱动未开）；两颗电荷泵；ramoops 移到 0xafff00000；去掉串口控制台；
PCIe WAKE# 改为低有效；CPU 温区少了一个没挂降频的 90°C passive 触发点（118°C 的 passive 降频仍在，效果相同）。

## 上机（M3a）

写入：`/etc/modprobe.d/opd2413-pps.conf`（`options erhai_pps pps_enable=0`）；`dnf install` 内核包
（`installonly_limit=2` 自动卸掉 `7.2.6-2.opd2413`，kernel-install 在 ESP 写 `fedora/7.3.3-1.opd2413/` 和条目）。
内核 3 保留为回退项。新条目版本最高，成为默认项。

1. 装前：内核 3 是当前最新且已真机通过的内核；ESP 空闲约 268 MB（卸 2 腾出约 128 MB，新内核约 19 MB + hostonly initramfs）。
2. 装后：`rpm -q kernel-opd2413` 为 3 和 7.3.3-1；ESP 上两个条目；`lsinitrd` 能看到设备固件；ESP 上条目以外的文件哈希不变。
3. 重启（kShimC 选 "Armada"）。起不来就重启后选 "Armada boot menu"，在 systemd-boot 里选内核 3。
4. 判据（M3a 完成标准）：`uname -r`、`running`、失败单元、`getenforce`、AVC、`journalctl -b -p err`；KWin 硬件渲染；
   用户确认画面、触控、键盘和触控板、声音、亮度、Wi-Fi、熄屏后亮屏；之后再冷启动 4 次都有画面。
5. 首次启动若整机重启或卡住，先怀疑：CoreSight 新节点、hostonly initramfs 缺模块、DRM 交接。

## 工作区（主机，忽略目录）

| 路径 | 内容 |
|---|---|
| `out/fedora-kernel/` | src.rpm 和解出来的源码包、redhat 补丁、aarch64 配置、kernel.spec |
| `out/m3-tree/` | git 树：分支 `fedora-7.3.3`（7.3.3 + Fedora 补丁）、`m3-merge`（erhai 三方合并）、`trial-erhai`（逐提交重放试验，不用）。通过 alternates 引用 `~/github/linux-sm8750-erhai` 的对象 |
| `out/m3-erhai/` | erhai 提交导出的补丁、分类和试验结果、merge-tree 输出、平板驱动清单、DTB 对比 |
| `out/m3-build/` | 构建目录（`O=`）；`out/m3-build*.log` 是构建日志 |
| `tools/kernel/`（仓库内） | `pick.py`（按块选冲突）、`mod2config.py`、`fixdeps.py` |
| `out/kernel-7.3.3-1.opd2413*` | 安装 stage 和 tar.zst；RPM 在 `out/rpmbuild/RPMS/aarch64/`，测试用的一套在 `out/m3-rpms/` |
| `out/m3-pkg-test/`、`out/m3-qemu-test/` | 两个离线测试的证据 |
