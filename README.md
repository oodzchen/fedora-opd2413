# Fedora on OnePlus Pad 2 Pro (OPD2413)

在一加平板 2 Pro（SM8750）上运行标准、可变的 Fedora 45 aarch64 + KDE Plasma，与 ColorOS 双启动。

项目处于早期阶段，尚无可安装的版本。

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 整体架构：分层、启动链、存储布局、软件包、内核路线 |
| [docs/STATUS.md](docs/STATUS.md) | 实现进度、下一步、设备状态 |
| [docs/HARDWARE.md](docs/HARDWARE.md) | 硬件清单和每项功能的复用来源 |
| [docs/BUILD.md](docs/BUILD.md) | 构建软件包和运行离线测试 |
| [docs/M1-INSTALL.md](docs/M1-INSTALL.md) | 第一阶段的安装手册：每步的命令、写入范围和判据 |
| [docs/WORKLOG.md](docs/WORKLOG.md) | 工作日志 |
| [docs/TECH-DEBT.md](docs/TECH-DEBT.md) | 技术债 |
| [AGENTS.md](AGENTS.md) | 工作规则、设备安全规则、已确认的决定 |

启动链（kShimC、U-Boot）和内核移植的历史在 Armada 移植分支里；本仓库只包含 Fedora 侧的集成、
内核补丁序列和打包。原厂固件不随仓库分发。
