# 引导菜单和无人值守重启

## 两层菜单

| 层 | 内容 | 选择记在哪 | Linux 能否改 |
|---|---|---|---|
| kShimC（`boot_b`） | ColorOS / Fedora / Fedora boot menu，倒计时后启动记住的项 | ESP 文件 `KSHIM.CHO` 的两页记录 | 能：`boot-select kshim` |
| systemd-boot（ESP） | Fedora 的内核条目 | `loader/loader.conf` 的 `default` | 能：`boot-select next` |

"Fedora" 进 systemd-boot 时关闭菜单、直接启动 `default`；"Fedora boot menu" 显示 systemd-boot 菜单且不倒计时，用于手工回退。

做不到的：systemd-boot 的一次性启动变量（`LoaderEntryOneShot`）和启动计数。U-Boot 只在内存里保存 EFI 变量（`efivarfs` 只读），
也故意不写存储（`Failed to rename … Access denied`）。

## 工具

设备端 `/usr/libexec/opd2413/boot-select`（`opd2413-device` 0.1-7 起，`default` 命令 0.1-8 起），源码 `device/libexec/boot-select`：

```sh
boot-select status                    # 菜单项、记住的项、倒计时、loader 默认项、本次启动的条目、待恢复的一次性设置
boot-select kshim Fedora              # 让 kShimC 记住某一项
boot-select kshim Fedora --manifest new-boot_b.img --keep-current
                                      # 为另一个 boot_b 的 manifest 预写记录，不动当前 boot_b 的记录
boot-select next opd2413-m3test       # 下一次启动这个内核条目
boot-select default fedora-7.2.15-1.opd2413
                                      # 改 loader 默认项（有待恢复的 next 时改的是恢复目标）
```

`next`、`default` 给精确条目名时写入完整 id（`xxx.conf`）：systemd-boot 拿 `default` 与带 `.conf` 的条目 id 做通配匹配，
不带后缀的名字匹配不上，会悄悄退回最新条目（0.1-10 之前的 `boot-select` 就是这样）。通配值（如 `fedora-*`）原样写入。
`tools/tablet-reboot.py` 重启前用平板上的 `bootctl list` 核对将启动的条目。

**测试新内核的顺序**：`loader.conf` 平时是 `default fedora-*`，systemd-boot 选版本最高的条目，所以 `dnf install` 一个新内核后它立刻就成了默认项。
装之前（或装完、重启之前）先 `boot-select default <当前内核的条目>` 固定默认项，再 `tools/tablet-reboot.py --entry <新条目>` 一次性启动；
验收通过后 `boot-select default 'fedora-*'` 并冷启动复查。

`next` 改 `default` 并留下记录；`opd2413-boot-restore.service` 在任何内核挂上根分区后立刻改回原默认项。
所以测试内核进到用户态以后，再崩溃或复位都会回到正常内核。**在挂根之前就复位的测试内核会反复启动**，
需要人在 kShimC 选 "Fedora boot menu" 再选正常内核（没有启动期写存储的能力，这一步无法自动化；真正的一次性选择要改 kShimC，见下）。

主机端 `tools/tablet-reboot.py`：`--entry X` 一次性启动某条目并等它回来，报告内核、条目和系统状态；`--fetch` 随后取日志。

## KSHIM.CHO 记录

格式与 Armada `porting/oneplus-pad-2-pro/kshim/{choice_journal.h,boot_choice.c}` 一致。每条记录绑定 manifest 的全部字节、ESP 的分区 GUID
和 provision 页的随机数，所以：

- 改 kShimC 菜单（名字、倒计时、条目）会让现有记录失效，回落到 manifest 默认项 ColorOS；
- 两页记录可以分别属于新旧两个 manifest。换 `boot_b` 时先写"旧 manifest → ColorOS""新 manifest → Fedora"，
  重启自动进 ColorOS 写 `boot_b`，再重启自动回 Fedora，全程不用碰菜单。

写入只改文件里一个 4 KiB 数据页（经挂载的 vfat），写后用 O_DIRECT 从块设备回读整个 16 KiB 区段核对；FAT 和目录项除修改时间外不变，
与 Armada 的 provision 工具做法相同。离线测试 `tests/boot-select-test.py`：有私有镜像时还会用真实 `boot_b` 重现平板上的记录，
并用 Armada 的 C 解码器验证新记录。

## 以后可以做的

- 真正的一次性 kShimC 选择：记录加"下次一次"字段，kShimC 在交接前先写回原选择（它已有写记录的能力），再加一个会设置
  `LoaderEntryOneShot`（启动期的内存变量够用）的 U-Boot 变体。需要改 kShimC 和 U-Boot、再写一次 `boot_b`。只在挂根前失败的测试多了再做。
