# AGENTS.md

本仓库把标准、可变的 Fedora 45 aarch64（KDE Plasma）适配到一加平板 2 Pro
（OPD2413 / erhai / SM8750，16 GB + 512 GB），与 ColorOS 双启动。

本文件只写规则和已确认的决定，不写进度。进度看 [docs/STATUS.md](docs/STATUS.md)，
架构看 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 用户已确认的决定

| 日期 | 决定 |
|---|---|
| 2026-11-10 | 发行版：标准可变的 Fedora 45 aarch64，不用 bootc / ostree / 容器化根 |
| 2026-11-10 | 桌面：KDE Plasma |
| 2026-11-10 | 现有 Armada 不需要保留，Fedora 直接取代它（`ARMADA_ROOT` 上的数据可清除） |
| 2026-11-10 | 内核分两步：先原样沿用已验证的 Armada 7.2.6 内核只换发行版，再升到 Fedora 45 的当前内核并合入 erhai 的功能（决定时以为是 7.2.x，核对后是 7.3.x；第二步已被 2026-11-11 的路线调整取代） |
| 2026-11-10 | 手写笔（笔输入、笔充电 CPS8601、配对）不在范围内 |
| 2026-11-10 | 新仓库 `~/github/fedora-opd2413`，先写架构文档和进度记录，再逐步实施 |
| 2026-11-10 | Fedora 账户与区域：登录名 `colin`、显示名 `Colin`、系统语言英文、时区 `Asia/Singapore`。初始密码由用户给出，只放 `private/install.env` |
| 2026-11-10 | 用户说"先不动"时指的是：先更新文档和进度、把后续步骤写清楚，不是让我等着或改方案。写入仍需单独批准 |
| 2026-11-10 | Armada 的数据（含 home 里约 35 GiB 的 Steam 游戏和文件）不保留，1.8 时全部删除 |
| 2026-11-11 | **内核路线调整**：留在已验证的 7.2 系列（内核 3，Armada 7.2.6），在它上面按功能逐项合入 erhai 的改动（休眠、充电、蓝牙、摄像头、传感器、合盖等），每项单独上机验收。升到 Fedora 45 当前内核（7.3.x）暂停，等 erhai/上游做完对应版本再跟。取代 2026-11-10"内核分两步"里的第二步。理由：erhai 的功能本身基于 7.2.15，不需要 7.3；Fedora 45 用户态在 7.2 上已真机验收；7.3 上 GPU、Wi-Fi、音频都出了新问题（[docs/M3-KERNEL.md](docs/M3-KERNEL.md)） |
| 2026-11-11 | 本项目的发现和修复可以回馈 erhai 仓库（`linux-sm8750-erhai`、`onepluspad-2pro-mainline`）。每次提 issue、PR 或推送前仍先问用户；内容不带本机唯一数据 |
| 沿用 | ColorOS 保留；启动链 kShimC → U-Boot → systemd-boot 保留；OEM ABL 不替换 |

## 设备安全规则

1. **永不触碰**：`abl`、`persist`、`modem` 及其他原厂固件分区。刷 OpenABL 会硬砖（ABL 由 OEM 熔丝签名）。
2. **只有三个分区归 Linux**：LUN0 的 `ARMADA`（ESP，sda16）、`ARMADA_BOOT`（sda17）、`ARMADA_ROOT`（sda18）。
   其余分区在 Linux 下由 ufs-guard 置为只读。不改 GPT，除非用户单独批准。
3. **ESP 不重新格式化、`KSHIM.CHO` 不移动不重建**：kShimC 的菜单记忆绑定这个文件的分区 GUID 和 extent。
4. **`boot_b` 不随日常更新改写**。确需改写时：整分区镜像、保留 AVB vbmeta 和 footer、写后整分区回读校验
   （见 armada 仓库 `ONEPLUS_PAD2_PRO_DUALBOOT_PLAN.md` §19.39）。A 槽不可启动，不切槽。
5. 每条设备命令带 serial；离开 Android 前读电量；对状态不明的设备不发写命令。
6. **每一步对设备的写入先向用户说明范围并得到确认**。只读查询（adb 读取、分区回读）可以直接做。
7. `adb shell` 已经是 root，不要再套 `su -c`。susfs 会伪造 getprop，以 `/proc/bootconfig` 为准。
8. Linux 侧的监听服务只绑定到指定地址，不监听所有接口（平板会连上家里的 Wi-Fi）。

## 工作规则

- 一次只改一个变量；同样的失败第二次出现就停下来找最早出错的层。
- 上机前在 [docs/WORKLOG.md](docs/WORKLOG.md) 写预期和判据，上机后当天写结果和证据位置。
- 临时做法必须在同一次改动里登记到 [docs/TECH-DEBT.md](docs/TECH-DEBT.md)。
- 状态只用这几个词：待调研、有源码线索、离线通过、真机启动、真机通过、真机失败。
  驱动加载、服务在跑、节点存在都不等于"真机通过"。
- 改启动路径（unit、udev、initramfs、启动参数、ESP）必须冷启动验证。
- 会话结束前更新 STATUS.md 的"唯一下一步"、阻塞和设备状态。

## 不能进仓库的东西

`private/` 和 `out/` 被 Git 忽略。下面这些只放 `private/`：

- 原厂固件、从 OTA 或设备提取的任何二进制。
- 本机唯一数据：序列号、MAC、蓝牙地址、校准、分区 GUID、Wi-Fi 名称、IP。
- 原始日志、分区备份、镜像。

提交前检查文档和脚本里没有 adb serial、`/home/...` 路径和上述标识。

## 提交

- 只在用户要求时提交和推送。建远端仓库、推送、发版都先问用户。
- AI 完成的提交只加 `Co-Authored-By:`，不代人签名。
- 引入第三方补丁保留原作者和来源，登记在 `kernel/PATCHES.md`。

## 相关位置

| 内容 | 位置 |
|---|---|
| Armada 移植分支（内核补丁、U-Boot、kShimC 后端、历史记录） | `~/github/armada`，分支 `oneplus-pad-2-pro` |
| kShimC | `~/github/kShimC` |
| erhai 参考内核（7.2.14）与 Ubuntu 集成 | `~/github/linux-sm8750-erhai`、`~/github/onepluspad-2pro-mainline` |
| 分区与 Android 数据备份 | `~/oneplus-pad2pro-backup` |
| 原厂 OTA 提取物、工具 | `~/oneplus-pad2pro-work` |
