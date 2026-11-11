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

## 工作区（主机，忽略目录）

| 路径 | 内容 |
|---|---|
| `out/fedora-kernel/` | src.rpm 和解出来的源码包、redhat 补丁、aarch64 配置、kernel.spec |
| `out/m3-tree/` | git 树：分支 `fedora-7.3.3`（7.3.3 + Fedora 补丁）、`m3-merge`（erhai 三方合并）、`trial-erhai`（逐提交重放试验，不用）。通过 alternates 引用 `~/github/linux-sm8750-erhai` 的对象 |
| `out/m3-erhai/` | erhai 提交导出的补丁、分类和试验结果、merge-tree 输出 |
