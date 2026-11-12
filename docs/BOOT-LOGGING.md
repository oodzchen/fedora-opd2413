# M3a：持久化启动取证

## 目标与当前结论

2026-11-11，用户明确反馈启动时抓拍不方便，要求自动采集、保存日志。不再以照片为实验前提。

当天 18:45 的评估推翻了一个旧结论：**ramoops 在这台机器上是可用的**，之前以为"重启后不保留"是被
`systemd-pstore.service` 和 `quiet loglevel=3` 骗了（经过见 WORKLOG"18:39 起：评估"）。现在的取证分三层：

| 层 | 通道 | 覆盖 | 丢失条件 | 状态 |
|---|---|---|---|---|
| 1 | ramoops 控制台（256 KiB 环形区）→ 下一次启动由 systemd-pstore 归档成文件 | 从第一行日志到复位前，含 `/init` 之前 | 长按电源、冷启动；控制台级别被 `quiet` 压住时只有 emerg | 真机通过：第 12 次（19:07）取到 7.3 自动复位前的 256 KiB 控制台，无人值守；内容有零星字符错位 |
| 2 | initramfs 采集器：`/dev/kmsg` → sda17 上的 `O_DSYNC` 文件 | `/init` 之后到切根前，序号 0 起完整 | 内核没走到 `/init`、UFS 不可用 | 稳定内核冷启动真机通过；有一个已修复待重新部署的缺陷（技术债 #29） |
| 3 | journald | 真实根挂载之后 | 卡死后长按电源会丢最后几十秒到几分钟 | 真机通过：第 13 次 7.3 没有网络，短按电源键正常关机后取回完整 journal（6514 行） |

取回只用一条命令，全程只读：

```sh
tools/bootlog/fetch-bootlogs.py                      # 现在就取
tools/bootlog/fetch-bootlogs.py --wait 900 --after <关机前的 boot id>   # 等平板回来再取
```

结果在 `private/bootlogs/<时间>-<boot>/`：`pstore-keep/`、`pstore-archive/`、`pstore-live/`、`bootlog/`（sda17，debugfs 只读）、
`journal/`（最近几次启动的内核日志），并打印每份日志的最后几行。

### 7.3 没有网络时的取证流程

选 M3 test → 等约一分钟 → **短按**电源键（logind 正常关机，约 1 秒）→ 平板自动开机进默认的稳定内核 →
主机 `tools/bootlog/fetch-bootlogs.py`，它会标出"另一个内核的 journal"。需要完整 journal 时在稳定内核下
`journalctl -b <那次的 boot id>`。短按无效（用户态没起来）才长按。

### 用 ramoops 要知道的几件事

- 两个内核的 ramoops 节点相同：`0xbfff00000`，1 MiB，控制台区 256 KiB。只保留最后 256 KiB。
- 热复位（`reboot`、panic 后重启、固件触发的自动复位）保留；**长按电源丢失**；关机再开机会损坏。
  所以测试时卡住了也先等，不要马上长按；能自动复位的失败最好取证。
- 内核默认 panic 后永远停住（`CONFIG_PANIC_TIMEOUT=0`），那就只能长按、日志丢失。诊断条目应带 `panic=15`
  （以及按需 `softlockup_panic=1`、`rd.shell=0 rd.emergency=reboot`），把停住变成热复位。还没上机验证。
- 测试条目必须带 `ignore_loglevel`（或不带 `quiet`），否则控制台区几乎是空的。
- `systemd-pstore.service` 开机约 4 s 把记录移到 `/var/lib/systemd/pstore/`，**固定文件名、后一次覆盖前一次**，并从
  `/sys/fs/pstore` 删除。`opd2413-pstore-keep.service`（`opd2413-device` 0.1-6）在它之前把记录复制到
  `/var/lib/opd2413-pstore/<发现记录的那次启动的 boot id>/`，不覆盖。目录不自动清理，稳定内核每次热重启留 41 字节。
- 复位后第一次启动必须是稳定内核：如果又进了 7.3，它会在自己的 ramoops 初始化时清掉上一次的记录。

### 文件采集器（第 2 层）现状

- 18:19 的冷启动对照：序号 0–1587 连续、无缺号、服务 success，跨重启读回一致。initramfs 阶段真机通过。
- 同一次启动进桌面后卡死。原因是采集模块在 `umask 077` 下调用 `mount`，把 `/run/mount` 建成了 0700 并带进真实根。
  仓库里已修（`bootlog_mount`/`bootlog_umount`，`tests/bootlog-mount-test.sh`），**ESP 上的 initrd 还是旧的，
  "Log capture" 项不要选**。
- 采集器在切根前停止，切根之后的卡死它记不到。要覆盖整个启动，需要让它带着 `@` 前缀活过切根并在关机时正常卸载，
  或在真实根里另起一个同样的服务。没有做；第 1 层已经够用，除非再遇到必须长按电源才能恢复、又没走到 journald 的失败。
- 它还没有进过 7.3 的 initramfs（现有产物是给稳定内核的附加层）。

下面 §1–§5 是 18:45 之前写的设计记录，其中"ramoops 不保留""首选路线"的说法已被本节取代，其余细节仍然有效。

启动实验原始证据：`private/m3-resume-20261111/`。恢复/存储核对和备份：`private/bootlog-20261111/`。
当前设备状态和唯一下一步以 STATUS 为准。

## 1. 覆盖边界：为什么不能只加一个保存日志的服务

以当前 7.3.3 源码和同次构建的 System.map 为准：

| 阶段 | 实际先后关系 | 对取证的影响 |
|---|---|---|
| built-in device initcalls | DISPCC、GPUCC 在这里注册；UFS 核心和 Qualcomm UFS 平台驱动也在这个级别，但链接位置更晚 | 若卡在时钟注册前后，此时可能尚无可写块设备 |
| late initcalls | `fs/pstore/blk.c:pstore_blk_init()` 在这里执行 | pstore/blk 并非从第一行日志就能写盘 |
| initramfs `/init` | `init/main.c` 在 `kernel_init_freeable()` / `do_basic_setup()` / 所有 initcalls 之后才执行 `/init` | 仅写 dracut hook，不能覆盖阻止 `/init` 执行的 built-in 驱动故障 |
| 真实根文件系统及 journald | 更晚 | 普通 systemd 服务或 persistent journal 也不能独自解决更早的故障 |

必须把“已发生的日志保存在 RAM 中”与“确实有通道把它写到非易失介质”分开。
日志缓冲调大、`rd.debug`、`initcall_debug` 都不等于已经持久化。

### pstore/blk 的适用范围与限制

`CONFIG_PSTORE_BLK` 配合 console frontend 可以持续保存控制台，不必等到 panic。
但当前内核未启用它，而且：

1. built-in 后端在 late initcall 才注册；如果没走到那里，日志仍落不了盘。
2. 普通块设备的 best-effort 路径没有专用 `panic_write`，不能承诺硬死锁、panic 或 TZ 复位瞬间还能写出最后一行。
3. 当前 `fs/pstore/zone.c` 还存在 RAM 缓冲和延迟刷脏区，不能把“写入 RAM 队列”当作掉电可读。
4. 它需要独占原始块设备；直接指向现有 ext4 分区会破坏文件系统，绝不是只创建一个日志文件。
5. 注册成功后 console 的 `CON_PRINTBUFFER` 可以回放仍在 printk 环形缓冲里的旧日志，但不能补救后端从未运行的启动。

因此不直接拿现有分区尝试 pstore/blk。它是有源码线索的备选，不是本轮已验证方案。

## 2. 文件采集路线：先验证文件持久化，再延后可疑初始化

### A. 稳定内核上的独立正对照

先不改变 `7.2.6-3.opd2413` 的内核或驱动，仅准备独立的诊断 initramfs 和非默认启动项：

1. **只读核对并备份存储**（已完成）：Linux 专属 `ARMADA_BOOT`（sda17，1 GiB，原 ext4 `/boot`，Fedora 启动不使用），
   实际未挂载、clean，有旧启动文件，约 827 MiB 空闲；完整备份及两侧哈希通过。后续写入仍需另行批准。
   在改 initramfs 前，当前稳定系统的真实 `/dev/kmsg` 试跑已于 17:09 获批执行并通过：根分区仅新增独立临时程序/脚本，
   sda17 仅新增日志目录；子进程 `RLIMIT_FSIZE` 为 16 MiB、禁用 core dump，READY 后写入唯一测试标记，
   SIGTERM 正常结束、卸载后用默认只读 debugfs 读回逐字节一致，自动取回主机的哈希也一致。
   这轮没有改启动路径、没有重启；卸载读回不能代替下面的冷启动正对照。
2. 若核对通过，使用其现有文件系统，只新增受限的 `opd2413-bootlog/` 目录和日志文件，**不格式化、不改 GPT**。
   挂载会产生文件系统正常的日志/元数据写入，需要一并纳入批准范围。
3. opt-in 的 dracut hook 在目标块设备出现后开始工作，用设备事件而不是固定延时；验证 PARTLABEL、设备归属和挂载目标。
   不把任意内核参数当成可写分区路径。
4. 以 boot ID 创建新日志，目录权限 0700、文件 0600。采集 `/dev/kmsg` 的旧记录及后续记录，保留序号、时间和原始级别；
   同步保存 kernel release、cmdline 和 boot ID。必须记录首个可读序号、检查期间缺号，并区分启动前已丢失与采集中 overrun。
   本轮桌面试跑首序号为 279；后续必须尽早在 initramfs 开始采集，并把“开头缺失”标为不完整，不能仅看正常结束标记。
   若诊断启动的 printk 缓冲仍不足，再单独调整非默认诊断项，不改稳定默认项。日志里的本机数据只放 `private/`，不进 Git。
5. 采集器将历史记录写完并完成同步后，通过专用 fd 回报 `READY`。未收到有效 readiness 或进程已退出，就不得继续触发可疑驱动。
6. 切换真实根前明确停止/等待采集器、关闭文件和卸载日志挂载点，不能让 initramfs 孤儿进程一直持有旧根。
   与真实根 journald 的交接需要单独验证，不能默认没有空档。
7. 冷启动正对照：正常写入可辨认标记，关机/重启，回到稳定系统后自动读取并校验标记和日志。
   采集器启动失败、源不可读、已有日志路径等反例必须明确失败，不能悄悄继续实验。

aarch64 静态构建及 QEMU user 文件/FIFO 测试已离线通过，真实 kmsg/文件系统的运行态试跑也真机通过。
试跑脚本已实施设备身份、clean/未挂载、空间、16 MiB 进程上限、readiness/标记和只读读回检查；
仍需将这些约束可靠接入 dracut，补齐完整性判断、日志总量限额及生命周期交接，再做冷启动正对照。
**只有上述步骤都完成并经冷启动验证后，才算取证通道真机通过。**

### B. 把可疑驱动移到日志就绪之后

若故障发生在 `/init` 之前，A 自身仍无法取到失败现场。因此下一份独立诊断内核需要：

- 将目标显示/GPU 时钟提供者编成模块，并明确阻止它们在日志就绪前被 udev 自动加载。
  当前候选是 `CONFIG_SM_DISPCC_8750=m`、`CONFIG_SM_GPUCC_8750=m`；必须核对依赖及实际模块名。
- 不改变 UFS、基础时钟、引脚、互联等存储路径必需驱动的内建状态。
- 日志通道验证就绪后，**一次显式加载一个可疑模块**，每次之前/之后写阶段标记并同步；随后自动取回日志。
- 新诊断内核与模块同次构建，使用新的独立版本号；不复用旧版本，不让安装自动删掉唯一稳定内核。
- 现有 GPUCC initcall blacklist 不直接沿用为“修复”；诊断模块的加载策略需要独立核对。

这是调试基础设施，不是故障修复。它改变了探测顺序，原始失败可能不再出现；届时据日志设计最小对照，不能声称驱动已经正常。
如果基础 UFS/PM 驱动自己在更早阶段挂死，仍需继续缩小最小启动配置或建立更早的外部通道；不能承诺文件日志覆盖所有固件致命复位。

## 3. 已有的离线原型

`tools/bootlog/kmsg-to-file.c`：不自行挂载、不查找分区、不启动任何服务，输出必须由调用者明确指定。
不在生产 RPM 或现有设备启动项中自动启用；只加入主机上的 opt-in 诊断 initramfs。

实现：

- 从 `/dev/kmsg` 最早可用记录开始读取，之后按事件等待新记录；测试可替换为普通文件或 FIFO。
- 新建日志使用 `O_EXCL | O_NOFOLLOW | O_DSYNC`，不覆盖旧证据；同步新文件的父目录。
- 初始记录排空并同步后才发送 `READY`；遇到 kmsg overrun 会写出明确的丢失标记，而不是假装完整。
- SIGTERM/SIGINT 结束时写结束标记并同步；错误返回非零。
- `O_DSYNC` 只能保证成功完成的写入符合内核/存储的同步语义，不能保证控制器失效或复位前正在执行的那次写入。

离线测试：

```sh
python3 tests/bootlog-collector-test.py
```

主机编译和 9 项普通文件/FIFO 测试离线通过（`out/bootlog-test/collector-test.txt`）：原样重放、元数据、0600 权限、
不覆盖旧文件、拒绝源/目标和目录 symlink、无效输入失败、流式追加、readiness 在历史日志之后、
实际 fd 的 `O_DSYNC` 标志，以及信号停止（含 READY 后立刻停止的 20 次竞态对照）；self-pipe 避免信号早于 poll 时丢失唤醒。

2026-11-11 追加 aarch64 静态构建（约 689 KiB），并用 QEMU user 对同一二进制重跑以上 9 项测试，全通过：

```sh
BOOTLOG_BINARY=out/bootlog-test/aarch64/kmsg-to-file \
BOOTLOG_RUNNER=qemu-aarch64-static \
python3 tests/bootlog-collector-test.py
```

证据：`out/bootlog-test/aarch64/` 的构建记录、二进制哈希和测试报告。
测试入口可指定既有二进制和 runner，不会因为验证其他架构就接触真实 kmsg 或块设备。

上述离线测试本身**没有**证明真实设备行为。17:09 的独立运行态对照另行验证了真实 kmsg、同步文件和卸载读回。
仍未证明 dracut 时序、重启/硬复位后的完整性或当前启动故障已解决，不能当作已建立完整持久启动日志通道。

## 4. 本轮接入：只做够用的诊断链

用户澄清“不要过度测试”不是取消日志功能；最小修复与日志接入并行推进，不再扩展通用测试框架。

- `tools/bootlog/dracut/91opd2413-bootlog/`：generator 只在参数恰好一次 `rd.opd2413.bootlog=1` 时拉起服务。
  关闭时连设备依赖都不生成，不靠 Condition 跳过后仍等待磁盘。
- `Type=notify` / `NotifyAccess=main`：控制脚本最后 exec 采集器，PID 由 systemd 监督；旧日志同步且首序号 0、
  没有缺号/异常格式后才发 READY。初始丢失或运行中新缺号都会明确失败并保留不完整标记。
- 分区只允许指定 UFS LUN0 / sda17 / ARMADA_BOOT / 1 GiB / ext4，加私有 PARTUUID 和 FSUUID 双重绑定；
  未挂载且 clean 才尝试挂载，不修盘或重放脏日志。目录 0700，文件 0600；16 MiB 单文件、128 MiB 总量预算，空间不足不自动删除。
- 停止顺序：与 `initrd-cleanup.service` 冲突，先停采集器、记录结果、正常卸载；不 lazy/force umount，不让旧根被孤儿进程持有。
- 产物 `out/bootlog-initrd/stable-7.2.6-3-bootlog.initrd` = 原稳定镜像原样保留 + 4 字节对齐 + root-owned newc 附加层。
  不重打包原归档，所以原始设备节点和固件不丢失；这种混合归档由内核 `init/initramfs.c` 的 unpacker 支持。
  目标程序及依赖从当前稳定系统只读取得，私有身份文件仅在忽略目录/镜像内，未写进 Git。
- 已完成必要检查：aarch64 编译和目标程序、严格完整性/通知回归、真实只读身份样本、generator 开关、unit 依赖。
  没有为此重新跑全套发行版安装/EFI 启动链测试。以上都不能代替真机冷启动。

计划独立启动项沿用稳定 Image/DTB/原参数，只改用此诊断 initrd，加 `rd.opd2413.bootlog=1 log_buf_len=8M`。
后者只增大独立诊断项的 printk 缓冲，避免已知的开头覆盖；默认项不改。冷启动后自动检查旧运行态日志跨重启仍同哈希，
并取回本次 initramfs 的序号 0、连续记录、正常结束及 service.result。用户只选菜单，不需要拍照。

## 5. 写入和恢复边界

- 当前稳定桌面的单次日志试跑已经单独获批并完成；不继续追加试跑或改启动路径，也不再要求用户抓拍。
- 下一次设备写入需重新批准：离线集成通过后，独立 initramfs/非默认条目和一次冷启动正对照。
- 临时部署和私有日志登记技术债 #27；清理也需另行批准，不擅自删证据或旧 `/boot`。
- B 另行批准，不把新内核安装夹在 A 的日志验证里。
- ESP 不重格式化，不移动或重建 `KSHIM.CHO`，不修改默认稳定条目，不触碰 `boot_b`、GPT、Android 分区或原厂固件分区。
- 测试卡住时可能仍需要人工长按电源和选择稳定项；应当自动保存和读回日志，而不是要求用户掌握抓拍时机。
