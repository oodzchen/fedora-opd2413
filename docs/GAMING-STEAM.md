# Steam 客户端与大型 3D 游戏适配路线（OPD2413 / Fedora 45 aarch64）

目标：在当前**标准、可变的 Fedora 45 aarch64（KDE Plasma、SELinux Enforcing）**系统上，参考 `Zaviya`（SM8750 / 联想拯救者 Y700 Gen 4 `elden` 等设备的 SteamOS ARM 适配经验），在不破坏 Fedora 发行版包、启动链与现有硬件适配的前提下，逐步完成**性能基座 → Steam ARM64 + ARM64EC Proton / FEX → 高分屏缩放与外设 → 大型 3D 游戏极限稳态优化**的完整闭环。

设计约束（沿用 [ARCHITECTURE.md](ARCHITECTURE.md) 与 `AGENTS.md`）：

- **不覆盖 Fedora 原有系统文件**：所有系统级调优、启动器、可选 Vulkan 层和工具均以独立 RPM（如 `opd2413-gaming`）交付；不覆盖 KDE 桌面所依赖的 Fedora 原版 Mesa EGL/GBM，必要时仅按游戏通过 `VK_DRIVER_FILES` 注入独立 Turnip。
- **不关闭 SELinux**：始终保持 `SELinux Enforcing`，对 FEX JIT / Steam 容器触发的任何拒绝通过审计日志收敛最小策略。
- **无风扇被动散热优先**：OPD2413 没有主动散热风扇。借鉴 Zaviya 对同款无风扇 SM8750 平板（Y700 Gen 4）的实测结论，**禁止在性能档把 Oryon Prime 大核无脑锁死为 `performance` governor**（否则会迅速击穿热墙，导致 GPU 被动降频、实际帧率反而低于均衡档）；优化重心放在“降无效发热 + 瞬时提频响应 + 旁路供电 + 合理分辨率缩放”。
- **单变量推进与冷启动验收**：内核与系统启动路径（sysctl/udev/tmpfiles/initramfs）改动分步验证，先离线测试、经用户确认后再上机安装并做冷启动复核。

---

## 1. 现网基线核对（2026-11-19，内核 `7.2.15-30.opd2413`）

在 `opd2413-fd`（Fedora 45 aarch64）上实测确认：

### 已就绪能力（无需重复移植）

| 能力 | 现网实测证据 | 说明 |
|---|---|---|
| ARM64 4 KiB 页 + 抢占 | `CONFIG_ARM64_4K_PAGES=y`、`CONFIG_PREEMPT=y` | 兼容 FEX / Proton / Adreno |
| 非对齐原子模拟 / 兼容输入 | Armada `0505`、`0505a`、`0504` 已合入 | x86 多线程游戏与手柄/输入必需 |
| Oryon `ssbd_sigreturn` | `signal.c` 已有 `ssbd_sigreturn`，匹配 `MIDR_QCOM_ORYON_X1`；实测 `cpu0-5` `0x514f0014`、`cpu6-7` `0x513f0014`（均为 Implementer `0x51` / Part `0x001`） | **已自动命中**，Wine/Proton 信号返回不会意外关闭 SSBS |
| Proton `ntsync` | `CONFIG_NTSYNC=y`，`/dev/ntsync` 已存在且为 `0666` | Proton 可直接使用 `PROTON_USE_NTSYNC=1` |
| 任务级 `uclamp` | `CONFIG_UCLAMP_TASK=y`、`CONFIG_UCLAMP_TASK_GROUP=y`，普通用户实测 `uclampset -m 256` 生效 | 无需常驻 root 守护进程即可为游戏进程设置 `uclamp.min` |
| CPU / 内存基础 | `schedutil` 默认启用（`policy0` `384–3533 MHz`、`policy6` `1018–4090 MHz`、`rate_limit_us=45`）；`THP=madvise`；`zram0` 已启用 `8 GiB zstd` | 避免 FEX 内存膨胀并已有压缩交换空间 |
| GPU 与存储底座 | Adreno 830 OPP 最高 `1100 MHz`（14 档）；GMU 独立绑定与 `CM3_FAULT`/超时修复已合入；UFS MCQ（`0x01da0000`）已启用、`sda` `read_ahead_kb=1024`、`mq-deadline`；Fedora Mesa `26.2.6` 原生支持 Turnip | 图形与 I/O 基线健康 |
| 电池充电阈值接口 | `/sys/class/power_supply/qcom-battmgr-bat/charge_control_{start,end}_threshold` 可访问 | 支持插电玩游戏时通过阈值锁定实现类旁路供电控温 |
| Fedora 45 官方游戏生态包 | 仓库已自带 `fex-emu 2604`、`fex-emu-rootfs-fedora`、`fex-emu-thunks`、`gamescope 3.16.31`、`gamemode 1.8.2`、`mangohud 0.8.3`、`box64 0.3.6`、`vulkan-tools` | 大幅降低用户态维护成本 |

### 已确认缺口（按阶段逐项补齐）

| 缺口 | 现网值 | 目标值 / 方案 | 归属阶段 |
|---|---|---|---|
| `cpuidle` 调度器 | 仅编入 `menu`（`CONFIG_CPU_IDLE_GOV_TEO` 未启用） | 启用 `CONFIG_CPU_IDLE_GOV_TEO=y` 并开机切 `teo`，减少帧间误进深睡带来的卡顿与能耗 | 阶段 1 |
| GPU devfreq 采样周期 | `polling_interval=50` ms | 降至 `16` ms（对齐 60 Hz 帧周期，消除拉频滞后掉帧） | 阶段 1 |
| RT 音频线程默认 `uclamp.min` | `kernel.sched_util_clamp_min_rt_default=1024` | 降至 `64`，避免 PipeWire 实时线程把 CPU 顶到满频增加废热 | 阶段 1 |
| ZRAM `swappiness` 与脏页回写 | `vm.swappiness=60`、`dirty_ratio=20`（~2.8 GiB） | `vm.swappiness=150`、`vm.dirty_bytes=536870912`（512 MiB）、`vm.dirty_background_bytes=67108864`（64 MiB） | 阶段 1 |
| Remote Play / 音频防爆音缓冲 | 未配置 | `net.core.rmem_max=33554432`；PipeWire/Pulse 最低 quantum `1024/48000`（21 ms）防止 Q6APM 欠载爆音 | 阶段 1 |
| 游戏启动器与无风扇功耗/旁路供电工具 | 无 | 新增 `opd-game`（`uclamp` + `ntsync` + WineD3D Vulkan + FEX 预设 + 可选 `gamescope`）与 `opd-power`（无风扇档位、GPU 频率、旁路供电、温度遥测） | 阶段 1 |
| Steam ARM64 客户端与休眠保活层 | 未安装 | 部署 Valve ARM64 客户端（`steamrtarm64`）+ 防自更新 `steam.cfg` + `webhelper_acquire` Vulkan 层 | 阶段 2 |
| ARM64EC Proton / FEX-Emu 与 SELinux 策略 | 未安装 | 安装 Fedora `fex-emu*` 与 ARM64EC Proton（`Proton-CachyOS arm64` / `GE-Proton aarch64`），收敛最小 SELinux 放行规则 | 阶段 2 |
| 高分屏缩放与游戏覆盖层 | 未安装 | 安装/验收 `gamescope`（`3392×2400` 上 1/2 整数 `1696×1200` 或 FSR 升频）、`mangohud`、外接手柄/力反馈，按需编译 ARM64 `lsfg-vk` | 阶段 3 |
| 大型 3D 游戏长时热稳态与特化 Turnip | 待实测 | 30 分钟连续 3D 负载记录 CPU/GPU 频率与 `xo-thermal`/`gpuss` 温控节流点；若遇特定游戏 Turnip 缺陷再通过 `VK_DRIVER_FILES` 定向注入补丁版 Turnip | 阶段 4 |

---

## 2. 分阶段实施路线与验收判据

### 阶段 1：性能基座（`opd2413-gaming` + 内核 `7.2.15-31.opd2413`）

1. **步骤 1A — 独立性能基座包 `opd2413-gaming`**（`packaging/opd2413-gaming/`、`tools/build-gaming-rpm.sh`）
   - sysctl：`/usr/lib/sysctl.d/60-opd2413-gaming.conf`
   - udev：`/usr/lib/udev/rules.d/60-opd2413-gaming.rules`（`/dev/ntsync` `0666`、`3d00000.gpu` `polling_interval=16`）
   - tmpfiles：`/usr/lib/tmpfiles.d/60-opd2413-gaming.conf`（`cpuidle=teo`、`3d00000.gpu/polling_interval=16`）
   - 环境变量：`/usr/lib/environment.d/61-opd2413-gaming.conf`（`WINE_D3D_CONFIG=renderer=vulkan`）
   - PipeWire 音频底限：`99-opd2413-gaming-buffers.conf`（`pipewire.conf.d` 与 `pipewire-pulse.conf.d`）
   - CLI 工具：`/usr/bin/opd-game` 与 `/usr/bin/opd-power`
   - **验收判据**：离线 `rpmbuild` 与脚本单测通过；上机安装并冷启动后，`polling_interval=16`、`sched_util_clamp_min_rt_default=64`、`swappiness=150`、`dirty_bytes=536870912`、`rmem_max=33554432`、`opd-power status` 读数完整、扬声器播放无异常、`0 failed`、`Enforcing` 零新增 AVC。
2. **步骤 1B — 内核 `7.2.15-31.opd2413` 启用 `TEO` cpuidle**（`kernel/opd2413-7.2/config/m4-gaming.config`）
   - 仅新增 `CONFIG_CPU_IDLE_GOV_TEO=y`，单一变量无代码补丁风险；安装前先将 `7.2.15-30` 设为默认回退并清理最旧条目（`-28`）以留足 ESP 空间。
   - **验收判据**：安全单次引导与冷启动后 `/sys/devices/system/cpu/cpuidle/current_governor` 为 `teo`，`s2idle` 短休眠唤醒与 Wi-Fi/蓝牙/GPU/相机/触摸板无回归。

### 阶段 2：Steam ARM64 客户端 + ARM64EC Proton + FEX-Emu

1. 安装 Fedora 官方 `fex-emu`、`fex-emu-rootfs-fedora`、`fex-emu-thunks`、`vulkan-tools`，验证 `FEXInterpreter` 与 `vkcube`（原生 ARM64 及 FEX x86_64 路径）。
2. 部署 Valve 原生 ARM64 Steam 客户端（位于用户目录 `~/.local/share/Steam` 或受控安装脚本），配置防覆盖 `steam.cfg`、启动包装器，并在平板原生编译安装 `webhelper_acquire` 隐式 Vulkan 层（防止休眠唤醒后 Steam UI GPU 进程 `VK_TIMEOUT` 崩溃）。
3. 部署 ARM64EC Proton（`Proton-CachyOS arm64` / `GE-Proton aarch64`，自动应用 `toolmanifest.vdf` 去 `require_tool_appid` 与 `files/bin -> bin-arm64` 修复）。
4. 实机运行轻量 3D Windows 游戏（DX11 / Vulkan），抓取 SELinux `ausearch -m avc`，按最小权限原则收口 SELinux 策略。
5. **验收判据**：Steam 客户端在 KDE Wayland 下正常登录、下载、休眠唤醒不崩；轻量 3D 游戏通过 `opd-game` 启动，确认走 Adreno 830 Turnip 硬件渲染、`ntsync` 生效、`Enforcing` 下可稳定运行。

### 阶段 3：高分屏缩放、监控覆盖层与外设体验

1. 安装并验收 Fedora `gamescope`（`3.16.31`）与 `mangohud`（`0.8.3`）：验证在 KDE Wayland 下嵌套运行 `gamescope -W 3392 -H 2400 -w 1696 -h 1200 -F fsr -f -- ...`，核对鼠标/触控/手柄焦点、帧率限制、120/60 Hz 匹配及全屏撕裂/延迟表现。
2. 验证外接蓝牙/USB 手柄（Xbox / DualSense / Switch Pro）识别与震动反馈；按需评估 `InputPlumber`。
3. 按需在平板原生编译 ARM64 `lsfg-vk` Vulkan 层（参考 `Zaviya/external-and-mods/lsfg-vk`），支持帧生成加速。
4. **验收判据**：3D 游戏可在 `1696×1200`（整数/FSR）与 `1920×1200` 流畅全屏渲染，MangoHud 正常显示帧率/帧时间/GPU 负载，外接手柄按键与摇杆正常。

### 阶段 4：大型 3D 游戏极限调校与长时热稳态验收

1. 选取大型 3D 基准/实际游戏（DX11/DX12，分别覆盖 DXVK 与 VKD3D-Proton），在 `opd-game balanced` / `fast` / `fastest`（评估 `FEX_TSOENABLED=0` 收益与稳定性）下对比帧率与 1% Low。
2. 插电开启 `opd-power bypass on` 进行 20–30 分钟连续 3D 压力测试，采集 `cpu`/`gpu`/`xo-thermal`/`skin-thermal` 温度与频率曲线：
   - 核实 `sm8750-oneplus-pad2pro.dts` 中 `xo-thermal`（触发 GPU state 5 / `734 MHz`）及各 CPU thermal zone 节流阈值；
   - 据实测数据微调 `opd-power` 的 `silent` / `balanced` / `performance` 频率上限与 `uclamp.min` 档位，追求最高**稳态帧率**而非短时跑分峰值。
3. 若特定大型 3D 游戏命中 Mesa `26.2.6` Turnip 缺陷（例如 `TU_Z_MUTABLE` UBWC 或特定 shader 编译错误），再按需独立构建游戏专用 Turnip 共享库（通过 `opd-game --vk-icd` 定向加载，不影响桌面）。
4. **验收判据**：目标大型 3D 游戏通过 Steam 客户端直接启动，连续运行 ≥ 20 分钟无闪退/GPU hang/音频爆音，帧时间平稳、温控可预测且插电旁路供电有效降电池温升。

---

## 3. 当前阶段状态

状态词仅使用：`待调研`、`有源码线索`、`离线通过`、`真机启动`、`真机通过`、`真机失败`（未动手项记 `未开始`）。

| 阶段 | 内容 | 状态 | 说明 |
|---|---|---|---|
| 1A | 性能基座包 `opd2413-gaming`（sysctl/udev/tmpfiles/env/PipeWire/`opd-game`/`opd-power`） | 真机通过 | 2026-11-19 装机与冷启动复核通过，现已迭代至 `0.1-7`（新增 `/usr/bin/steam`、`ulimit -c 0`、`PROTON_USE_PIPEWIRE=0`、`FEX_PROFILESTATS=0`、`fastest` 零 TSO 屏障、`uclamp=320`、`vm.swappiness=60` 及 `opd-power profile sustained` `policy6 <= 3.51 GHz` + GPU `443..1100 MHz`，`Enforcing` 零 AVC） |
| 1B | 内核 `7.2.15-31.opd2413`（`m4-gaming.config` 启用 `CONFIG_CPU_IDLE_GOV_TEO=y`） | 真机通过 | 2026-11-19 重启验收通过并固化为默认启动项：`uname -r = 7.2.15-31.opd2413`、`CPUIDLE: teo`、`running`、`0 failed`、`Enforcing` 零 AVC、`KSHIM.CHO` 保持 `1 extent` |
| 2 | Steam ARM64 + ARM64EC Proton + FEX-Emu + SELinux 策略 | 真机通过 | 2026-11-19 真机全链路打通：补齐 28 个 ZIP 缺 `+x` 可执行文件（`steam-launch-wrapper`/`reaper`/`fossilize_replay`/`gameoverlayui`）、非阻塞 `steamerrorreporter` 桩、`steam.desktop` 与 7 档官方 PNG 图标、`libappindicator` 托盘图标、`steamoverlay_arm64.json` 覆盖层、用户级 `opd-drkonqi-filter` 静默 Wine 退出弹窗；实测《黑暗之魂 3》（AppID 374320）登录、下载、启动、游玩达 60 FPS（34.4 s 稳态中位 `16.78 ms` / `59.6 FPS`），全程 `SELinux Enforcing` 零 AVC |
| 3 | `gamescope` 高分屏缩放 + `mangohud` + 外接手柄 + 可选 `lsfg-vk` | 真机通过（主链路） | 2026-11-19 已原生编译部署 Zaviya `MangoHud v0.8.4`（高通 `msm_dpu` / Adreno 830 真实 GPU 温度/频率/负载）；已实测 `--gamescope` 1696×1200/1280×800 FSR 60 Hz 缩放（肉眼更顺但无风扇功耗偏高，轻/中载游戏推荐直出；外接手柄与可选 `lsfg-vk` 按需补测） |
| 4 | 大型 3D 游戏极限调优、长时热稳态、旁路供电与定向 Turnip 调校 | 进行中（关键突破） | 2026-11-19 实测突破：《黑暗之魂 3》在 `PROTON_DISABLE_HIDRAW=1 FEX_SMCCHECKS=none opd-game --mangohud fastest %command%` 下消除了 FEX `mtrack` 与 Arxan 定时内存校验触发的周期性卡顿，达成稳定满 60 帧且几乎无卡顿，退出弹窗经 `opd-drkonqi-filter` 实机静默；`opd2413-gaming-0.1-7` 全部内核/sysctl/udev 参数经冷启动持久化复核通过；待继续验证更高画质/其他大型 3D（含 DX12）游戏及 20–30 分钟插电旁路供电热稳态 |
