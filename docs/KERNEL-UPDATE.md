# 内核升级与回滚

在平板上装新的 `kernel-opd2413`、改启动参数、退回旧内核的步骤。内核怎么构建见 [../kernel/README.md](../kernel/README.md)。
2026-11-11 装内核 `7.2.6-3.opd2413` 时按这个流程做过一遍。

## 先知道的几件事

- **ESP 只放两个内核**（每个约 128 MB，ESP 512 MiB）。`opd2413-device` 设置了 `installonly_limit=2`：装第三个时，
  dnf 自动卸掉**最旧**的那个。
- **默认项是版本最新的内核**：`loader.conf` 写的是 `default fedora-*`，systemd-boot 在匹配的条目里选排在最前（版本最高）的。
  装完新内核，下次开机就会进新内核。
- **U-Boot 的 EFI 变量在系统运行时只读**：`bootctl set-default`、`bootctl set-oneshot` 都会失败。要临时选别的条目，只能在开机时
  手选（kShimC 选 "Armada boot menu"，再在 systemd-boot 菜单里选）。
- **kShimC 会记住上次选的菜单项**（ESP 上的 `KSHIM.CHO`）。手选过 "Armada boot menu" 之后，下次要改回 "Armada"，
  否则每次开机都停在 systemd-boot 菜单。
- **版本号不能互为前缀**：卸载时 kernel-install 会删除所有 `fedora-<kver>*.conf`。版本号一律用 `7.2.6-<N>.opd2413`。
- **每个条目带自己的 DTB**（`/fedora/<kver>/sm8750-oneplus-pad2pro.dtb`），回滚内核时 DTB 一起回滚。
- 不要在 ESP 上自己建以 `fedora-` 开头的条目：会被 `default fedora-*` 匹配，也会被卸载时的通配删掉。

## 装新内核

**前提：当前最新的内核已经真机通过。** 否则装新内核时被自动卸掉的就是那个已知能用的旧内核，ESP 上只剩两个都没验证过的内核。
如果最新的那个还没验证，先 `dnf remove` 掉它，再装新的。

```sh
# 主机
tools/build-kernel-rpm.sh out/kernel-<kver>.tar.zst <kver> 1   # 见 kernel/README.md；带 -N.opd2413 时最后的 1 不起作用
OPD_OS=fedora private/scp.sh out/rpmbuild/RPMS/aarch64/kernel-opd2413-<ver>.aarch64.rpm /var/tmp/

# 平板（root）
rpm -q kernel-opd2413                       # 记下现有的两个，确认被卸掉的是哪个
df -h /boot/efi                             # 卸掉一个、装上一个，空间不变；保险起见留 150 MB 以上
dnf install /var/tmp/kernel-opd2413-<ver>.aarch64.rpm
```

装完核对：

```sh
rpm -q kernel-opd2413                        # 两个：上一个已验证的 + 新的
ls /boot/efi/loader/entries/                 # 两个 fedora-<kver>.conf
cmp /usr/lib/modules/<kver>/vmlinuz /boot/efi/fedora/<kver>/linux
bootctl list --no-pager | grep title         # 新内核标 (default)
```

然后把主机的 `out/rpms` 对齐：旧内核包移到 `out/old-rpms/`，再跑 `tools/collect-rpms.sh`。

## 开机验证

重启（`systemctl reboot`；插着电时 `poweroff` 也会自动重新开机），kShimC 30 秒后自动进默认项。回来后：

```sh
uname -r                                     # 新内核
systemctl is-system-running                  # running
systemctl --failed
getenforce                                   # Enforcing
ausearch -m AVC,USER_AVC,SELINUX_ERR -ts boot
journalctl -b -p err -k
```

再请用户看一眼：画面、触控、键盘、声音、亮度、熄屏后亮屏。都正常才算新内核真机通过，结果写进 WORKLOG 和
`kernel/README.md` 的补丁表。

## 改启动参数

`/etc/kernel/cmdline` 只在 kernel-install 写条目时生效，改完要对每个已装的内核重新执行一次：

```sh
for k in $(ls /usr/lib/modules); do kernel-install add "$k" "/usr/lib/modules/$k/vmlinuz"; done
grep -H ^options /boot/efi/loader/entries/fedora-*.conf
```

这会重新生成 initramfs，每个内核约 1 分钟。改的参数影响启动的话，冷启动验证。

## 回滚

- **临时**：开机时 kShimC 选 "Armada boot menu" → systemd-boot 菜单选旧内核。之后记得把 kShimC 改回 "Armada"。
- **长期**：进入能用的内核后 `dnf remove kernel-opd2413-<坏的版本>`，默认项自然回到剩下的那个。
  不要靠改 `loader.conf` 的 `default` 来固定旧内核（它不归任何包管，改了容易忘）。
- **用回退内核 `7.2.6-2.opd2413` 启动过**：它没有 SELinux，期间新建的文件没有标签。回到新内核后执行 `fixfiles onboot` 并重启
  （全盘重新标记约 23 秒）。见技术债 #22。
- **两个内核都起不来**：kShimC 的 USB 入口，或回 ColorOS 用 adb 处理 ESP。ESP 整分区备份在 `private/esp-20261110/`
  （那是 Armada 时期的内容，只用来恢复 systemd-boot、`loader.conf` 和 `KSHIM.CHO`，不要整盘写回）。
