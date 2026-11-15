# Fedora on OnePlus Pad 2 Pro (OPD2413)

在一加平板 2 Pro（OPD2413 / SM8750）上运行**标准、可变的 Fedora 45 aarch64 + KDE Plasma**，与 ColorOS 双启动。

Fedora 系统软件由 `dnf` 原样管理，设备适配通过独立的内核与用户态 RPM 包注入，不修改发行版自带文件。

## 当前支持情况

- **基础与显示**：Adreno 830 硬件渲染（stock Mesa）、120/60/30 Hz 刷新率切换、Night Light 色温调节、DPMS 熄屏断电、亮度调节
- **输入与外设**：触控、Pogo 磁吸键盘与触控板、s2idle 休眠与开盖/键盘唤醒
- **连接与音频**：Wi-Fi（含 5 GHz AP）、蓝牙、扬声器、麦克风
- **多媒体与传感器**：H.264/HEVC 视频硬解、自动旋转 / 环境光 / 陀螺仪 / 指南针、前后摄像头基础拍照录像
- **特色适配**：
  - [opd-netshare](netshare/)：手机蓝牙唤醒 + 5 GHz Wi-Fi Direct 自动共享移动网络
  - [opd2413-face](packaging/opd2413-face/)：锁屏与 `sudo`/`polkit` 原生人脸解锁

> **已知局限**：手写笔不在适配范围内；后摄物理自动对焦（`cn3927`）暂不可用；9 V 充电正常，PPS 快充待测。完整状态见 [docs/STATUS.md](docs/STATUS.md) 与 [docs/TECH-DEBT.md](docs/TECH-DEBT.md)。

---

## 如果你想在自己的平板上使用

本项目不提供开箱即用的刷机包，你需要自己完成以下 4 步准备和构建工作：

### 1. 准备双启动分区与引导链（前置条件）
本仓库**不包含**启动链改造和分区工具。**当前方案是在 ArmadaOS 的安装分区与引导链基础上进行覆盖性安装的**——直接复用其划分好的 `ARMADA`（ESP）、`ARMADA_BOOT`、`ARMADA_ROOT` 三个分区以及 `kShimC` + `U-Boot` 启动链，将 `ARMADA_ROOT` 替换为 Fedora。

如果你还没有双启动环境，从零开始调整分区与刷写 `boot_b` 的完整前置步骤请直接借鉴 **ArmadaOS**（`oneplus-pad-2-pro` 分支）。
> **安全红线**：切勿替换原厂 OEM ABL，切勿触碰 `persist`、`modem`、`abl` 等原厂固件分区。

### 2. 自备原厂固件
仓库**不分发任何原厂二进制固件**。你需要自行从本机或对应版本的 ColorOS OTA 中提取所需的固件（如 GPU、视频、Wi-Fi/蓝牙、DSP 及传感器校准/registry 文件），放入本地目录用于打包 `opd2413-firmware`。

### 3. 在主机上构建 RPM 软件包
在 Fedora x86_64 主机上安装构建与测试依赖（`rpm-build`、`podman`、`qemu-user-static`、`qemu-system-aarch64`、`mtools`、`zstd`），然后：
1. 参考 [kernel/README.md](kernel/README.md) 准备内核构建产物；
2. 运行 `tools/build-*.sh` 构建内核、固件、设备适配、音频、传感器等 RPM 包，并用 `tools/collect-rpms.sh` 汇总到 `out/rpms/`；
3. 运行 `tests/` 下的离线安装与 QEMU 启动测试。

具体命令与版本规则见 [docs/BUILD.md](docs/BUILD.md)。

### 4. 部署到平板
通过 SSH 将 `out/rpms/` 以及 `tools/install-rootfs.sh`、`tools/install-kernel.sh` 传到平板运行：
- `tools/install-rootfs.sh <用户名> <显示名>`：在 `ARMADA_ROOT` 的 btrfs 顶层创建子卷并安装 Fedora 45 KDE（支持用环境变量 `OPD_USER_PASSWORD`、`OPD_TIMEZONE`、`OPD_MIRROR` 自定义密码、时区与镜像源）；
- `tools/install-kernel.sh`：安装内核与设备包并配置 ESP 引导条目。

完整安装流程与避坑指南见 [docs/M1-INSTALL.md](docs/M1-INSTALL.md)。

---

## 文档导航

| 文档 | 说明 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 整体架构、启动链与存储布局 |
| [docs/STATUS.md](docs/STATUS.md) | 当前实现进度与最新设备状态 |
| [docs/BUILD.md](docs/BUILD.md) | RPM 软件包构建与离线测试指南 |
| [docs/M1-INSTALL.md](docs/M1-INSTALL.md) | 首次安装到机内的完整操作手册 |
| [docs/HARDWARE.md](docs/HARDWARE.md) | 硬件清单与各模块复用来源 |
| [docs/TECH-DEBT.md](docs/TECH-DEBT.md) | 已知问题与待解决的技术债 |
| [docs/WORKLOG.md](docs/WORKLOG.md) | 开发与真机测试日志 |
| [AGENTS.md](AGENTS.md) | 仓库开发规范与设备安全规则 |

## 参考项目

- **ArmadaOS**：[oodzchen/armada](https://github.com/oodzchen/armada)（`oneplus-pad-2-pro` 分支）— 双启动分区方案、U-Boot 与基础内核移植
- **kShimC**：[oodzchen/kShimC](https://github.com/oodzchen/kShimC) — `boot_b` 启动菜单与 ColorOS / Linux 双启动切换
- **erhai（OnePlus Pad 2 Pro Mainline）**：[yzddmr6/onepluspad-2pro-mainline](https://github.com/yzddmr6/onepluspad-2pro-mainline) 与 `linux-sm8750-erhai` — 7.2 内核特性（休眠、充电、蓝牙、摄像头、传感器、合盖等）的主要参考来源
- **其他上游参考**：[linux-msm/hexagonrpc](https://github.com/linux-msm/hexagonrpc)、[xiaomipad-8pro-mainline](https://github.com/yzddmr6/xiaomipad-8pro-mainline) / [xiaomipad-6pro-mainline](https://github.com/yzddmr6/xiaomipad-6pro-mainline)（SSC 传感器栈）、[opencv/opencv_zoo](https://github.com/opencv/opencv_zoo)（YuNet / SFace 人脸识别模型）

## 许可证

本仓库代码与脚本默认采用 [GPL-2.0-only](LICENSE) 开源协议；引用的第三方补丁保留其原作者与原有许可证。原厂固件及本机私有数据不随仓库分发。
