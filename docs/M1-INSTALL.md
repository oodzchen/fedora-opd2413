# M1：把 Fedora 45 KDE 装到机内并首次启动

M1.5–M1.8 的操作手册：每步的前提、命令、写入范围、判据和退路。
进度以 [STATUS.md](STATUS.md) 为准；每步做完把结果和证据位置记到 [WORKLOG.md](WORKLOG.md)。

**状态（2026-11-11）**：1.5a–1.8 全部完成，Fedora 已取代 Armada。本文保留为当时的操作记录和以后重装的参考；
实际执行中的偏差（镜像、rescue 插件、hostonly）都已改进脚本，结果记在 [WORKLOG.md](WORKLOG.md)。

## 约定

- "主机"指开发用的电脑，"平板"指运行中的 Armada（之后是 Fedora）。
- 主机到平板的 SSH 用 `private/ssh.sh`（root 密钥登录；平板 IP 变了就设 `OPD_HOST`）。
- 平板上的工作目录 `/run/opd2413-install`（tmpfs，重启即消失），软件包和脚本放 `/var/tmp/opd2413`。
- 账户和区域设置（用户 2026-11-10 确认）：登录名 `colin`、显示名 `Colin`、英文 `en_US.UTF-8`、
  时区 `Asia/Singapore`、主机名 `opd2413`。初始密码在 `private/install.env`，不进仓库。
- 平板重启后 `/run` 下的挂载都会消失。重启后要继续 1.6，先按 1.6 的"重新挂载"恢复。

## 1.5a 只读核对（完成）

结果（2026-11-10，Armada `20261104.92448d0.grey1`，内核 7.2.6 #32）：

| 项目 | 结果 |
|---|---|
| btrfs 顶层子卷 | `root`（Armada 的 ostree sysroot）、`var`、`home`，以及嵌套的 `home/armada/.local/share/Steam/steamapps` |
| 空间 | 文件系统 254.5 GiB，已用 88 GiB（`/var/home` 35 GiB，`/var/lib/armada` 39 GiB），可用约 165 GiB |
| 挂载 | `/sysroot` 和 `/boot`（sda17，ext4）只读；ESP 在 `/boot/efi` 可写，剩 69 MB |
| ostree 部署 | 索引 0 当前 `f24e0e96…`（grey1）；索引 1 `291e99d1…`（rollback，firmware1）；索引 2 `b0402782…`（已 pin，usb3） |
| `/boot/ostree` | 三个目录，与 ESP 的 `/ostree` 一一对应 |
| 工具 | 有 `podman` 5.8.9、`dnf5`、`btrfs`、`lsinitrd`、`rsync`；没有 `systemd-nspawn`、`createrepo_c` |
| 网络 | 能直连 Fedora 镜像站和容器仓库，无代理 |
| 其他 | SELinux Disabled；时区 UTC；NetworkManager 有 1 个 Wi-Fi 连接配置；失败单元 0 |
| ESP 同步 | `armada-bootimg-sync.service` 在开机和关机时各运行一次 `armada-boot-update`，把 `/boot/ostree` 镜像到 ESP |

Fedora 45 环境组核对（主机上的 aarch64 容器，只解析不安装）：
`@^kde-desktop-environment` 共 2204 个包，下载 3 GiB，安装后 8 GiB。
已包含 `plasma-login-manager`、`plasma-setup`、`plasma-keyboard`、`NetworkManager-wifi`、
`selinux-policy-targeted`、`iio-sensor-proxy`、`qrtr`、`rmtfs`、`bluez`、`pipewire`。

## 1.5b 安装根文件系统

**写入范围**：在 `ARMADA_ROOT` 的 btrfs 顶层新建子卷 `fedora` 和 `fedora-home` 并写入内容；
在 Armada 的 `/var/tmp/opd2413` 放软件包和脚本；podman 拉取一个 Fedora 容器镜像到 Armada 的 `/var`。
不动 Armada 的子卷、ESP 和其他分区。

**前提**：用户批准；电量 50% 以上或在充电；`private/ssh.sh true` 能连上。

主机上：

```sh
cd ~/github/fedora-opd2413
tools/collect-rpms.sh                      # 确认 out/rpms 是最新的一套
private/ssh.sh 'mkdir -p /var/tmp/opd2413/rpms'
scp -i ~/.ssh/opd2413_ed25519 -o UserKnownHostsFile=~/oneplus-pad2pro-work/known_hosts-internal \
    out/rpms/* root@<平板>:/var/tmp/opd2413/rpms/
scp -i ~/.ssh/opd2413_ed25519 -o UserKnownHostsFile=~/oneplus-pad2pro-work/known_hosts-internal \
    tools/install-rootfs.sh tools/install-kernel.sh root@<平板>:/var/tmp/opd2413/
private/ssh.sh 'cd /var/tmp/opd2413/rpms && sha256sum --check SHA256SUMS'
```

平板上（经 SSH；耗时主要在下载 3 GiB 和安装 2204 个包，放后台并把输出写到日志）：

```sh
. private/install.env     # 主机上执行，取得 OPD_USER_PASSWORD
private/ssh.sh "OPD_MIRROR=https://mirrors.jlu.edu.cn/fedora OPD_USER_PASSWORD='$OPD_USER_PASSWORD' \
    nohup /var/tmp/opd2413/install-rootfs.sh colin Colin \
    > /var/tmp/opd2413/install-rootfs.log 2>&1 &"
private/ssh.sh 'tail -3 /var/tmp/opd2413/install-rootfs.log'      # 查看进度
```

**必须指定 `OPD_MIRROR`**：Fedora 的 metalink 曾把平板分到只有约 35 KB/s 的镜像。换镜像前先在平板上核对
`releases/45` 和 `updates/45` 的 repodata 都完整（南京大学镜像 2026-11-10 的 `updates` 正在同步，
repomd 引用的文件返回 404）。核对方法见 WORKLOG 2026-11-10 "镜像"一节。

脚本做的事（细节见 `tools/install-rootfs.sh`）：核对机型和分区 → 挂载 btrfs 顶层 → 建两个子卷 →
在 Fedora 45 容器里用 `dnf --installroot` 安装 KDE 环境组（排除 Fedora 的 `kernel*`）→
写 fstab、主机名、时区、语言、machine-id、`/etc/kernel/cmdline`、`/etc/kernel/entry-token`、
`/.autorelabel` → 建用户 → 复制 root 的 SSH 公钥和 Wi-Fi 连接配置，SSH 只允许密钥登录 →
启用 sshd，默认目标设为图形界面。结束时新根仍挂在 `/run/opd2413-install/target`。

**判据**：

- 日志最后一行是 `Root file system installed and left mounted at …`。
- `rpm -q plasma-desktop` 有结果，`rpm -q kernel-core` 没有。
- `etc/fstab` 的两个 UUID 与 `blkid` 一致；`etc/kernel/cmdline` 含 `rootflags=subvol=fedora` 和 `enforcing=0`。
- `etc/systemd/system/display-manager.service` 指向 `plasmalogin.service`（或 sddm）。
- `btrfs subvolume list` 比之前多了 `fedora`、`fedora-home` 两项，原有的不变。

**装完后要人工看一眼的**（脚本没有处理，按结果决定）：

- `plasma-setup` 是首次启动向导。已经建了用户，它不应该再运行；检查它的 unit 条件
  （`systemctl --root=<新根> cat plasma-setup.service`），必要时在首启前禁用。
- `rmtfs`、`qrtr-ns`、`tqftpserv`、`pd-mapper` 这类高通服务的启用状态，与 Armada 里的做个对照。

**失败或撤销**：卸载 `/run/opd2413-install/target/home`、`target`，然后
`btrfs subvolume delete /run/opd2413-install/top/fedora-home /run/opd2413-install/top/fedora`。
脚本拒绝在子卷已存在时重跑，重试前先删。

## 1.6 部署内核到 ESP

**写入范围**：(a) Armada 的 ostree：移除两套旧部署；(b) ESP：Armada 的同步脚本删掉对应的两套
`/ostree/default-…` 和两个 `armada-ostree-*.conf`；(c) ESP 新增 Fedora 的四个文件；
(d) 新根里安装四个软件包及其依赖。不改 `loader.conf`、`/EFI`、`KSHIM.CHO`、`/dtbs`。

**前提**：1.5b 通过；用户批准；新根挂在 `/run/opd2413-install/target`。

**重新挂载**（只在平板重启过时需要）：

```sh
mkdir -p /run/opd2413-install/top /run/opd2413-install/target
mount -o subvolid=5,noatime /dev/disk/by-partlabel/ARMADA_ROOT /run/opd2413-install/top
mount -o subvol=fedora,noatime,compress=zstd:1,discard=async /dev/disk/by-partlabel/ARMADA_ROOT /run/opd2413-install/target
mount -o subvol=fedora-home,noatime,compress=zstd:1,discard=async /dev/disk/by-partlabel/ARMADA_ROOT /run/opd2413-install/target/home
```

### 1.6a 腾出 ESP 空间

不能直接删 ESP 上的文件：`armada-boot-update` 会在下次开关机时把 `/boot/ostree` 重新镜像回来，
到时 ESP 写满、同步失败。要让 Armada 自己把旧部署移除，再由它的同步脚本清理 ESP。

```sh
ostree admin status                      # 先确认索引：0 = 当前，1 = rollback，2 = pinned
ostree admin pin --unpin 2
ostree admin undeploy 2                  # 从大索引删起，索引不会错位
ostree admin undeploy 1
ostree admin status                      # 只剩当前部署
ls /boot/ostree                          # 只剩 default-f11793fe…
/usr/libexec/armada/armada-boot-update   # 同步到 ESP，删除多余的两套
ls /boot/efi/ostree /boot/efi/loader/entries
df -h /boot/efi                          # 预期可用约 360 MB
sha256sum /boot/efi/KSHIM.CHO            # 与操作前一致
```

操作前先记下 `sha256sum /boot/efi/KSHIM.CHO /boot/efi/EFI/BOOT/BOOTAA64.EFI /boot/efi/loader/loader.conf`。

**判据**：ESP 上只剩一套 `/ostree/default-f11793fe…` 和一个 `armada-ostree-*.conf`（标题 `Armada`）；
三个文件的哈希不变；可用空间不少于 200 MB。

**如果 `undeploy` 报错或状态不符**：停下，不要手工删 `/boot` 或 ESP 上的文件；把 `ostree admin status`
和报错记到工作日志再分析。此时 Armada 的当前部署和默认启动项都没动。

### 1.6b 安装内核和设备包

```sh
/var/tmp/opd2413/install-kernel.sh /var/tmp/opd2413/rpms 2>&1 | tee /var/tmp/opd2413/install-kernel.log
```

脚本做的事（细节见 `tools/install-kernel.sh`）：校验软件包哈希和 ESP 剩余空间 → 记录 ESP 上现有文件的哈希 →
把 ESP 绑定挂载到新根的 `/boot/efi` → 在容器里 `dnf --installroot` 安装四个包 →
`kernel-install` 写 ESP → 核对新文件和条目 → 核对 ESP 上其余文件的哈希都没变。

**判据**：

- 脚本最后一行是 `Kernel 7.2.6 deployed. The default boot entry is unchanged.`
- ESP 新增且仅新增：`/fedora/7.2.6/linux`、`/fedora/7.2.6/initrd`、
  `/fedora/7.2.6/sm8750-oneplus-pad2pro.dtb`、`/loader/entries/fedora-7.2.6.conf`。
- 条目的 `options` 与新根的 `/etc/kernel/cmdline` 一致。
- 安装日志里没有 `opd2413-initrd-check` 的报错（它失败时内核装不上）。

已离线确认：ESP 上现有的 `/dtbs/qcom/sm8750-oneplus-pad2pro.dtb` 与内核包里的 DTB 相同，
所以 DTB 同步插件不会改写它。

### 1.6c 确认默认路径没坏

重启平板，仍选 "Armada"，确认 Armada 正常进桌面、`systemctl --failed` 为空。
这一步验证腾空间和加条目没有影响原来的启动路径，之后再试 Fedora。

**失败的退路**：删除 ESP 上的 `/fedora` 目录和 `fedora-7.2.6.conf` 即恢复到 1.6a 之后的状态。

## 1.7 首次启动 Fedora

**用户操作**：重启 → kShimC 菜单选 **"Armada boot menu"** → systemd-boot 菜单里选
**"Fedora Linux 45 (KDE Plasma Desktop Edition)"**。

**预期**：第一次启动做 SELinux 重新标记（屏幕上可能长时间只有少量文字，几分钟），然后自动重启。
重启后 kShimC 记住的是 "Armada boot menu"，要再手选一次 Fedora，这次进入登录界面。

**机器证据**（主机经 SSH 采集，存到 `private/m1-firstboot/`）：

```sh
uname -r; cat /etc/os-release | head -3; cat /proc/cmdline
systemctl is-system-running; systemctl --failed --no-legend
journalctl -b -p err --no-pager | tail -50
findmnt -no SOURCE,OPTIONS / /home /boot/efi
lsblk -o NAME,RO,PARTLABEL /dev/sd?            # Android 分区 RO=1，ARMADA* 为 0
getenforce                                      # 预期 Permissive
dmesg | grep -iE 'nt36536|adreno|a8xx|gmu|ath12k|aw88|q6apm|firmware.*fail'
qdbus6 org.kde.KWin /KWin supportInformation | grep -iE 'renderer|OpenGL vendor'   # 以登录用户身份
bootctl status 2>&1 | head -20
```

**需要用户确认的**：看到登录界面和桌面；触控和多点；键盘套打字和触控板；播放一段声音；调亮度。

**判据**：[STATUS.md](STATUS.md) 的 M1 验收清单逐项有结果。GPU 若是 llvmpipe 软件渲染，记为
"Fedora 的 Mesa 不支持 Adreno 830"，不阻塞 M1，进入 M2 处理（带补丁的 Mesa 包）。

**启动失败的判断**：

| 现象 | 先查什么 |
|---|---|
| 选了 Fedora 后黑屏或卡住 | 等 5 分钟（可能在 relabel）；仍无反应则长按电源键重启回 Armada，挂载 `fedora` 子卷看 `var/log/journal` |
| 掉到 emergency shell | 根挂载问题：核对条目的 `root=UUID` 和 `rootflags` |
| 进了桌面但触控或 GPU 不工作 | `dmesg` 里的固件加载错误；`lsinitrd` 核对 |
| 没有 Wi-Fi 所以 SSH 不通 | 用键盘套在本机终端里查 `nmcli`，或回 Armada 看日志 |

Fedora 启动失败不影响另外两个系统：默认项仍是 Armada，ColorOS 入口不变。

## 1.8 取代 Armada

**前提**：1.7 通过，再做两到三次冷启动回归，用户确认可以日用并批准。

开始前先问用户：Armada 的 `/var/home`（35 GiB，含 Steam 游戏）里有没有要留的文件。

每小步之后冷启动验证一次：

1. `loader.conf` 的 `default armada-*` 改为 `default fedora-*`。之后 kShimC 的 "Armada" 项直接进 Fedora。
2. 在 Fedora 里用 `bootctl update --no-variables` 把 `/EFI/BOOT/BOOTAA64.EFI` 换成 Fedora 45 的
   systemd-boot（262）。先备份旧文件；QEMU 测试只覆盖了 259，换之前用 262 重跑一次
   `tests/qemu-esp-boot.sh`。
3. 删除 ESP 上的 `/ostree`、`armada-*.conf`、`/EFI/systemd/drivers/dtbloaderaa64.efi` 和
   `/dtbs/qcom` 下其他机型的 DTB（保留 `sm8750-oneplus-pad2pro.dtb`）。
4. 删除 btrfs 子卷 `root`、`var`、`home`（先删嵌套的 `steamapps`）。
5. `ARMADA_BOOT`（sda17）不再使用，处理方式见技术债 #7。

完成后更新 ARCHITECTURE.md §3，把"并存期"的描述改成最终布局。

## 已识别的风险

| 风险 | 处理 |
|---|---|
| ESP 空间不足（剩 69 MB） | 1.6a 先腾空间；`install-kernel.sh` 在空间不足 200 MB 时拒绝执行 |
| Armada 的启动同步脚本改写 ESP | 它只管理 `armada-*.conf`、`/ostree`、`/dtbs` 和 loader 本体，不碰 `/fedora`；1.6c 重启验证 |
| `ostree admin undeploy` 改动 Armada 的启动条目 | 只移除非当前部署；失败就停，不手工修；当前部署不受影响 |
| chroot 里 dracut 看到的是 Armada 的运行环境 | initramfs 用非 hostonly 模式，不依赖主机探测 |
| initramfs 缺设备固件 | `60-opd2413-initrd-check.install` 会让内核安装失败（有离线反例测试） |
| ESP 上的 systemd-boot 259 读不了 262 生成的条目 | QEMU 离线测试已覆盖 |
| Fedora 的 Mesa 不支持 Adreno 830 | 桌面退回软件渲染但仍能用；记录后在 M2 处理 |
| SELinux 重新标记中途断电 | 首启前确认电量；`enforcing=0`，标记不完整不阻止启动 |
| 主机在安装中途断开 SSH | 安装用 `nohup` 放后台，日志在 `/var/tmp/opd2413/`，重连后看日志 |
