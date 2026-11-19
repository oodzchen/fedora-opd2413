%global debug_package %{nil}

Name:           opd2413-gaming
Version:        %{pkgver}
Release:        %{pkgrel}
Summary:        Gaming performance foundation for Fedora on OnePlus Pad 2 Pro (OPD2413)
License:        GPL-2.0-or-later
BuildArch:      noarch

Requires:       opd2413-device
Requires:       python3
Requires:       util-linux
Requires:       systemd
Requires:       systemd-udev
Recommends:     libappindicator

%description
Non-invasive gaming performance baseline for the OnePlus Pad 2 Pro (SM8750 /
Adreno 830) on Fedora 45: sysctl memory/RT-uclamp/network tuning, 16 ms GPU
devfreq polling and /dev/ntsync permissions, TEO cpuidle activation, Q6APM
PipeWire audio buffer floors, plus the opd-game launcher and fanless-safe
opd-power telemetry/profile/bypass-charging CLI.

%prep

%build

%install
install -D -m 0755 %{srcdir}/bin/opd-game %{buildroot}%{_bindir}/opd-game
install -D -m 0755 %{srcdir}/bin/opd-power %{buildroot}%{_bindir}/opd-power
install -D -m 0755 %{srcdir}/bin/steam %{buildroot}%{_bindir}/steam
install -D -m 0644 %{srcdir}/sysctl/60-opd2413-gaming.conf %{buildroot}%{_prefix}/lib/sysctl.d/60-opd2413-gaming.conf
install -D -m 0644 %{srcdir}/udev/60-opd2413-gaming.rules %{buildroot}%{_prefix}/lib/udev/rules.d/60-opd2413-gaming.rules
install -D -m 0644 %{srcdir}/tmpfiles/60-opd2413-gaming.conf %{buildroot}%{_prefix}/lib/tmpfiles.d/60-opd2413-gaming.conf
install -D -m 0644 %{srcdir}/environment.d/61-opd2413-gaming.conf %{buildroot}%{_prefix}/lib/environment.d/61-opd2413-gaming.conf
install -D -m 0644 %{srcdir}/pipewire/pipewire-99-opd2413-gaming-buffers.conf \
    %{buildroot}%{_datadir}/pipewire/pipewire.conf.d/99-opd2413-gaming-buffers.conf
install -D -m 0644 %{srcdir}/pipewire/pipewire-pulse-99-opd2413-gaming-buffers.conf \
    %{buildroot}%{_datadir}/pipewire/pipewire-pulse.conf.d/99-opd2413-gaming-buffers.conf
install -D -m 0644 %{srcdir}/binfmt-dispatcher/50-opd2413-native-fex.toml \
    %{buildroot}%{_prefix}/lib/binfmt-dispatcher.d/50-opd2413-native-fex.toml
# Mask Asahi 16 KiB binfmt-dispatcher x86/x86_64 wrappers and early FEX entries,
# then register FEX last (zz-opd2413-*) so kernel binfmt_misc LIFO places native
# /usr/bin/FEX above qemu-x86_64-static.
mkdir -p %{buildroot}%{_sysconfdir}/binfmt.d
ln -s /dev/null %{buildroot}%{_sysconfdir}/binfmt.d/zz-binfmt-dispatcher-x86.conf
ln -s /dev/null %{buildroot}%{_sysconfdir}/binfmt.d/zz-binfmt-dispatcher-x86_64.conf
ln -s /dev/null %{buildroot}%{_sysconfdir}/binfmt.d/FEX-x86.conf
ln -s /dev/null %{buildroot}%{_sysconfdir}/binfmt.d/FEX-x86_64.conf
install -D -m 0644 %{srcdir}/binfmt/zz-opd2413-FEX-x86.conf \
    %{buildroot}%{_prefix}/lib/binfmt.d/zz-opd2413-FEX-x86.conf
install -D -m 0644 %{srcdir}/binfmt/zz-opd2413-FEX-x86_64.conf \
    %{buildroot}%{_prefix}/lib/binfmt.d/zz-opd2413-FEX-x86_64.conf

%post
/usr/lib/systemd/systemd-sysctl /usr/lib/sysctl.d/60-opd2413-gaming.conf >/dev/null 2>&1 || :
systemd-tmpfiles --create /usr/lib/tmpfiles.d/60-opd2413-gaming.conf >/dev/null 2>&1 || :
udevadm control --reload >/dev/null 2>&1 || :
udevadm trigger --subsystem-match=devfreq --action=change >/dev/null 2>&1 || :
for e in binfmt-dispatcher-x86 binfmt-dispatcher-x86_64 FEX-x86 FEX-x86_64; do
    if [ -e "/proc/sys/fs/binfmt_misc/${e}" ]; then
        printf '%s\n' -1 > "/proc/sys/fs/binfmt_misc/${e}" 2>/dev/null || :
    fi
done
systemctl restart systemd-binfmt.service >/dev/null 2>&1 || :

%files
%{_bindir}/opd-game
%{_bindir}/opd-power
%{_bindir}/steam
%{_prefix}/lib/sysctl.d/60-opd2413-gaming.conf
%{_prefix}/lib/udev/rules.d/60-opd2413-gaming.rules
%{_prefix}/lib/tmpfiles.d/60-opd2413-gaming.conf
%{_prefix}/lib/environment.d/61-opd2413-gaming.conf
%{_datadir}/pipewire/pipewire.conf.d/99-opd2413-gaming-buffers.conf
%{_datadir}/pipewire/pipewire-pulse.conf.d/99-opd2413-gaming-buffers.conf
%{_prefix}/lib/binfmt-dispatcher.d/50-opd2413-native-fex.toml
%{_prefix}/lib/binfmt.d/zz-opd2413-FEX-x86.conf
%{_prefix}/lib/binfmt.d/zz-opd2413-FEX-x86_64.conf
%{_sysconfdir}/binfmt.d/zz-binfmt-dispatcher-x86.conf
%{_sysconfdir}/binfmt.d/zz-binfmt-dispatcher-x86_64.conf
%{_sysconfdir}/binfmt.d/FEX-x86.conf
%{_sysconfdir}/binfmt.d/FEX-x86_64.conf
