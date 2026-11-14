# 60 Hz 刷新率切换与在线 Modeset 黑屏调研报告

本文整理针对一加平板 2 Pro（OPD2413 / `erhai` / SM8750）在 Fedora 45（`7.2.15` 系列与 `7.2.6` 诊断基线）上切换 60 Hz 刷新率及在线 modeset 黑屏的调研证据、根因分析与修复方案。

相关背景：
- [docs/TECH-DEBT.md](TECH-DEBT.md) `#19`（`1411`）、`#20`（`1412` 只提供 120 Hz）、`#35`（`0068` 触发夜灯黑屏）。
- 本仓库内核补丁：[kernel/opd2413/1412-drm-panel-nt36536-offer-only-120hz.patch](../kernel/opd2413/1412-drm-panel-nt36536-offer-only-120hz.patch)、[kernel/armada-7.2.6/patches/0068-drm-msm-dpu-lutdma-dspp-igc-gamut.patch](../kernel/armada-7.2.6/patches/0068-drm-msm-dpu-lutdma-dspp-igc-gamut.patch)。

---

## 1. 结论摘要

1. **面板与设备树侧不存在“隐藏的 60 Hz 解锁 DCS 命令”**（已对照官方 Android `dtbo_10.dtbo` 与 `linux-sm8750-erhai` 源码验证）：
   官方系统实现 `120 / 144 / 90 / 60 / 50 / 48 / 30 Hz` 完全只靠拉长垂直前肩（VFP）配合立即前肩刷新率切换（`dfps_immediate_porch_mode_both_hv_porch`），像素时钟与水平时序保持不变，没有任何切帧率专用的面板 DCS 指令。
2. **60 Hz 切换失败与“60 Hz 时序本身”并非两个独立问题，两者同源于主线 DPU/DSI 在运行中执行在线 modeset（`active: 1->1, mode_changed=1`）时卡死硬件通路**：
   在保持 `120 Hz -> 120 Hz`（分辨率、刷新率、像素时钟、porch 全不变）的前提下开关 KDE 夜灯，触发 `mode_changed=1` 后会出现与 `120 -> 60 -> 120 Hz` 切换失败**一致**的 DPU 硬件卡死现场（`sspp_8` 停止取帧、VBIF `0x204/0x20c` 处于空闲/halt 位状态），而完整执行一次 DPMS 熄屏再亮屏（`active: 1->0` 再 `0->1`）均可恢复。
3. **官方 Android `msm_drm.ko` 之所以正常，有两方面机制差异**（通过反汇编 OEM `msm_drm.ko` 确认）：
   - 对仅修改 VFP/刷新率的切换，支持原地热更新时序（`sde_encoder_virt_modeset_rc` → `_sde_encoder_modeset_helper_locked` + `dsi_ctrl_hw_cmn_set_video_timing` 动态写 `V_TOTAL`），**不经过** DPU/DSI/DSC 整套拆卸重装。
   - 在确实需要 stop/start 时，不会在双 DSI 共享同一个 `CTL_0` 的循环里提前触发 per-phys 的 `CTL_SW_RESET`，而是有序停 phys、`sde_encoder_dce_disable`、使用 `sde_hw_ctl_reset_post_disable` 并对称管理 IRQ/资源与 CRTC 状态。

---

## 2. 多方对照核查结果

### 2.1 官方 Android `dtbo_10.dtbo` 与面板驱动对照

| 项目 | 官方 Android (`dtbo_10.dtbo`) | `linux-sm8750-erhai` | 本仓库当前状态 (`panel-novatek-nt36536.c`) |
|---|---|---|---|
| 支持刷新率 | `120 / 144 / 90 / 60 / 50 / 48 / 30 Hz` | `120 / 60 / 30 Hz` | `1412` 补丁把 `novatek_nt36536_vfp[]` 从 `{ 26, 2684, 8000 }` 限制为 `{ 26 }`（仅 120 Hz） |
| 切换机制 | `dfps_immediate_porch_mode_both_hv_porch`，仅改 VFP (`26, 26, 26, 2684, 2010, 2196, 8000`) | 与上游/主线 `msm` 相同的 modeset 路径，无单独 DFPS bypass | 水平时序与像素时钟不变，通过 VFP 改 `vsync_start` / `vsync_end` / `vtotal` |
| FPS 切换 DCS 命令 | 无 | 无 | 无 |

结论：不需要也不存在额外的 NT36536 切帧率私有 DCS 命令；`1412` 补丁中关于“可能缺少未知切帧率 DCS 命令”的猜测不成立。

### 2.2 `linux-sm8750-erhai` DPU/DSI 差异核查

对比 `linux-sm8750-erhai` 与本仓库 `7.2.15` 内核树的 `dpu_kms.c`、`dpu_crtc.c`、`dpu_encoder.c`、`dpu_encoder_phys_vid.c`、`dpu_hw_ctl.c`、`dpu_hw_intf.c`、`dsi_manager.c`、`dsi_host.c`、`dsi_phy_7nm.c`、`panel-novatek-nt36536.c`：

- `erhai` 在面板与显示节点定义上同源，在 DPU/DSI 上同样沿用上游 DRM atomic inline-modeset 链路。
- 该路径下没有现成的“免拆卸 VFP 热切”或双 phys `CTL_0` cleanup 修复补丁可直接移植。

---

## 3. KMS Devcoredump 硬件现场对比

为排除偶发状态干扰，对两类黑屏现场与各自恢复后的正常快照做全寄存器 4 字节粒度对比（均排除纯 DSPP 色彩查表区干扰）：

- **正常基线 A (`ok`)**：`7.2.15-10` 经 DPMS 熄屏再亮屏恢复后（DSPP 已启用但画面正常）。
- **夜灯黑屏 (`nl_fail`)**：`7.2.15-10` 在恒定 `120 -> 120 Hz` 下切换 Night Light（仅触发 `0068` 置 `mode_changed = true`，模式/时钟/porch 零变化）。
- **60 Hz 切回黑屏 (`60_fail`)**：`7.2.6` 在 `120 -> 60 -> 120 Hz` 切换后卡死；经整套关闭再开启恢复为 `kms-after-cycle`。

### 3.1 关键寄存器逐项对照

| 模块 / 偏移 | 含义线索 | `ok15` (`7.2.15` DPMS 重置后正常) | `nl15` (`7.2.15` 120→120 夜灯黑屏) | `ok6` (`7.2.6` 完整开关后恢复正常) | `f60` (`7.2.6` 120→60→120 黑屏) |
|---|---|---|---|---|---|
| `sspp_8 + 0x0d0` | 当前取帧行/地址进度 | `000bb700`（扫描中） | **`00000c80`**（停滞） | `0008b9e0`（扫描中） | **`00000c80`**（停滞） |
| `sspp_8 + 0x0d4` | 取帧状态 | `000bb783` | **`00000c80`** | `0008ba73` | **`00000c80`** |
| `sspp_8 + 0x0e0` | 取帧状态 | `000bad1c` | **`00000008`** | `0008afe1` | **`00000008`** |
| `sspp_8 + 0x0ec` | 取帧状态 | `00000008` | **`00000000`** | `00000004` | **`00000000`** |
| `sspp_8 + 0x0f8` | 取帧状态 | `070e070e` | **`00000000`** | `05400540` | **`00000000`** |
| `vbif + 0x204` | `VBIF_XIN_HALT_CTRL1` | `fffd0000`（bit17=0，XIN1 取帧中） | **`ffff0000`**（全 XIN 空闲） | `fffd0000`（XIN1 取帧中） | **`ffff0000`**（全 XIN 空闲） |
| `vbif + 0x20c` | `VBIF_AXI_HALT_CTRL1` | `00000000` | **`00000030`** | `00000000` | **`00000030`** |
| `ctl_0 + 0x804` | CTL 状态寄存器 | `00060006` | `00000006` | `00000006` | `00000006` |
| `top + 0x00c` | TOP 状态/控制 | `00000000` | `00000200` | `00000200` | `00000200` |
| `top + 0x010` | `MDP_INTR_EN` | `1c000000` | `00000000` | `00000000` | `00000000` |
| `top + 0x014` | `MDP_INTR_STATUS` | `00000000` | `28000300` | `28000300` | `28000300` |
| `intf_1/2 + 0x1c4` | `MDP_INTF_REV_7xxx_INTR_STATUS` | `00000000` | `00000a00` | `00000a00` | `00000a00` |
| `intf_1/2 + 0x268` | INTF 状态寄存器 | `000285a1` | `ffffffff` | `ffffffff` | `ffffffff` |
| `intf_1/2 + 0x0ac/0b0` | `FRAME_COUNT` / `LINE_COUNT` | 持续递增 | 仍在递增（时序在扫） | 持续递增 | 仍在递增（时序在扫） |
| `dsi0_ctrl + 0x0b0` | `DLN0_PHY_ERR` | `00098888` | `00088888` | `00098888` | `00098888` |
| `dsi0_ctrl + 0x10c` | `INTR_CTRL` (`DSI_IRQ`) | `aa21a800` | `aa21a800` | `aa21aa00` | `aa21a800` |

说明与排疑：
- **真正严格区分“正常出图”与“黑屏卡死”的三组寄存器特征**（在 `ok15` 与 `ok6` 两个完全不同内核版本的正常现场中一致成立，而在 `nl15` 与 `f60` 两个黑屏现场中一致异常）：
  1. `sspp_8` 停止取帧（`0x0d0=00000c80, 0x0d4=00000c80, 0x0e0=00000008, 0x0ec=0, 0x0f8=0`）；
  2. `vbif + 0x204`（`VBIF_XIN_HALT_CTRL1`）从 `fffd0000`（XIN1 活跃取帧）变为 `ffff0000`（全 XIN 空闲）；
  3. `vbif + 0x20c`（`VBIF_AXI_HALT_CTRL1`）从 `00000000` 变为 `00000030`。
- **关于 DSPP、`ctl_0 + 0x804`、`top + 0x010` 与 `intf_1/2 + 0x268`**：
  - `ctl_0` 的 DSPP 相关配置（`0x094=80c008c0`、`0x180=1`、`0x184=3`、`0x18c=6`、`0x844=0x33`）在 `nl15`、`f60` 与正常工作的 `ok15` 中完全相同，并非导致黑屏的直接原因；
  - `ctl_0 + 0x804`、`top + 0x010/0x014` 与 `intf_1/2 + 0x1c4/0x268` 在 `ok15` 与 `nl15` 间存在差异，但在同样正常显示画面的 `ok6`（`7.2.6` 空闲稳态抓取）中也为 `00000006` / `00000000` / `28000300` / `00000a00` / `ffffffff`，反映的是快照抓取时是否处于空闲节电/vblank 关中断窗口，而非卡死的唯一判据。
- **为什么确定“60 Hz 黑屏与 60 Hz 时序本身无关”**：`nl15` 在整个过程保持 `120 -> 120 Hz` 恒定时序与像素时钟，却触发了与 `f60`（`120 -> 60 -> 120`）完全一致的 `sspp_8` 停取 + `vbif 0x204/0x20c` 异常状态。两者共享的唯一触发条件是：**在显示开启时执行运行中在线 modeset（`active: 1->1, mode_changed=1`）**。

---

## 4. 内核代码路径根因分析

当任意操作在显示开启状态下令 `new_crtc_state->mode_changed = true` 且 `active` 保持 `1 -> 1` 时，`msm_atomic_commit_tail()`（`drivers/gpu/drm/msm/msm_atomic.c:213-324`）按以下顺序执行：

```text
msm_atomic_commit_tail()
  1. drm_atomic_helper_commit_modeset_disables(dev, state)
       ├─ disable_outputs():
       │    ├─ dpu_encoder_virt_atomic_disable()   [dpu_encoder.c:1439-1492]
       │    ├─ dsi_mgr_bridge_post_disable()       [dsi_manager.c:343-392]
       │    └─ dpu_crtc_disable()                  [dpu_crtc.c:1330-1407]
       ├─ drm_atomic_helper_update_legacy_modeset_state()
       └─ drm_atomic_helper_commit_crtc_set_mode()
  2. drm_atomic_helper_commit_planes(dev, state, 0)        <-- flags=0，而非 ACTIVE_ONLY
  3. drm_atomic_helper_commit_modeset_enables(dev, state)
       ├─ dsi_mgr_bridge_pre_enable()
       ├─ dpu_crtc_enable()                        [dpu_crtc.c:1409-1445]
       └─ dpu_encoder_virt_atomic_enable()         [dpu_encoder.c:1392-1437]
  4. dpu_kms_flush_commit() -> dpu_crtc_commit_kickoff()   [dpu_crtc.c:1195-1245]
```

对照官方 Android `msm_drm.ko` 反汇编，暴露出以下关键问题：

### 4.1 问题 1：双 DSI 共用 `CTL_0` 在 `disable` 循环中被提前、重复硬复位

在 `dpu_encoder_virt_atomic_disable()`（`drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c:1471-1476`）中按索引循环关闭物理编码器：

```c
for (i = 0; i < dpu_enc->num_phys_encs; i++) {
    struct dpu_encoder_phys *phys = dpu_enc->phys_encs[i];
    if (phys->ops.disable)
        phys->ops.disable(phys);
}
```

而在 `dpu_encoder_phys_vid_disable()`（`dpu_encoder_phys_vid.c:604-675`）中：
- `i = 0`（slave，例如 `intf2`）关 timing 后，因为 `!dpu_encoder_phys_vid_is_master(phys_enc)`，**直接跳过等待 vsync**，立即调用 `dpu_encoder_helper_phys_cleanup(phys_enc)`（`dpu_encoder.c:2371-2461`）。
- `dpu_encoder_helper_phys_cleanup()` 内**直接执行**：
  - `ctl->ops.reset(ctl)`（写 `CTL_SW_RESET`，超时时还会走 `dpu_hw_ctl_force_reset()` 的 `CTL_SW_RESET_OVERRIDE` 强复）；
  - 清空全部 blendstage 与 `CTL_FETCH_PIPE_ACTIVE`；
  - 循环把**所有** `dpu_enc->phys_encs[0..n-1]` 的 `hw_intf` 都绑定为 `PINGPONG_NONE`；
  - 调用 `dpu_encoder_unprep_dsc(dpu_enc)` 并置 `dpu_enc->dsc = NULL`；
  - 对共用 `ctl_0` 触发 `trigger_flush(ctl)` + `trigger_start(ctl)`。
- **此时 `i = 1`（master，`intf1`）的 timing engine 尚未关闭**。接着进入 `i = 1` 时，`intf1` 才写 `enable_timing(0)`、在已被拆空的 CTL/PP 上等待 vsync，随后再次执行一遍 `dpu_encoder_helper_phys_cleanup()`（此时 `dpu_enc->dsc` 已为 `NULL`）。
- `dpu_encoder.c:2384-2388` 自身也带有 `TODO` 注释，指出应把一次性的 CTL flush/trigger 等操作移出 per-phys cleanup。
- **对比 OEM `msm_drm.ko`**：`sde_encoder_virt_modeset_rc` 走完全不同的清理序——先停止物理编码器，再调用 `sde_encoder_dce_disable`，CTL 侧调用 `sde_hw_ctl_reset_post_disable` 而不是在循环中途打 `CTL_SW_RESET`。

### 4.2 问题 2：`modeset_disables` 与 `modeset_enables` 之间夹带 `commit_planes(flags=0)`，且热切走完整资源拆卸

- **中间态平面提交**：`msm_atomic_commit_tail()` 第 248 行调用 `drm_atomic_helper_commit_planes(dev, state, 0)`（未使用 `DRM_PLANE_COMMIT_ACTIVE_ONLY`）。此时 `dpu_enc->enabled == false`、`dpu_enc->crtc == NULL`、`dpu_crtc->enabled == false`、`rc_state == DPU_ENC_RC_STATE_OFF`、`dsi_mgr_bridge_post_disable` 已关 DSI/PHY，却先把平面与 `dpu_crtc_atomic_flush()` 下发，再进入 `commit_modeset_enables()`。
- **VFP-only 切换缺少无缝路径**：`120 <-> 60 <-> 30 Hz` 时分辨率、pixel clock、DSC 与水平时序完全一致，只有垂直前肩（`vfp` / `vsync_start` / `vsync_end` / `vtotal`）变化。主线因为没有类似 OEM `sde_encoder_virt_modeset_rc` / `dsi_ctrl_hw_cmn_set_video_timing`（只刷 timing / `V_TOTAL` 不停链路）的逻辑，每次切刷新率都被迫关断并重开双 DSI host/PHY、DPU IRQ（`DPU_ENC_RC_EVENT_STOP`）、DSC 和 `CTL_0`。
- **Night Light 误触发 modeset (`0068`)**：`dpu_crtc_check_mode_changed()`（`dpu_crtc.c:1667-1668`）因按需动态增删 DSPP，在开/关夜灯时强置 `mode_changed = true`，把纯色彩属性变更拖进整条在线 modeset 故障链（`#35`）。
- **DSI 时钟保护范围遗漏 SM8750**：`drivers/gpu/drm/msm/dsi/dsi_host.c:2274-2284` 中避免运行期重设 link clocks 的判断只针对 `qcom,sm8250`。

---

## 5. 下一步修复计划（状态追踪）

按从“止血稳定”到“根治多刷新率与在线 modeset”的顺序推进：

1. **修复在线 modeset（`active: 1->1, mode_changed=1`）核心缺陷（`kernel/opd2413-7.2/patches/2411`）** — *状态：真机通过（`7.2.15-18.opd2413`）*
   - 重构 `dpu_encoder_virt_atomic_disable()` / `dpu_encoder_helper_phys_cleanup()`：保留原始 `phys_encs[]` 停用顺序（`phys_0`/`cur_master` 先、`phys_1`/从端后；二分 `-16`/`-17` 证明若先停从端再停主端，会在后续 `DPMS off -> on` 触发 `dsi0` `ERR_CONTENTION_LP1` 与 `dsi1 cmd dma timeout`），并在全部物理编码器停用后再按共享 `hw_ctl` 执行一次 `dpu_encoder_helper_phys_cleanup()` 及全部 phys mixer/`CTL_INTF_ACTIVE` 清理。
2. **恢复 120 / 60 / 30 Hz 模式列表（`kernel/opd2413-7.2/patches/2413`）** — *状态：真机通过（`7.2.15-18.opd2413`）*
   - 放开 `1412` 补丁中 `novatek_nt36536_vfp[] = { 26, 2684, 8000 }`（覆盖 120 / 60 / 30 Hz）；实机验证 `120 -> 60 -> 30 -> 120 -> 60 -> 120 Hz` 连续在线切换正常出图且三档下 `DPMS off -> on` 全通过。
3. **常驻分配 DSPP 以消除 `#35` 夜灯故障（`kernel/opd2413-7.2/patches/2412`）** — *状态：真机通过（`7.2.15-18.opd2413`）*
   - 在 `dpu_encoder_update_topology()` 预先分配 `num_dspp = num_lm`，并在 `hw_dspp` 已持有时取消 `ctm` 触发 `mode_changed = true`；实机确认 Night Light 色温调节与 `6500K` 清零零 modeset。
4. **编译、离线测试与获批后上机验收** — *状态：真机通过（`7.2.15-18.opd2413`；后经 `-19`..`-22` 补全 `2414` 并最终真机通过）*
   - 已通过 `120 <-> 60 <-> 30 Hz` 内联切换、`120/60/30 Hz` 多轮 `DPMS off -> 1s/2s -> on`、Night Light `dspp_0_pcc`/`dspp_1_pcc` 验证与 `s2idle` 唤醒。
5. **后续 `-18` 手动 60 Hz 回归与 `2414` 分支隔离（`7.2.15-19..22.opd2413`）** — *状态：真机通过（`7.2.15-22.opd2413`），残留技术债记入 `#36` / `#37`*
   - 用户在 `-18` 上于 KDE 设置手动切换 `60 Hz` 时仍复现 `CTL_0` 卡死黑屏（且连带 120 Hz 黑屏）。
   - 控制变量对照（`-19` vs `-20` vs `-21`）证明唯一变量在于 `_dpu_encoder_helper_phys_cleanup()` 末尾的 `ctl->ops.trigger_flush(ctl); ctl->ops.trigger_start(ctl);`：
     - **保留调用（`-19`）**：`DPMS off -> 3s -> on` 4/4 通过，但在线切换 `CTL_0` 卡死；
     - **全部跳过（`-20` 含二次 reset、`-21` 仅跳过 trigger）**：在线 `120 <-> 60 <-> 30 Hz` 全部通过，但 `DPMS off -> 3s -> on`（`mdss_gdsc` 掉电再上电）必在下次亮屏时于 `DSI1` 发送初始化 DCS（`ff 20` / `fb 01`）处触发 `dsi1 cmd dma timeout` 与 `vblank timeout`。
   - **修复方案（`2414` / `7.2.15-22.opd2413`）**：在 `dpu_encoder_virt_atomic_disable()` 中按 `new_state && new_state->active`（以及编码器绑定未迁移）判定在线 modeset，仅此时对 `INTF_MODE_VIDEO` 跳过 `trigger_flush`/`trigger_start`；`DPMS off` 仍保留调用。
   - **当前定位**：`7.2.15-22` 实机自动化（`120/60/30 Hz` 互切、三档 DPMS、夜览、`s2idle` 唤醒及唤醒后再切换）与用户手动切换均正常通过；但 `2414` 本质上仍是软件状态代理规避（未做寄存器级硬件状态机溯源，且未做 seamless VFP 热切），以及快速切换时 `nt36536` 偶发 `-112` 竞争日志，已分别登记为 [TECH-DEBT.md](TECH-DEBT.md) `#36` 与 `#37`。
