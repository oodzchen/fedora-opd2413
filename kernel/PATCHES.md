# 本仓库追加的内核补丁来源

Armada 原补丁作者及来源继续保留在 `armada-7.2.6/PATCHES.md`；
M3 的 erhai / Armada 移植来源见各补丁头和 `docs/M3-KERNEL.md`，不重写原作者。

| 补丁 | 来源与作者 | 用途与状态 |
|---|---|---|
| `opd2413-7.3/patches/0005-clk-qcom-restore-async-runtime-put-for-boot-diagnosis.patch` | 本仓库新增的本地诊断回退，不是引入第三方补丁；参考已验证 7.2.6 的 `drivers/clk/qcom/common.c` 行为，原驱动归属不变 | `qcom_cc_really_probe()` 的 `pm_runtime_put_sync()` 改回 `pm_runtime_put()`，仅一行功能改动；构建为 `7.3.3-4.opd2413`，真机结果尚待验证，不认定根因已确认 |
| `opd2413-7.2/refreshed/0048`、`0532`、`1145` | Armada 序列中的同名补丁（原作者和来源见补丁头与 `armada-7.2.6/PATCHES.md`），本仓库只按 Linux 7.2.15 刷新上下文 | 7.2.15 基线用；改动内容与原补丁相同，见 `opd2413-7.2/README.md` |
| `opd2413-7.2/patches/2001-Bluetooth-hci_qca-reset-the-in-band-sleep-state-on-power-off.patch` | erhai 提交 `5fbc7cbd1`（erhai-v0.7.2），FROMLIST：Birk Skyum、Vladyslav Tymoshchuk，linux-bluetooth v2 投稿（补丁头里有链接）；本仓库只按 7.2.15 刷新注释上下文 | M3.1 蓝牙：控制器断电时把 IBS 睡眠状态复位，避免快速关开蓝牙或休眠恢复后命令超时；上游合入后换成上游版本 |
| `opd2413-7.2/config/m3-1-bluetooth.config` | 依据 erhai 提交 `eb313ec77`（yzddmr6）"enable the Bluetooth profiles the desktop uses"，按本内核的模块化方式改写 | M3.1 蓝牙：`BT_RFCOMM_TTY`、`BT_BNEP` 及其过滤选项 |
| `opd2413-7.2/patches/2101-power-supply-qcom_battmgr-take-the-erhai-v0.7.2-driver.patch` | erhai-v0.7.2 的 `qcom_battmgr.c` 整个文件和 `erhai_otg_glink.h`；补丁头按顺序列出 erhai 里改过这个文件的 21 个提交及作者（yzddmr6、BUSHIGEMENNI、Joonhoe Kim、Brandon Williams、Bjorn Andersson、gennro、yading），`From:` 用主要作者 yzddmr6 | M3.2a 电池与固定 9 V PD；erhai 的这段历史经过一次 7.2.10 合并和事后补回（`67cdfbca6`），无法逐个重放，所以整文件引入。替代 Armada 序列中 `0503`、`0901`–`0904` 对该文件的改动 |
| `opd2413-7.2/patches/2102-usb-typec-mux-wcd939x-usbss-DP-DM-route-for-the-charge-pump.patch` | erhai 提交 `af5949fb9`（yading）中 `wcd939x-usbss.c` 和新头文件的部分，取 erhai-v0.7.2 的差异 | M3.2b：SC8547A 驱动链接需要的 D+/D- 切换函数；串行 VOOC 默认关闭，正常使用不切换。在 Armada `0063` 之上原样应用 |
| `opd2413-7.2/patches/2103-power-supply-add-the-erhai-SC8547A-charge-pump-and-PPS-engine.patch` | erhai-v0.7.2 的 `sc8547a.c/.h`、`erhai_pps.c`、`erhai_pps_trace.h`、`southchip,sc8547a.yaml` 整文件；补丁头列出 7 个来源提交（yzddmr6、yading），两个驱动文件保留 OnePlus 厂商源码的 GPL-2.0-only 声明 | M3.2b PPS 快充；不含手写笔充电 `cps8601` |
| `opd2413-7.2/config/m3-2b-pps.config` | 依据 erhai 配置（那边是内建），改为模块 | M3.2b：`CHARGER_SC8547A`、`CHARGER_ERHAI_PPS` |
| `opd2413-7.2/patches/2301`–`2346`（46 个） | erhai v0.7.2 里相机相关的 46 个提交，按 erhai 顺序 `git format-patch` 导出，作者和来源保留在各补丁头（Bryan O'Donoghue 的 CSI2 PHY 与 phy core、Hangxiang Ma 的 SM8750/Kaanapali CAMSS、yzddmr6 与 yading 的传感器、对焦马达和 SM8750 适配、pmdomain 性能态）；导出时去掉了板级 DTS 和 defconfig 部分（本机 DTS 的相机节点已与 erhai 相同） | M3.4b 摄像头；在 7.2.15 上按顺序严格应用，代码文件与 erhai v0.7.2 逐字节相同 |
| `opd2413-7.2/config/m3-4b-camera.config` | 依据 erhai 配置 | M3.4b：CSI2 PHY、SC1300CS、SC820CS、CN3927（模块），udmabuf 和 DMA-BUF 堆内建（同 Fedora） |
| `opd2413-7.2/patches/2401-ASoC-codecs-lpass-tx-va-macro-take-the-erhai-v0.7.2-drivers.patch` | erhai-v0.7.2 的 `lpass-tx-macro.c`、`lpass-va-macro.c` 整文件和 Kconfig 去掉 `PM_CLK` 依赖；补丁头列出 10 个来源提交（Ajay Kumar Nandam 的 FROMLIST "manage clocks in runtime PM"、yzddmr6 的 HPF 控件等），`From:` 用 Ajay Kumar Nandam | M3.5 麦克风：替换内核 3 序列里 PM 时钟框架版本的两个驱动（候选修复，待真机验证） |
| `opd2413-7.2/patches/2403-Input-oneplus-pogo-keyboard-report-the-Esc-key-as-KEY_ESC.patch` | 本仓库 | M3.6 键盘：Esc 位置的键（固件发 AC Back）报 `KEY_ESC`（可回馈 erhai） |
| `opd2413-7.2/patches/2404`–`2406` | erhai 提交 `7bbdee3c1`（Abel Vesa：q6v5 handover 中断改为 one-shot）、`0ccae6665`（yzddmr6：GLINK 暂存端点就绪前到达的消息，按 erhai 最终文件刷新上下文）、`e8c5cc534`（Junhao Xie：APR 在探测服务前装好 GPR 回调） | M3.5 麦克风候选：每次启动都有 `qcom-apm … CMD timeout`，怀疑开机时丢了发给 ADSP 的消息 |
| `opd2413-7.2/patches/2407-ASoC-codecs-wcd939x-report-and-switch-SoundWire-channels-individually.patch` | 本仓库 | M3.5 麦克风根因修复：ADC1–4 共用一个 SoundWire 端口，开关控件按端口报告导致混音器状态保存/恢复后多开声道；改为按声道报告和切换（可回馈 erhai/上游，wcd938x 同样写法） |
