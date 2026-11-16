# 构建软件包与离线测试

`noarch`、固件包及交叉编译内核打包在宿主机（`x86_64` Fedora）直接执行、不依赖平板；用户态需要编测 `aarch64` C++/Python 的包默认通过 SSH 调度平板的 SM8750 Fedora 原生执行（也可传 `--local` 退回宿主机 QEMU 容器）。所有产物统一归档到被 Git 忽略的 `out/` 下。

## 构建分工

| 脚本 | 打包内容 | 默认构建节点 | 兜底/备注 |
|---|---|---|---|
| `tools/build-kernel-rpm.sh` | `kernel-opd2413` | 宿主机打包（`aarch64-linux-gnu-gcc` 交叉编译产物） | 保留宿主机独立救砖/编包能力 |
| `tools/build-firmware-rpm.sh` | `opd2413-firmware` | 宿主机 | 从本地固件目录按清单打包 |
| `tools/build-device-rpms.sh` | `opd2413-device`、`opd2413-audio` | 宿主机 | `noarch` 配置包 |
| `tools/build-netshare-rpm.sh` | `opd2413-netshare` | 宿主机 | `noarch` Python/systemd 包 |
| `tools/build-camera-rpm.sh` | `opd2413-camera` | **平板原生（默认）** | 传 `--local` 退回宿主机 `arm64` 容器 |
| `tools/build-face-rpm.sh` | `opd2413-face` | **平板原生（默认）** | 传 `--local` 退回宿主机 `arm64` 容器 |
| `tools/build-libcamera-rpm.sh` | `libcamera*` / `python3-libcamera` | **平板原生（默认）** | 支持 `REUSE_BUILD=1` 复用编译树及 `--local` |
| `tools/build-sensors-rpm.sh` | `opd2413-sensors` | **平板原生（默认）** | 传 `--local` 退回宿主机 `arm64` 容器 |

## 平板原生 ARM64 编译（用户态包）

共享辅助库 [../tools/tablet-build-common.sh](../tools/tablet-build-common.sh) 为用户态 `aarch64` 构建脚本提供统一调度，架构遵循“**宿主机管源码校验与产物归档，平板只做无状态原生算力节点**”：

1. **宿主机前置校验**：模型/源码压缩包/ROM 校准文件仍在宿主机完成 `sources.json` / `rom-config.json` 的 SHA-256 校验，再通过 `OPD_OS=fedora private/ssh.sh` 探活平板（确认架构为 `aarch64`，且电池电量 `>=15%` 或处于充电状态；不可达时直接报错并提示唤醒平板或改用 `--local`）。
2. **工作目录与闪存零磨损**：常规构建仅把最小必要上下文经 `tar` 流式传入平板 `/tmp/opd-build-*`（内存盘 `tmpfs`），脚本结束时通过 `EXIT` trap 自动清理，不写入长期文件；`build-libcamera-rpm.sh` 启用 `REUSE_BUILD=1` 时使用 `/var/tmp/opd-build-libcamera` 保留 `BUILD/` 增量树。
3. **防休眠与留核限流**：远端构建统一套用 `systemd-inhibit --what=idle:sleep` 防止长编过程中平板休眠断网；并行度在平板上动态取 `nproc - 1`（8 核 SM8750 上固定为 `-j7`），始终留出至少 1 核保障 KDE 前台流畅。
4. **环境隔离与镜像缓存**：
   - `build-face-rpm.sh`、`build-libcamera-rpm.sh`、`build-sensors-rpm.sh` 在平板 `podman` 内自动构建并复用持久化原生镜像 `localhost/opd2413-builder-<pkg>:fc45`（`dnf` 包缓存目录挂载于平板 `/var/tmp/opd2413-dnf-cache`），不往平板日常系统装一堆 `-devel` 头文件；其中 `libcamera` 镜像会按 `.spec` 中 `BuildRequires`/`BuildConflicts` 的哈希自动判别重建。
   - `build-camera-rpm.sh`（纯 Python + Qt/OpenCV/NumPy 应用）直接复用平板已装的运行库，仅在首次缺包时按需补齐 `rpm-build`/`python3-devel`/`desktop-file-utils`，随后数秒内即可完成原生 `rpmbuild` 与 `%check`。
5. **常用切换参数与环境变量**：
   ```sh
   # 默认平板原生编译（示例）
   tools/build-camera-rpm.sh 0.1 1
   REUSE_BUILD=1 tools/build-libcamera-rpm.sh 3

   # 平板离线/未开机时回退宿主机 QEMU aarch64 固化镜像容器（--local 或环境变量）
   tools/build-camera-rpm.sh --local 0.1 1
   OPD_BUILD_TARGET=local tools/build-face-rpm.sh 0.1 1

   # 当上游依赖更新时，强制重建固化构建镜像（--rebuild-image 或 OPD_REBUILD_IMAGE=1）
   tools/build-libcamera-rpm.sh --rebuild-image 3
   ```

## 需要的输入

| 输入 | 位置 | 说明 |
|---|---|---|
| 内核构建产物 | `<armada>/output/opd2413-stage4/kern2/out/armada-kernel-7.2.6.tar.zst` | SHA-256 `7c6d84fa…`，见 [../kernel/README.md](../kernel/README.md) |
| 固件 | `<armada>/system_files/usr/lib/firmware` | 62 个原厂文件在该仓库的忽略目录里，9 个 WCN7860 文件是已提交的 |
| 设备文件 | 本仓库 `device/` | |

`<armada>` 是 armada 仓库 `oneplus-pad-2-pro` 分支的检出。

主机需要 `rpm-build`、`podman`、`qemu-user-static`（仅 `--local` 跑 aarch64 容器及离线安装测试需要）、`qemu-system-aarch64`、`mtools`、`zstd`。

## 构建

```sh
cd ~/github/fedora-opd2413
A=~/github/armada

tools/build-kernel-rpm.sh   out/kernel-7.2.6-2.opd2413.tar.zst 7.2.6-2.opd2413 1   # 内核树的构建见 kernel/README.md
tools/build-firmware-rpm.sh 16.0.10.600 1 $A/system_files/usr/lib/firmware
tools/build-device-rpms.sh  0.1 5
tools/collect-rpms.sh       # 汇总到 out/rpms/ 并生成 SHA256SUMS
```

参数依次是版本和 release。规则：

- 改了 `device/` 下任何文件，`build-device-rpms.sh` 的 release 加一。
- 内核每次重新构建都要换版本串或 release，不复用（模块 BTF 必须与内核配套）。
- 固件包的版本取原厂 OTA 的版本号。
- 重新构建同名包之前先删掉 `out/rpmbuild/RPMS` 里的旧文件，`collect-rpms.sh` 要求每个包只有一份。

当前平板上的一套（2026-11-11）：`kernel-opd2413-7.2.6-2.opd2413`、`opd2413-firmware-16.0.10.600-1`、
`opd2413-device-0.1-5`、`opd2413-audio-0.1-5`。

## 测试

```sh
tests/ufs-guard-test.sh                                   # 几秒

tests/package-install-test.sh out/rpms out/pkg-test       # 约 3–5 分钟（首次要下载依赖）

export ARMADA_REPO=$A
export UBOOT_QEMU=$A/output/opd2413-stage4/install1/uboot-qemu/build/u-boot-nodtb.bin
export GPT_DIR=$A/output/opd2413-stage4/install1/gpt-plan
export ABL_FDT=~/oneplus-pad2pro-backup/fdt/runtime.dtb
tests/qemu-esp-boot.sh private/esp-20261110/esp-sda16.img out/pkg-test/esp out/qemu-test   # 约 6 分钟
```

| 测试 | 验证什么 | 通过标志 |
|---|---|---|
| `ufs-guard-test.sh` | Android 分区被置为只读，`ARMADA*` 三个分区保持可写 | 打印一行总结，退出码 0 |
| `package-install-test.sh` | 在干净的 Fedora 45 aarch64 里装四个包后，ESP 布局、启动条目、initramfs 里的 67 个设备固件、Fedora 内核被排除；以及 initramfs 缺固件时内核安装被拒绝 | `PASS: package install` |
| `qemu-esp-boot.sh` | 平板同款 U-Boot 读取"真实 ESP 副本 + 上一个测试产出的 Fedora 文件"，systemd-boot 启动 Fedora 条目的内核 | `PASS: systemd-boot started the Fedora entry's kernel` |

注意：

- `package-install-test.sh` 的退出码才是结果。用管道接 `tail` 之类会吞掉退出码。
- podman 的 aarch64 容器用了 `--network host`：主机的代理环境变量指向 `127.0.0.1`，
  不用主机网络的话容器里连不上。
- `qemu-esp-boot.sh` 会一直等到时限（默认 300 秒，`QEMU_DEADLINE` 可调），因为内核启动后不会返回。
  判据是 U-Boot 的 ExitBootServices 钩子有没有触发。它证明到内核 EFI stub 退出启动服务为止，
  不证明内核能在真机上跑起来。
- `qemu-esp-boot.sh` 依赖的 U-Boot 二进制是 Armada 时期的产物，见技术债 #13。

改了 `device/`、任何 spec 或内核产物之后，三个测试都要重跑，再往平板上装。
