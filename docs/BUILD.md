# 构建软件包与离线测试

在主机（x86_64 Fedora）上执行，不需要平板。产物都在被 Git 忽略的 `out/` 下。

## 需要的输入

| 输入 | 位置 | 说明 |
|---|---|---|
| 内核构建产物 | `<armada>/output/opd2413-stage4/kern2/out/armada-kernel-7.2.6.tar.zst` | SHA-256 `7c6d84fa…`，见 [../kernel/README.md](../kernel/README.md) |
| 固件 | `<armada>/system_files/usr/lib/firmware` | 62 个原厂文件在该仓库的忽略目录里，9 个 WCN7860 文件是已提交的 |
| 设备文件 | 本仓库 `device/` | |

`<armada>` 是 armada 仓库 `oneplus-pad-2-pro` 分支的检出。

主机需要 `rpm-build`、`podman`、`qemu-user-static`（跑 aarch64 容器）、`qemu-system-aarch64`、`mtools`、`zstd`。

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
| `package-install-test.sh` | 在干净的 Fedora 45 aarch64 里装四个包后，ESP 布局、启动条目、initramfs 里的 66 个设备固件、Fedora 内核被排除；以及 initramfs 缺固件时内核安装被拒绝 | `PASS: package install` |
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
