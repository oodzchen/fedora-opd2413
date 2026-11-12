# rpmbuild --define 'pkgver X' --define 'pkgrel N' --define 'srcdir /repo/device'

Name:           opd2413-device
Version:        %{pkgver}
Release:        %{pkgrel}
Summary:        Device integration for Fedora on the OnePlus Pad 2 Pro (OPD2413)
License:        GPL-2.0-or-later
BuildArch:      noarch

Requires:       kernel-opd2413
Requires:       opd2413-firmware
Requires:       dracut
Requires:       systemd-udev
Requires:       systemd-boot-unsigned
Requires:       util-linux
Requires:       diffutils
Requires:       coreutils
Requires:       gawk
Requires:       python3

%description
What a stock Fedora needs to run on the OnePlus Pad 2 Pro next to Android:
the udev guard that keeps Android's partitions read-only, the dracut module
that puts device firmware into the initramfs, kernel-install settings for the
ESP layout the boot chain expects, a dnf exclude for Fedora's own kernel, and
a unit that keeps every pstore (ramoops) record of a failed boot, and
boot-select, which picks the next kShimC menu entry and kernel without the menus.

%prep

%build

%install
install -D -m 0755 %{srcdir}/libexec/ufs-guard %{buildroot}/usr/libexec/opd2413/ufs-guard
install -D -m 0755 %{srcdir}/libexec/early-firmware %{buildroot}/usr/libexec/opd2413/early-firmware
install -D -m 0755 %{srcdir}/libexec/boot-select %{buildroot}/usr/libexec/opd2413/boot-select
install -D -m 0644 %{srcdir}/udev/90-opd2413-ufs-guard.rules %{buildroot}/usr/lib/udev/rules.d/90-opd2413-ufs-guard.rules
install -D -m 0644 %{srcdir}/udev/90-opd2413-pogo-keyboard.hwdb %{buildroot}/usr/lib/udev/hwdb.d/90-opd2413-pogo-keyboard.hwdb
install -D -m 0755 %{srcdir}/dracut/90opd2413/module-setup.sh %{buildroot}/usr/lib/dracut/modules.d/90opd2413/module-setup.sh
install -D -m 0644 %{srcdir}/dracut/90-opd2413.conf %{buildroot}/usr/lib/dracut/dracut.conf.d/90-opd2413.conf
install -D -m 0644 %{srcdir}/kernel-install/50-opd2413.conf %{buildroot}/usr/lib/kernel/install.conf.d/50-opd2413.conf
install -D -m 0644 %{srcdir}/kernel-install/devicetree %{buildroot}/usr/lib/kernel/devicetree
install -D -m 0755 %{srcdir}/kernel-install/60-opd2413-initrd-check.install %{buildroot}/usr/lib/kernel/install.d/60-opd2413-initrd-check.install
install -D -m 0755 %{srcdir}/kernel-install/95-opd2413-dtb.install %{buildroot}/usr/lib/kernel/install.d/95-opd2413-dtb.install
install -D -m 0644 %{srcdir}/dnf/50-opd2413-kernel.conf %{buildroot}/usr/share/dnf5/libdnf.conf.d/50-opd2413-kernel.conf
# dracut-config-rescue (in Fedora's desktop environments) builds a second,
# larger initramfs per kernel; the 512 MiB ESP has no room for it.
mkdir -p %{buildroot}/etc/kernel/install.d
ln -s /dev/null %{buildroot}/etc/kernel/install.d/51-dracut-rescue.install
install -D -m 0644 %{srcdir}/systemd/90-opd2413-sleep.conf %{buildroot}/usr/lib/systemd/sleep.conf.d/90-opd2413-sleep.conf
# Enabled statically: it only runs when the previous boot left pstore records.
install -D -m 0644 %{srcdir}/systemd/opd2413-pstore-keep.service %{buildroot}/usr/lib/systemd/system/opd2413-pstore-keep.service
mkdir -p %{buildroot}/usr/lib/systemd/system/sysinit.target.wants
ln -s ../opd2413-pstore-keep.service %{buildroot}/usr/lib/systemd/system/sysinit.target.wants/opd2413-pstore-keep.service
install -D -m 0644 %{srcdir}/systemd/opd2413-boot-restore.service %{buildroot}/usr/lib/systemd/system/opd2413-boot-restore.service
ln -s ../opd2413-boot-restore.service %{buildroot}/usr/lib/systemd/system/sysinit.target.wants/opd2413-boot-restore.service

%files
/usr/libexec/opd2413
/usr/lib/udev/rules.d/90-opd2413-ufs-guard.rules
/usr/lib/udev/hwdb.d/90-opd2413-pogo-keyboard.hwdb
/usr/lib/dracut/modules.d/90opd2413
/usr/lib/dracut/dracut.conf.d/90-opd2413.conf
/usr/lib/kernel/install.conf.d/50-opd2413.conf
/usr/lib/kernel/devicetree
/usr/lib/kernel/install.d/60-opd2413-initrd-check.install
/usr/lib/kernel/install.d/95-opd2413-dtb.install
/usr/share/dnf5/libdnf.conf.d/50-opd2413-kernel.conf
/usr/lib/systemd/sleep.conf.d/90-opd2413-sleep.conf
/usr/lib/systemd/system/opd2413-pstore-keep.service
/usr/lib/systemd/system/sysinit.target.wants/opd2413-pstore-keep.service
/usr/lib/systemd/system/opd2413-boot-restore.service
/usr/lib/systemd/system/sysinit.target.wants/opd2413-boot-restore.service
/etc/kernel/install.d/51-dracut-rescue.install
