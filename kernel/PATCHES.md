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
